"""Aggregate telemetry in PostgreSQL; do not load an unbounded event history."""

from sqlalchemy import func, select

from .models import GeminiTelemetry as Event

TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "thinking_tokens",
    "cached_tokens",
    "tool_tokens",
    "total_tokens",
    "billable_characters",
)


class TelemetryRepository:
    def __init__(self, session):
        self.session = session

    def add(self, event):
        self.session.add(Event(**event.model_dump()))

    def report(self, *, since, until, operation, page, hourly):
        filters = [
            Event.tenant_id == "parrilladas",
            Event.created_at >= since,
            Event.created_at <= until,
        ]
        if operation is not None:
            filters.append(Event.operation == operation)
        model = Event.is_model_call.is_(True)
        failure = Event.status != "ok"

        def count(condition):
            return func.count().filter(condition)

        p50 = func.percentile_cont(0.5).within_group(Event.duration_ms).filter(model)
        p95 = func.percentile_cont(0.95).within_group(Event.duration_ms).filter(model)
        summary = (
            self.session.execute(
                select(
                    count(model).label("calls"),
                    count(model & failure).label("errors"),
                    count(model & (Event.http_status == 429)).label("quota_errors"),
                    count(model & Event.total_tokens.is_not(None)).label("usage_reported_calls"),
                    func.percentile_cont(0.5)
                    .within_group(Event.duration_ms)
                    .filter(Event.operation == "rag_result")
                    .label("rag_p50_ms"),
                    func.percentile_cont(0.95)
                    .within_group(Event.duration_ms)
                    .filter(Event.operation == "rag_result")
                    .label("rag_p95_ms"),
                    p50.label("p50_ms"),
                    p95.label("p95_ms"),
                    *[func.sum(getattr(Event, f)).filter(model).label(f) for f in TOKEN_FIELDS],
                    count((Event.operation == "rag_result") & (Event.status == "ok")).label(
                        "rag_answers"
                    ),
                    count(
                        (Event.operation == "rag_result") & (Event.status == "no_evidence")
                    ).label("rag_no_evidence"),
                    count((Event.operation == "rag_result") & (Event.status == "fallback")).label(
                        "rag_fallbacks"
                    ),
                    count(
                        (Event.operation == "extraction_result")
                        & (Event.reason == "invalid_output")
                    ).label("extraction_invalid"),
                    func.count().label("total_events"),
                ).where(*filters)
            )
            .mappings()
            .one()
        )
        groups = (
            self.session.execute(
                select(
                    Event.operation,
                    Event.model,
                    func.count().label("calls"),
                    count(failure).label("errors"),
                    func.percentile_cont(0.5).within_group(Event.duration_ms).label("p50_ms"),
                    func.percentile_cont(0.95).within_group(Event.duration_ms).label("p95_ms"),
                    *[
                        func.sum(getattr(Event, f)).label(f)
                        for f in ("input_tokens", "output_tokens", "total_tokens")
                    ],
                )
                .where(*filters, model)
                .group_by(Event.operation, Event.model)
                .order_by(Event.operation, Event.model)
            )
            .mappings()
            .all()
        )
        # UTC grouping is stable; the Admin presents bucket timestamps in Costa Rica.
        bucket = func.date_trunc("hour" if hourly else "day", Event.created_at, "UTC")
        timeline = (
            self.session.execute(
                select(
                    bucket.label("at"),
                    func.count().label("calls"),
                    count(failure).label("errors"),
                    func.sum(Event.total_tokens).label("total_tokens"),
                )
                .where(*filters, model)
                .group_by(bucket)
                .order_by(bucket)
            )
            .mappings()
            .all()
        )
        recent = self.session.scalars(
            select(Event)
            .where(*filters)
            .order_by(Event.created_at.desc(), Event.id.desc())
            .offset((page - 1) * 50)
            .limit(50)
        ).all()
        data = dict(summary)
        data.update(
            first_recorded_at=self.session.scalar(
                select(func.min(Event.created_at)).where(Event.tenant_id == "parrilladas")
            ),
            error_rate=(100 * data["errors"] / data["calls"]) if data["calls"] else None,
            groups=[dict(g) for g in groups],
            timeline=[dict(p) for p in timeline],
            recent=[
                {
                    **{
                        field: getattr(e, field)
                        for field in (
                            "id",
                            "trace_id",
                            "created_at",
                            "tenant_id",
                            "operation",
                            "model",
                            "region",
                            "duration_ms",
                            "status",
                            "is_model_call",
                            "error_kind",
                            "http_status",
                            "finish_reason",
                            "reason",
                            "result_count",
                            "selected_count",
                            "similarity",
                            *TOKEN_FIELDS,
                        )
                    }
                }
                for e in recent
            ],
            page=page,
        )
        return data

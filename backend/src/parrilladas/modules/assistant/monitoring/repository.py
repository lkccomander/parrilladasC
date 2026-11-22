"""Bounded SQL for monitoring. Caller owns transactions and authorization."""

from sqlalchemy import delete, func, select, text

from parrilladas.modules.assistant.models import GeminiTelemetry, KnowledgeChunk, KnowledgeDocument

from .ops_models import RagAlert, RagIndexCheck, RagProbeRun
from .trace_models import RagQueryTrace


class MonitoringRepository:
    def __init__(self, session):
        self.session = session

    def trace_stats(self, tenant_id, since, until):
        row = (
            self.session.execute(
                select(
                    func.count().label("count"),
                    func.count()
                    .filter(RagQueryTrace.decision == "no_evidence")
                    .label("no_evidence"),
                    func.count()
                    .filter(func.jsonb_array_length(RagQueryTrace.results) == 0)
                    .label("empty"),
                    func.percentile_cont(0.50)
                    .within_group(RagQueryTrace.search_ms)
                    .label("search_p50"),
                    func.percentile_cont(0.95)
                    .within_group(RagQueryTrace.search_ms)
                    .label("search_p95"),
                    func.percentile_cont(0.95)
                    .within_group(RagQueryTrace.total_ms)
                    .label("total_p95"),
                    func.sum(RagQueryTrace.unsupported_amounts).label("unsupported_amounts"),
                ).where(
                    RagQueryTrace.tenant_id == tenant_id,
                    RagQueryTrace.kind == "online",
                    RagQueryTrace.created_at >= since,
                    RagQueryTrace.created_at <= until,
                )
            )
            .mappings()
            .one()
        )
        return dict(row)

    def calls(self, tenant_id, since, until):
        return (
            self.session.execute(
                select(
                    func.count().label("count"),
                    func.count().filter(GeminiTelemetry.status != "ok").label("errors"),
                ).where(
                    GeminiTelemetry.tenant_id == tenant_id,
                    GeminiTelemetry.is_model_call.is_(True),
                    GeminiTelemetry.created_at >= since,
                    GeminiTelemetry.created_at <= until,
                )
            )
            .mappings()
            .one()
        )

    def traces(self, tenant_id, since, until, *, limit=25, decision=None):
        query = select(RagQueryTrace).where(
            RagQueryTrace.tenant_id == tenant_id,
            RagQueryTrace.created_at >= since,
            RagQueryTrace.created_at <= until,
        )
        if decision:
            query = query.where(RagQueryTrace.decision == decision)
        return self.session.scalars(
            query.order_by(RagQueryTrace.created_at.desc(), RagQueryTrace.id.desc()).limit(limit)
        ).all()

    def trace(self, tenant_id, trace_id):
        return self.session.scalar(
            select(RagQueryTrace).where(
                RagQueryTrace.tenant_id == tenant_id, RagQueryTrace.id == trace_id
            )
        )

    def fact_metadata(self, tenant_id, ids):
        if not ids:
            return {}
        rows = self.session.execute(
            select(
                KnowledgeChunk.id,
                KnowledgeChunk.topic,
                KnowledgeDocument.source,
                KnowledgeDocument.content_version,
            )
            .join(KnowledgeDocument)
            .where(KnowledgeDocument.tenant_id == tenant_id, KnowledgeChunk.id.in_(ids))
        ).all()
        return {str(row.id): row for row in rows}

    def knowledge(self, tenant_id):
        return (
            self.session.execute(
                select(
                    KnowledgeDocument.source,
                    KnowledgeDocument.content_version,
                    KnowledgeDocument.active,
                    KnowledgeDocument.catalog,
                    KnowledgeDocument.created_at,
                    func.count(KnowledgeChunk.id).label("chunks"),
                )
                .outerjoin(KnowledgeChunk)
                .where(KnowledgeDocument.tenant_id == tenant_id)
                .group_by(KnowledgeDocument.id)
                .order_by(KnowledgeDocument.created_at.desc())
                .limit(100)
            )
            .mappings()
            .all()
        )

    def vectors(self, tenant_id):
        return (
            self.session.execute(
                select(
                    func.count().label("vectors"),
                    func.array_agg(func.distinct(KnowledgeDocument.embedding_model)).label(
                        "models"
                    ),
                    func.array_agg(func.distinct(func.vector_dims(KnowledgeChunk.embedding))).label(
                        "dimensions"
                    ),
                    func.count()
                    .filter(
                        (KnowledgeDocument.source == "")
                        | (KnowledgeDocument.embedding_model == "")
                        | (KnowledgeChunk.topic == "")
                    )
                    .label("missing_metadata"),
                )
                .select_from(KnowledgeChunk)
                .join(KnowledgeDocument)
                .where(KnowledgeDocument.tenant_id == tenant_id, KnowledgeDocument.active.is_(True))
            )
            .mappings()
            .one()
        )

    def storage(self):
        return (
            self.session.execute(
                text("""
            SELECT pg_total_relation_size('knowledge_chunks') AS total_bytes,
                   pg_relation_size('knowledge_chunks') AS table_bytes,
                   pg_indexes_size('knowledge_chunks') AS index_bytes,
                   n_live_tup, n_dead_tup,
                   (SELECT extversion FROM pg_extension WHERE extname = 'vector') AS vector_version
            FROM pg_stat_user_tables WHERE relid = 'knowledge_chunks'::regclass
        """)
            )
            .mappings()
            .one_or_none()
        )

    def indexes(self):
        return (
            self.session.execute(
                text("""
            SELECT c.relname AS name, am.amname AS mode, c.reloptions AS options,
                   pg_relation_size(c.oid) AS size_bytes,
                   pg_get_indexdef(i.indexrelid) AS definition
            FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
            JOIN pg_am am ON am.oid = c.relam
            WHERE i.indrelid = 'knowledge_chunks'::regclass
              AND am.amname IN ('hnsw','ivfflat') AND i.indisvalid
            ORDER BY c.relname
        """)
            )
            .mappings()
            .all()
        )

    def database_health(self, tenant_id):
        """Return cheap, read-only health facts for the vector store.

        This deliberately does not expose connection details or customer data.  It is
        called on every dashboard refresh, so keep the probes bounded and metadata-only.
        """
        vector = self.session.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one_or_none()
        documents = (
            self.session.execute(
                select(
                    func.count().label("total"),
                    func.count().filter(KnowledgeDocument.active.is_(True)).label("active"),
                ).where(KnowledgeDocument.tenant_id == tenant_id)
            )
            .mappings()
            .one()
        )
        chunks = (
            self.session.execute(
                select(func.count().label("total"))
                .select_from(KnowledgeChunk)
                .join(KnowledgeDocument)
                .where(KnowledgeDocument.tenant_id == tenant_id)
            )
            .mappings()
            .one()
        )
        return {
            "pgvector_version": vector,
            "documents_total": documents["total"],
            "documents_active": documents["active"],
            "chunks_total": chunks["total"],
        }

    def latest_probe(self, tenant_id, since):
        return self.session.scalar(
            select(RagProbeRun)
            .where(RagProbeRun.tenant_id == tenant_id, RagProbeRun.created_at >= since)
            .order_by(RagProbeRun.created_at.desc())
            .limit(1)
        )

    def latest_index_checks(self, tenant_id, since):
        return self.session.scalars(
            select(RagIndexCheck)
            .where(RagIndexCheck.tenant_id == tenant_id, RagIndexCheck.created_at >= since)
            .order_by(RagIndexCheck.created_at.desc())
            .limit(20)
        ).all()

    def alerts(self, tenant_id):
        return self.session.scalars(
            select(RagAlert)
            .where(RagAlert.tenant_id == tenant_id, RagAlert.resolved_at.is_(None))
            .order_by(RagAlert.severity, RagAlert.first_seen)
            .limit(100)
        ).all()

    def set_alert(self, tenant_id, key, severity, message, value, now):
        existing = self.session.scalar(
            select(RagAlert)
            .where(
                RagAlert.tenant_id == tenant_id,
                RagAlert.rule_key == key,
                RagAlert.resolved_at.is_(None),
            )
            .with_for_update()
        )
        if severity is None:
            if existing:
                existing.resolved_at = now
            return
        if existing:
            existing.severity, existing.message = severity, message
            existing.last_seen, existing.detail = now, {"value": value}
        else:
            self.session.add(
                RagAlert(
                    tenant_id=tenant_id,
                    rule_key=key,
                    severity=severity,
                    message=message,
                    detail={"value": value},
                    first_seen=now,
                    last_seen=now,
                )
            )

    def observed_leaks(self, tenant_id, since):
        # JSON IDs are validated UUIDs by the recorder. Never return other tenants' metadata.
        return (
            self.session.execute(
                text("""
            SELECT count(*) FILTER (WHERE d.tenant_id <> :tenant) AS cross_tenant,
                   count(*) FILTER (WHERE NOT d.active) AS inactive
            FROM rag_query_traces t
            CROSS JOIN LATERAL jsonb_array_elements(t.results) r
            JOIN knowledge_chunks c ON c.id = (r->>'chunk_id')::uuid
            JOIN knowledge_documents d ON d.id = c.document_id
            WHERE t.tenant_id = :tenant AND t.created_at >= :since
        """),
                {"tenant": tenant_id, "since": since},
            )
            .mappings()
            .one()
        )

    def foreign_vectors(self, tenant_id):
        return self.session.execute(
            select(KnowledgeChunk.topic, KnowledgeChunk.embedding)
            .join(KnowledgeDocument)
            .where(KnowledgeDocument.tenant_id != tenant_id, KnowledgeDocument.active.is_(True))
            .limit(5)
        ).all()

    def purge(self, tenant_id, before):
        # Bounded batches; cascade is not used for business data.
        ids = (
            select(RagQueryTrace.id)
            .where(RagQueryTrace.tenant_id == tenant_id, RagQueryTrace.created_at < before)
            .order_by(RagQueryTrace.created_at)
            .limit(1000)
        )
        return self.session.execute(delete(RagQueryTrace).where(RagQueryTrace.id.in_(ids))).rowcount

"""Monitoring use cases. Measurements do not change customer-facing decisions."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from .repository import MonitoringRepository
from .schemas import (
    AlertView,
    EvalRunView,
    EvalSetSummary,
    IndexInfo,
    KnowledgeRow,
    Metric,
    MonitoringHealth,
    MonitoringReport,
    TraceDetail,
    TraceResult,
    TraceSummary,
)

logger = logging.getLogger(__name__)


def _catalog_valid_until(catalog):
    value = catalog.get("valid_until") if isinstance(catalog, dict) else None
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def metric(
    key,
    label,
    value=None,
    *,
    watch=None,
    breach=None,
    lower=False,
    percentage=False,
    unit="",
    note="",
    target="",
):
    status = "not_measured"
    display = "No medido"
    if value is not None:
        value = float(value)
        status = "ok"
        if breach is not None and (value < breach if lower else value > breach):
            status = "breach"
        elif watch is not None and (value < watch if lower else value > watch):
            status = "watch"
        display = f"{value * 100:.1f}%" if percentage else f"{value:,.2f}".rstrip("0").rstrip(".")
        display += unit
    return Metric(
        key=key,
        label=label,
        value=value,
        display=display,
        status=status,
        note=note,
        target_text=target,
    )


def trace_summary(row):
    return TraceSummary(**{key: getattr(row, key) for key in TraceSummary.model_fields})


class MonitoringService:
    def __init__(self, sessions, settings, *, evaluations=None):
        self.sessions, self.settings, self.evaluations = sessions, settings, evaluations

    def report(self, *, tenant_id="parrilladas", days=7):
        now = datetime.now(UTC)
        since = now - timedelta(days=days)
        with self.sessions() as session, session.begin():
            repository = MonitoringRepository(session)
            stats = repository.trace_stats(tenant_id, since, now)
            calls = repository.calls(tenant_id, since, now)
            vectors = repository.vectors(tenant_id)
            storage = repository.storage()
            database = repository.database_health(tenant_id)
            indexes = repository.indexes()
            recent = repository.traces(tenant_id, since, now)
            traces = [trace_summary(row) for row in recent]
            knowledge = [
                KnowledgeRow(
                    source=row["source"],
                    content_version=row["content_version"],
                    status=(
                        "Vencida"
                        if (valid_until := _catalog_valid_until(row["catalog"]))
                        and valid_until.date() < now.date()
                        else "Publicada"
                        if row["active"]
                        else "Inactiva"
                    ),
                    valid_until=valid_until,
                    chunks=row["chunks"],
                    created_at=row["created_at"],
                )
                for row in repository.knowledge(tenant_id)
            ]
            alerts = [
                AlertView(**{key: getattr(row, key) for key in AlertView.model_fields})
                for row in repository.alerts(tenant_id)
            ]
            probe = repository.latest_probe(tenant_id, since)
            leaks = repository.observed_leaks(tenant_id, since)
            checks = repository.latest_index_checks(tenant_id, since)
            index_definition = indexes[0]["definition"] if indexes else ""
            distance = next(
                (
                    name
                    for name, label in (
                        ("Cosine", "vector_cosine_ops"),
                        ("L2", "vector_l2_ops"),
                        ("Inner product", "vector_ip_ops"),
                    )
                    if label in index_definition
                ),
                None,
            )
            index = IndexInfo(
                mode=indexes[0]["mode"] if indexes else "exact",
                name=indexes[0]["name"] if indexes else None,
                distance=distance,
                parameters=dict(option.split("=", 1) for option in (indexes[0]["options"] or []))
                if indexes
                else {},
                checks=[
                    {
                        "ef_search": row.ef_search,
                        "recall": row.recall_vs_exact,
                        "p95_ms": row.p95_ms,
                        "sample_size": row.sample_size,
                    }
                    for row in checks
                ],
                note=(
                    "Búsqueda exacta: recall del índice 100% por definición; no mide relevancia."
                    if not indexes
                    else "ANN: calidad frente a exacta pendiente de chequeo."
                    if not checks
                    else "ANN: comparación medida frente a búsqueda exacta."
                ),
            )
            latency_series = [
                float(row.search_ms)
                for row in reversed(recent)
                if row.search_ms is not None and row.kind == "online"
            ]
            probe_count = probe.probes if probe else 0
            cross_tenant = max(leaks["cross_tenant"], probe.violations if probe else 0)
        latest = self.evaluations.latest(tenant_id=tenant_id) if self.evaluations else None
        eval_data = latest.metrics if latest else {}
        sets = self.evaluations.sets(tenant_id=tenant_id) if self.evaluations else []
        cfg = self.settings
        recall = metric(
            "recall_at_5",
            "Recall@5",
            eval_data.get("recall_at_5"),
            watch=cfg.rag_target_recall_watch,
            breach=cfg.rag_target_recall_breach,
            lower=True,
            percentage=True,
            target=f"Objetivo ≥ {cfg.rag_target_recall_watch:.0%}",
            note="Evaluación curada; recuperador online conserva k=3.",
        )
        faithfulness = metric(
            "faithfulness",
            "Fidelidad · proxy determinista",
            eval_data.get("faithfulness"),
            watch=cfg.rag_target_faithfulness_watch,
            breach=cfg.rag_target_faithfulness_breach,
            lower=True,
            percentage=True,
            note="Comprueba números y citas; no evalúa cada afirmación semántica.",
        )
        empty = stats["empty"] / stats["count"] if stats["count"] else None
        no_evidence = stats["no_evidence"] / stats["count"] if stats["count"] else None
        error_rate = calls["errors"] / calls["count"] if calls["count"] else None
        total_tuples = storage["n_live_tup"] + storage["n_dead_tup"] if storage else 0
        bloat = storage["n_dead_tup"] / total_tuples if storage and total_tuples else None
        # No conversation IDs are collected; a trace is not a customer conversation.
        kpis = [
            recall,
            faithfulness,
            metric(
                "no_evidence_handoffs",
                "Derivaciones sin evidencia",
                note="No medido: un resultado sin evidencia no demuestra derivación al asesor.",
            ),
            metric(
                "latency_p95_end_to_end",
                "p95 recorrido RAG",
                stats["total_p95"],
                watch=cfg.rag_target_latency_watch_ms,
                breach=cfg.rag_target_latency_breach_ms,
                unit=" ms",
                note="Incluye embedding, búsqueda y selección; excluye transporte WhatsApp.",
            ),
            metric(
                "cost_per_conversation",
                "Costo por conversación",
                note="No medido: sin correlación de conversación y tarifa completa.",
            ),
            metric(
                "cross_tenant_results",
                "Resultados entre tenants",
                cross_tenant if probe_count or stats["count"] else None,
                watch=0,
                breach=0,
                target="Siempre 0",
                note=(
                    f"Última prueba: {probe_count} consultas."
                    if probe_count
                    else "Sin vectores de otros tenants para prueba operativa."
                ),
            ),
        ]
        retrieval = [
            recall,
            *[
                metric(key, label, eval_data.get(key), percentage=True)
                for key, label in (
                    ("precision_at_5", "Precision@5"),
                    ("mrr", "MRR"),
                    ("ndcg_at_5", "nDCG@5"),
                    ("context_relevance", "Relevancia del contexto"),
                )
            ],
            metric(
                "empty_result_rate",
                "Búsquedas sin resultados",
                empty,
                percentage=True,
                watch=cfg.rag_target_no_evidence_watch,
                breach=cfg.rag_target_no_evidence_breach,
            ),
            metric(
                "no_evidence_rate",
                "Resultados sin evidencia utilizable",
                no_evidence,
                percentage=True,
                watch=cfg.rag_target_no_evidence_watch,
                breach=cfg.rag_target_no_evidence_breach,
            ),
        ]
        generation = [
            faithfulness,
            *[
                metric(key, label, eval_data.get(key), percentage=True)
                for key, label in (
                    ("answer_relevance", "Relevancia de respuesta"),
                    ("citation_accuracy", "Exactitud de citas"),
                    ("correct_handoff_rate", "Decisión esperada"),
                    ("language_match", "Idioma"),
                )
            ],
            metric(
                "unsupported_amounts",
                "Importes sin respaldo",
                stats["unsupported_amounts"]
                if stats["unsupported_amounts"] is not None
                else eval_data.get("unsupported_amounts"),
                watch=0,
                breach=0,
                target="Siempre 0",
            ),
        ]
        health = [
            metric("vectors", "Vectores publicados", vectors["vectors"]),
            metric("documents_total", "Documentos del tenant", database["documents_total"]),
            metric("documents_active", "Documentos publicados", database["documents_active"]),
            metric("chunks_total", "Fragmentos totales", database["chunks_total"]),
            Metric(
                key="pgvector_version",
                label="Extensión pgvector",
                display=database["pgvector_version"] or "No medido",
                status="ok" if database["pgvector_version"] else "not_measured",
                note="Versión reportada por PostgreSQL en tiempo real.",
            ),
            Metric(
                key="embedding_profile",
                label="Perfil de embedding",
                display=", ".join(vectors["models"] or [])
                + " · "
                + ", ".join(str(n) for n in (vectors["dimensions"] or []))
                + " dimensiones"
                if vectors["vectors"]
                else "Sin vectores publicados",
                status="breach"
                if len(vectors["models"] or []) > 1 or len(vectors["dimensions"] or []) > 1
                else "ok"
                if vectors["vectors"]
                else "not_measured",
            ),
            metric("search_p50", "Búsqueda p50", stats["search_p50"], unit=" ms"),
            metric("search_p95", "Búsqueda p95", stats["search_p95"], unit=" ms"),
            metric(
                "index_recall_vs_exact",
                "Recall del índice frente a exacta",
                1.0 if not indexes else checks[0].recall_vs_exact if checks else None,
                percentage=True,
                lower=True,
                watch=cfg.rag_target_index_recall_watch,
                breach=cfg.rag_target_index_recall_breach,
                note=index.note,
            ),
            metric(
                "storage_bytes",
                "Tabla e índices · instalación",
                storage["total_bytes"] if storage else None,
                unit=" bytes",
            ),
            metric(
                "table_bytes",
                "Tabla · instalación",
                storage["table_bytes"] if storage else None,
                unit=" bytes",
            ),
            metric(
                "index_bytes",
                "Índices · instalación",
                storage["index_bytes"] if storage else None,
                unit=" bytes",
            ),
            metric(
                "dead_tuples",
                "Tuplas muertas",
                storage["n_dead_tup"] if storage else None,
            ),
            metric(
                "bloat_ratio",
                "Proporción estimada de tuplas muertas",
                bloat,
                percentage=True,
                watch=cfg.rag_target_bloat_watch,
                breach=cfg.rag_target_bloat_breach,
                note="Estadísticas de PostgreSQL compartidas; no es bloat físico medido.",
            ),
            metric(
                "ingestion_lag",
                "Retraso de indexación",
                note="No existen fechas verificadas de publicación e indexación.",
            ),
            metric(
                "missing_metadata",
                "Fragmentos sin metadatos requeridos",
                vectors["missing_metadata"],
                watch=0,
                breach=0,
            ),
            metric(
                "inactive_chunks_retrieved",
                "Fragmentos inactivos recuperados",
                leaks["inactive"] if stats["count"] else None,
                watch=0,
                breach=0,
            ),
            metric(
                "expired_chunks_retrievable",
                "Fragmentos vencidos recuperables",
                note="El catálogo actual no define caducidad; no se puede medir.",
            ),
            metric(
                "provider_error_rate",
                "Errores del proveedor",
                error_rate,
                percentage=True,
                watch=cfg.rag_target_provider_error_watch,
                breach=cfg.rag_target_provider_error_breach,
            ),
        ]
        if probe and probe.probes and not probe.violations:
            alerts.append(
                AlertView(
                    rule_key="isolation_probe",
                    severity="healthy",
                    message="Prueba de aislamiento sin resultados de otro tenant.",
                    first_seen=probe.created_at,
                    last_seen=probe.created_at,
                    detail={"probes": probe.probes},
                )
            )
        return MonitoringReport(
            days=days,
            generated_at=now,
            tenant_id=tenant_id,
            last_eval_run_at=latest.completed_at if latest else None,
            kpis=kpis,
            retrieval_metrics=retrieval,
            generation_metrics=generation,
            vector_health=health,
            index=index,
            traces=traces,
            knowledge=knowledge,
            alerts=alerts,
            eval_sets=[
                EvalSetSummary(id=s.id, name=s.name, version=s.version, cases=s.case_count)
                for s in sets
            ],
            latency_series=latency_series,
            price_table_updated_at=str(cfg.rag_price_table_updated_at)
            if cfg.rag_price_table_updated_at
            else None,
            eval_enabled=cfg.rag_eval_enabled,
        )

    def health(self, *, tenant_id="parrilladas", days=1):
        """Return one live health snapshot for SSE and bounded polling clients."""
        report = self.report(tenant_id=tenant_id, days=days)
        measured = [
            item for item in (*report.kpis, *report.vector_health) if item.status != "not_measured"
        ]
        statuses = {item.status for item in (*report.kpis, *report.vector_health)}
        if "breach" in statuses:
            status = "critical"
        elif "watch" in statuses:
            status = "degraded"
        elif measured:
            status = "healthy"
        else:
            status = "unknown"
        return MonitoringHealth(
            status=status,
            generated_at=report.generated_at,
            freshness_seconds=0,
            report=report,
        )

    def traces(self, *, tenant_id, days, limit=25, decision=None):
        now = datetime.now(UTC)
        with self.sessions() as session, session.begin():
            rows = MonitoringRepository(session).traces(
                tenant_id, now - timedelta(days=days), now, limit=limit, decision=decision
            )
            return [trace_summary(row) for row in rows]

    def maintenance(self, *, tenant_id="parrilladas"):
        """Purge old traces and deduplicate actionable operational alerts."""
        if self.evaluations is not None and self.settings.rag_eval_enabled:
            try:
                self.evaluations.run_next()
            except Exception:
                logger.warning("RAG evaluation worker unavailable")
        now = datetime.now(UTC)
        since = now - timedelta(days=self.settings.rag_trace_retention_days)
        window = now - timedelta(days=1)
        with self.sessions() as session, session.begin():
            repository = MonitoringRepository(session)
            repository.purge(tenant_id, since)
            stats = repository.trace_stats(tenant_id, window, now)
            calls = repository.calls(tenant_id, window, now)
            vectors = repository.vectors(tenant_id)
            database = repository.database_health(tenant_id)
            storage = repository.storage()
            indexes = repository.indexes()
            checks = repository.latest_index_checks(tenant_id, window)
            probe = repository.latest_probe(tenant_id, window)
            total = stats["count"]
            error_rate = calls["errors"] / calls["count"] if calls["count"] else None
            no_evidence = stats["no_evidence"] / total if total else None
            repository.set_alert(
                tenant_id,
                "unsupported_amounts",
                "breach"
                if stats["unsupported_amounts"] and stats["unsupported_amounts"] > 0
                else None,
                "Se detectaron importes sin evidencia aprobada.",
                stats["unsupported_amounts"],
                now,
            )
            repository.set_alert(
                tenant_id,
                "provider_error_rate",
                "breach"
                if error_rate is not None
                and error_rate > self.settings.rag_target_provider_error_breach
                else "watch"
                if error_rate is not None
                and error_rate > self.settings.rag_target_provider_error_watch
                else None,
                "La tasa de errores del proveedor supera el objetivo.",
                error_rate,
                now,
            )
            repository.set_alert(
                tenant_id,
                "no_evidence_rate",
                "breach"
                if no_evidence is not None
                and no_evidence > self.settings.rag_target_no_evidence_breach
                else "watch"
                if no_evidence is not None
                and no_evidence > self.settings.rag_target_no_evidence_watch
                else None,
                "La recuperación devuelve evidencia insuficiente con demasiada frecuencia.",
                no_evidence,
                now,
            )
            repository.set_alert(
                tenant_id,
                "missing_metadata",
                "breach" if vectors["missing_metadata"] else None,
                "Hay fragmentos publicados sin metadatos requeridos.",
                vectors["missing_metadata"],
                now,
            )
            bloat = None
            if storage:
                total_tuples = storage["n_live_tup"] + storage["n_dead_tup"]
                bloat = storage["n_dead_tup"] / total_tuples if total_tuples else None
            repository.set_alert(
                tenant_id,
                "bloat_ratio",
                "breach"
                if bloat is not None and bloat > self.settings.rag_target_bloat_breach
                else "watch"
                if bloat is not None and bloat > self.settings.rag_target_bloat_watch
                else None,
                "La proporción estimada de tuplas muertas requiere mantenimiento.",
                bloat,
                now,
            )
            index_recall = checks[0].recall_vs_exact if checks else 1.0 if not indexes else None
            repository.set_alert(
                tenant_id,
                "index_recall",
                "breach"
                if index_recall is not None
                and index_recall < self.settings.rag_target_index_recall_breach
                else "watch"
                if index_recall is not None
                and index_recall < self.settings.rag_target_index_recall_watch
                else None,
                "El recall del índice ANN cayó frente a la búsqueda exacta.",
                index_recall,
                now,
            )
            repository.set_alert(
                tenant_id,
                "cross_tenant_results",
                "breach" if probe and probe.violations else None,
                "La prueba de aislamiento encontró resultados de otro tenant.",
                probe.violations if probe else None,
                now,
            )
            repository.set_alert(
                tenant_id,
                "pgvector_extension",
                "breach" if not database["pgvector_version"] else None,
                "La extensión pgvector no está disponible en PostgreSQL.",
                None,
                now,
            )

    def trace(self, trace_id, *, tenant_id="parrilladas"):
        with self.sessions() as session, session.begin():
            repository = MonitoringRepository(session)
            row = repository.trace(tenant_id, trace_id)
            if row is None:
                return None
            ids = [UUID(r["chunk_id"]) for r in row.results]
            metadata = repository.fact_metadata(tenant_id, ids)
            results = []
            for result in row.results:
                fact = metadata.get(result["chunk_id"])
                results.append(
                    TraceResult(
                        **result,
                        title=fact.topic if fact else None,
                        source=fact.source if fact else None,
                        content_version=fact.content_version if fact else None,
                    )
                )
            scores = [r.score for r in results]
            return TraceDetail(
                **trace_summary(row).model_dump(),
                query_hash=row.query_hash,
                embed_ms=row.embed_ms,
                search_ms=row.search_ms,
                top_k=row.top_k,
                score_threshold=row.score_threshold,
                embedding_model=row.embedding_model,
                embedding_dim=row.embedding_dim,
                index_mode=row.index_mode,
                unsupported_amounts=row.unsupported_amounts,
                results=results,
                top1_gap=scores[0] - scores[1] if len(scores) > 1 else None,
            )

    def eval_report(self, run_id, *, tenant_id="parrilladas"):
        result = self.evaluations.report(run_id, tenant_id=tenant_id)
        return None if result is None else self.eval_run_view(result)

    @staticmethod
    def eval_run_view(result):
        """Translate the evaluation module contract to the compact HTTP contract."""
        return EvalRunView(
            id=result.id,
            status=result.status,
            started_at=result.started_at,
            finished_at=result.completed_at,
            metrics=result.metrics,
            error=result.error_kind,
        )

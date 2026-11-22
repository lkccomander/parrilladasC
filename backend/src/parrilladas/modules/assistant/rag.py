"""Ingest approved catalog atomically; retrieve evidence and render only stored facts."""

import hashlib
import json
import logging
from time import monotonic

from sqlalchemy.exc import SQLAlchemyError

from .errors import ExtractionUnavailable
from .knowledge import ApprovedMenu, KnowledgeAnswer, answer_question
from .models import KnowledgeChunk, KnowledgeDocument
from .rag_contracts import (
    SOURCE,
    KnowledgeDocumentView,
    KnowledgeOverview,
    RagProvider,
    validated_vector,
)
from .rag_repository import KnowledgeRepository
from .telemetry import Telemetry, telemetry_trace

logger = logging.getLogger(__name__)


def catalog_facts(menu: ApprovedMenu):
    # Generate bounded facts from validated fields, never arbitrary source instructions.
    names = [item.name for item in menu.items if item.active]
    facts = []
    if names:
        facts.append(
            (
                "menu",
                "Nuestro menú incluye estas opciones: "
                + ", ".join(names)
                + ". Un asesor confirma la combinación y los detalles de tu evento.",
            )
        )
    facts.append(
        (
            "coverage",
            "Atendemos en "
            + ", ".join(menu.coverage.provinces)
            + ", Costa Rica. La cobertura no confirma disponibilidad para una fecha "
            "ni costos de traslado.",
        )
    )
    if menu.prepared_on_site:
        facts.append(("preparation", "Cocinamos en el lugar del evento."))
    return facts


class KnowledgeService:
    def __init__(
        self,
        session_factory,
        provider: RagProvider | None,
        settings,
        *,
        telemetry=None,
        recorder=None,
    ):
        self.sessions = session_factory
        self.provider = provider
        self.settings = settings
        self.telemetry = telemetry or Telemetry()
        self.recorder = recorder

    def ingest(self, menu: ApprovedMenu) -> str:
        if self.provider is None:
            raise ExtractionUnavailable("Knowledge provider unavailable")
        payload = menu.model_dump(mode="json")
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        # An unchanged load is free; no external calls or version churn.
        with self.sessions() as session, session.begin():
            active = KnowledgeRepository(session).active(menu.tenant_id)
            if self._same(active, menu, digest):
                return "unchanged"
            self._check_version(active, menu)
        facts = catalog_facts(menu)
        chunks = [
            KnowledgeChunk(
                topic=topic,
                body=body,
                embedding=validated_vector(self.provider.embed(body, document=True)),
            )
            for topic, body in facts
        ]
        # All remote calls complete before acquiring the publication lock.
        with self.sessions() as session, session.begin():
            repository = KnowledgeRepository(session)
            repository.lock_publication()
            active = repository.active(menu.tenant_id)
            if self._same(active, menu, digest):
                return "unchanged"
            self._check_version(active, menu)
            repository.publish(
                KnowledgeDocument(
                    tenant_id=menu.tenant_id,
                    source=SOURCE,
                    content_version=menu.content_version,
                    content_hash=digest,
                    embedding_model=self.settings.embedding_model,
                    embedding_location=self.settings.embedding_location,
                    active=True,
                    catalog=payload,
                ),
                chunks,
            )
        return "published"

    def _same(self, active, menu, digest):
        return active is not None and (
            active.content_version == menu.content_version
            and active.content_hash == digest
            and active.embedding_model == self.settings.embedding_model
            and active.embedding_location == self.settings.embedding_location
        )

    @staticmethod
    def _check_version(active, menu):
        if active is not None and menu.content_version <= active.content_version:
            raise ValueError("Increment content_version before replacing published knowledge")

    @telemetry_trace
    def answer(self, topic, *, tenant_id, question=None, kind="online"):
        started = monotonic()
        observation = {
            "decision": "error",
            "decision_reason": "internal_error",
            "results": [],
            "embed_ms": None,
            "search_ms": None,
            "used_count": 0,
            "index_mode": "unknown",
            "unsupported_amounts": None,
        }
        query = question or {
            "menu": "¿Cuál es el menú?",
            "coverage": "¿Dónde atienden?",
            "preparation": "¿Cocinan en el lugar del evento?",
        }.get(topic, "")
        try:
            return self._answer(topic, tenant_id=tenant_id, query=query, observation=observation)
        finally:
            if self.recorder is not None:
                try:
                    self.recorder.record(
                        query=query,
                        tenant_id=tenant_id,
                        kind=kind,
                        embedding_model=self.settings.embedding_model,
                        embedding_dim=768,
                        top_k=3,
                        score_threshold=self.settings.rag_min_similarity,
                        total_ms=max(0, int((monotonic() - started) * 1000)),
                        **observation,
                    )
                except Exception:
                    logger.warning("RAG trace recorder unavailable")

    def _answer(self, topic, *, tenant_id, query, observation):
        started = monotonic()
        fallback = answer_question(topic, tenant_id=tenant_id)
        if tenant_id != "parrilladas" or topic not in {"menu", "coverage", "preparation"}:
            observation.update(decision="bypassed", decision_reason="unsupported")
            return fallback
        if not self.settings.rag_enabled or self.provider is None:
            observation.update(
                decision="catalog_fallback",
                decision_reason="disabled"
                if not self.settings.rag_enabled
                else "provider_unavailable",
            )
            self.telemetry.emit(
                operation="rag_result",
                duration_ms=max(0, int((monotonic() - started) * 1000)),
                status="fallback",
                reason="catalog_fallback",
            )
            return fallback
        if not query.strip() or len(query) > 4000:
            observation.update(decision="no_evidence", decision_reason="invalid_query")
            self.telemetry.emit(
                operation="rag_result",
                duration_ms=max(0, int((monotonic() - started) * 1000)),
                status="no_evidence",
                reason="invalid_query",
            )
            return answer_question("policies", tenant_id=tenant_id)
        try:
            embedding_started = monotonic()
            try:
                vector = validated_vector(self.provider.embed(query, document=False))
            finally:
                observation["embed_ms"] = max(0, int((monotonic() - embedding_started) * 1000))
            search_started = monotonic()
            try:
                with self.sessions() as session, session.begin():
                    repository = KnowledgeRepository(session)
                    if repository.active(tenant_id) is None:
                        raise ExtractionUnavailable("Knowledge not published")
                    facts = repository.retrieve(
                        tenant_id,
                        topic,
                        vector,
                        model=self.settings.embedding_model,
                        location=self.settings.embedding_location,
                        minimum=self.settings.rag_min_similarity,
                    )
            finally:
                observation["search_ms"] = max(0, int((monotonic() - search_started) * 1000))
            observation["results"] = [
                {"chunk_id": fact.id, "rank": rank, "score": fact.similarity, "used": False}
                for rank, fact in enumerate(facts, 1)
            ]
            if not facts:
                observation.update(decision="no_evidence", decision_reason="no_matches")
                self.telemetry.emit(
                    operation="rag_result",
                    duration_ms=max(0, int((monotonic() - started) * 1000)),
                    status="no_evidence",
                    reason="no_matches",
                    result_count=0,
                    selected_count=0,
                )
                return answer_question("policies", tenant_id=tenant_id)
            selection = self.provider.select_facts(query, facts)
            ids = selection.fact_ids
            allowed = {fact.id: fact for fact in facts}
            if not ids or len(set(ids)) != len(ids) or any(i not in allowed for i in ids):
                observation.update(
                    decision="no_evidence",
                    decision_reason="no_selection" if not ids else "invalid_citation",
                )
                self.telemetry.emit(
                    operation="rag_result",
                    duration_ms=max(0, int((monotonic() - started) * 1000)),
                    status="no_evidence",
                    reason="no_selection" if not ids else "invalid_citation",
                    result_count=len(facts),
                    selected_count=0,
                    similarity=max(f.similarity for f in facts),
                )
                return answer_question("policies", tenant_id=tenant_id)
            selected = [allowed[i] for i in ids]
            observation.update(
                decision="grounded",
                decision_reason="grounded",
                used_count=len(selected),
                unsupported_amounts=0,
            )
            for result in observation["results"]:
                result["used"] = result["chunk_id"] in ids
            self.telemetry.emit(
                operation="rag_result",
                duration_ms=max(0, int((monotonic() - started) * 1000)),
                status="ok",
                reason="grounded",
                result_count=len(facts),
                selected_count=len(selected),
                similarity=max(f.similarity for f in selected),
            )
            # Model prose is never sent: every claim is an approved stored fact.
            return KnowledgeAnswer(
                "\n\n".join(f.text for f in selected),
                "rag:" + ",".join(f"{f.source}:v{f.content_version}:{f.id}" for f in selected),
            )
        except (ExtractionUnavailable, SQLAlchemyError, ValueError):
            observation.update(decision="catalog_fallback", decision_reason="catalog_fallback")
            self.telemetry.emit(
                operation="rag_result",
                duration_ms=max(0, int((monotonic() - started) * 1000)),
                status="fallback",
                reason="catalog_fallback",
            )
            logger.warning("RAG unavailable; using approved catalog fallback")
            return fallback

    def isolation_probe(self, tenant_id, vectors):
        """Read-only check using production retrieval filters, without model calls."""
        samples = [(topic, validated_vector(vector)) for topic, vector in vectors[:5]]
        with self.sessions() as session, session.begin():
            return KnowledgeRepository(session).isolation_probe(
                tenant_id,
                samples,
                model=self.settings.embedding_model,
                location=self.settings.embedding_location,
                minimum=self.settings.rag_min_similarity,
            )

    def overview(self, *, tenant_id):
        documents = []
        with self.sessions() as session, session.begin():
            repository = KnowledgeRepository(session)
            document = repository.active(tenant_id)
            if document is not None:
                documents.append(
                    KnowledgeDocumentView(
                        source=document.source,
                        content_version=document.content_version,
                        content_hash=document.content_hash,
                        embedding_model=document.embedding_model,
                        embedding_location=document.embedding_location,
                        facts=[
                            repository.fact(c, document) for c in repository.chunks(document.id)
                        ],
                    )
                )
        return KnowledgeOverview(enabled=self.settings.rag_enabled, documents=documents)

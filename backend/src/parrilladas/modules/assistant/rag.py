"""Ingest approved catalog atomically; retrieve evidence and render only stored facts."""

import hashlib
import json
import logging

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
    def __init__(self, session_factory, provider: RagProvider | None, settings):
        self.sessions = session_factory
        self.provider = provider
        self.settings = settings

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

    def answer(self, topic, *, tenant_id, question=None):
        fallback = answer_question(topic, tenant_id=tenant_id)
        if tenant_id != "parrilladas" or topic not in {"menu", "coverage", "preparation"}:
            return fallback
        if not self.settings.rag_enabled or self.provider is None:
            return fallback
        query = (
            question
            or {
                "menu": "¿Cuál es el menú?",
                "coverage": "¿Dónde atienden?",
                "preparation": "¿Cocinan en el lugar del evento?",
            }[topic]
        )
        if not query.strip() or len(query) > 4000:
            return answer_question("policies", tenant_id=tenant_id)
        try:
            vector = validated_vector(self.provider.embed(query, document=False))
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
            if not facts:
                return answer_question("policies", tenant_id=tenant_id)
            selection = self.provider.select_facts(query, facts)
            ids = selection.fact_ids
            allowed = {fact.id: fact for fact in facts}
            if not ids or len(set(ids)) != len(ids) or any(i not in allowed for i in ids):
                return answer_question("policies", tenant_id=tenant_id)
            selected = [allowed[i] for i in ids]
            # Model prose is never sent: every claim is an approved stored fact.
            return KnowledgeAnswer(
                "\n\n".join(f.text for f in selected),
                "rag:" + ",".join(f"{f.source}:v{f.content_version}:{f.id}" for f in selected),
            )
        except (ExtractionUnavailable, SQLAlchemyError, ValueError):
            logger.warning("RAG unavailable; using approved catalog fallback")
            return fallback

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

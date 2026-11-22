"""SQL for versioned, tenant-scoped knowledge. Caller owns the transaction."""

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from .models import KnowledgeChunk, KnowledgeDocument
from .rag_contracts import SOURCE, RetrievedFact


class KnowledgeRepository:
    def __init__(self, session: Session):
        self.session = session

    def lock_publication(self):
        self.session.execute(text("SELECT pg_advisory_xact_lock(741903271)"))

    def active(self, tenant_id):
        return self.session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.source == SOURCE,
                KnowledgeDocument.active.is_(True),
            )
        )

    def publish(self, document, chunks):
        self.session.execute(
            update(KnowledgeDocument)
            .where(
                KnowledgeDocument.tenant_id == document.tenant_id,
                KnowledgeDocument.source == document.source,
                KnowledgeDocument.active.is_(True),
            )
            .values(active=False)
        )
        self.session.add(document)
        self.session.flush()
        for chunk in chunks:
            chunk.document_id = document.id
            self.session.add(chunk)

    def retrieve(self, tenant_id, topic, vector, *, model, location, minimum):
        distance = KnowledgeChunk.embedding.cosine_distance(vector)
        rows = self.session.execute(
            select(KnowledgeChunk, KnowledgeDocument, distance)
            .join(KnowledgeDocument, KnowledgeDocument.id == KnowledgeChunk.document_id)
            .where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.source == SOURCE,
                KnowledgeDocument.active.is_(True),
                KnowledgeDocument.embedding_model == model,
                KnowledgeDocument.embedding_location == location,
                KnowledgeChunk.topic == topic,
                distance <= 1 - minimum,
            )
            .order_by(distance, KnowledgeChunk.id)
            .limit(3)
        ).all()
        return [self.fact(chunk, doc, 1 - float(dist)) for chunk, doc, dist in rows]

    def chunks(self, document_id):
        return self.session.scalars(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id)
            .order_by(KnowledgeChunk.topic)
        ).all()

    @staticmethod
    def fact(chunk, document, similarity=1.0):
        return RetrievedFact(
            id=str(chunk.id),
            topic=chunk.topic,
            text=chunk.body,
            source=document.source,
            content_version=document.content_version,
            similarity=similarity,
        )

    def isolation_probe(self, tenant_id, vectors, *, model, location, minimum):
        """Exercise the real retrieval filter with foreign vectors; read-only and bounded."""
        self.session.execute(text("SET LOCAL statement_timeout = '2s'"))
        probes = violations = 0
        for topic, vector in list(vectors)[:5]:
            facts = self.retrieve(
                tenant_id, topic, vector, model=model, location=location, minimum=minimum
            )
            probes += 1
            ids = [fact.id for fact in facts]
            if ids:
                ownership = (
                    self.session.execute(
                        select(KnowledgeDocument.tenant_id)
                        .join(KnowledgeChunk, KnowledgeChunk.document_id == KnowledgeDocument.id)
                        .where(KnowledgeChunk.id.in_(ids))
                    )
                    .scalars()
                    .all()
                )
                violations += sum(owner != tenant_id for owner in ownership)
        return {"probes": probes, "violations": violations}

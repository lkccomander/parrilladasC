from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, false, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from parrilladas.db.base import Base, Record


class AssistantPreference(Base):
    __tablename__ = "assistant_preferences"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    natural_language_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    advisor_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    advisor_name: Mapped[str | None] = mapped_column(String(80))
    advisor_phone: Mapped[str | None] = mapped_column(String(16))
    advisor_template: Mapped[str | None] = mapped_column(String(100))
    advisor_language: Mapped[str | None] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))


class KnowledgeDocument(Record, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        Index(
            "uq_knowledge_active_source",
            "tenant_id",
            "source",
            unique=True,
            postgresql_where=text("active"),
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(120))
    content_version: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    embedding_model: Mapped[str] = mapped_column(String(80))
    embedding_location: Mapped[str] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean)
    catalog: Mapped[dict] = mapped_column(JSONB)


class KnowledgeChunk(Record, Base):
    __tablename__ = "knowledge_chunks"

    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    topic: Mapped[str] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(768))

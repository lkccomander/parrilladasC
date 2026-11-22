"""Privacy-preserving retrieval traces; intentionally no prompt/response columns."""

from uuid import UUID

from sqlalchemy import CheckConstraint, Float, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from parrilladas.db.base import Base, Record


class RagQueryTrace(Record, Base):
    __tablename__ = "rag_query_traces"
    __table_args__ = (
        Index("ix_rag_query_traces_tenant_created", "tenant_id", "created_at"),
        Index("ix_rag_query_traces_trace_id", "trace_id"),
        CheckConstraint("total_ms >= 0 AND used_count >= 0", name="measurements_nonnegative"),
        CheckConstraint("kind IN ('online', 'eval')", name="valid_kind"),
    )
    tenant_id: Mapped[str] = mapped_column(String(64))
    trace_id: Mapped[UUID] = mapped_column()
    kind: Mapped[str] = mapped_column(String(12))
    query_hash: Mapped[str] = mapped_column(String(64))
    embedding_model: Mapped[str] = mapped_column(String(120))
    embedding_dim: Mapped[int] = mapped_column(Integer)
    embed_ms: Mapped[int | None] = mapped_column(Integer)
    search_ms: Mapped[int | None] = mapped_column(Integer)
    total_ms: Mapped[int] = mapped_column(Integer)
    top_k: Mapped[int] = mapped_column(Integer)
    score_threshold: Mapped[float] = mapped_column(Float)
    results: Mapped[list[dict]] = mapped_column(JSONB)
    used_count: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(24))
    decision_reason: Mapped[str] = mapped_column(String(32))
    index_mode: Mapped[str] = mapped_column(String(12))
    unsupported_amounts: Mapped[int | None] = mapped_column(Integer)

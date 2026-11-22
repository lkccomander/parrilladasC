"""Durable synthetic evaluations, isolated from customer messages."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from parrilladas.db.base import Base, Record


class RagEvalSet(Record, Base):
    __tablename__ = "rag_eval_sets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", "version"),
        UniqueConstraint("id", "tenant_id"),
        CheckConstraint("version > 0", name="version_positive"),
    )
    tenant_id: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))


class RagEvalCase(Record, Base):
    __tablename__ = "rag_eval_cases"
    __table_args__ = (
        ForeignKeyConstraint(
            ["set_id", "tenant_id"], ["rag_eval_sets.id", "rag_eval_sets.tenant_id"]
        ),
        UniqueConstraint("id", "set_id", "tenant_id"),
        UniqueConstraint("set_id", "position"),
    )
    tenant_id: Mapped[str] = mapped_column(String(64))
    set_id: Mapped[UUID] = mapped_column()
    position: Mapped[int] = mapped_column(Integer)
    question: Mapped[str] = mapped_column(Text)
    topic: Mapped[str] = mapped_column(String(32))
    language: Mapped[str] = mapped_column(String(8))
    expected_chunk_ids: Mapped[list] = mapped_column(JSONB)
    expected_source_ids: Mapped[list] = mapped_column(JSONB)
    expected_action: Mapped[str | None] = mapped_column(String(24))


class RagEvalRun(Record, Base):
    __tablename__ = "rag_eval_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["set_id", "tenant_id"], ["rag_eval_sets.id", "rag_eval_sets.tenant_id"]
        ),
        UniqueConstraint("id", "set_id", "tenant_id"),
        Index("ix_rag_eval_runs_tenant_created", "tenant_id", "created_at"),
        Index(
            "uq_rag_eval_pending_tenant",
            "tenant_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        CheckConstraint("status IN ('queued','running','completed','failed')", name="valid_status"),
        CheckConstraint("model_calls >= 0 AND completed_cases >= 0", name="nonnegative_counts"),
    )
    tenant_id: Mapped[str] = mapped_column(String(64))
    set_id: Mapped[UUID] = mapped_column()
    status: Mapped[str] = mapped_column(String(16))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    case_count: Mapped[int] = mapped_column(Integer)
    completed_cases: Mapped[int] = mapped_column(Integer, default=0)
    model_calls: Mapped[int] = mapped_column(Integer, default=0)
    error_kind: Mapped[str | None] = mapped_column(String(32))
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)


class RagEvalCaseResult(Record, Base):
    __tablename__ = "rag_eval_case_results"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "set_id", "tenant_id"],
            ["rag_eval_runs.id", "rag_eval_runs.set_id", "rag_eval_runs.tenant_id"],
        ),
        ForeignKeyConstraint(
            ["case_id", "set_id", "tenant_id"],
            ["rag_eval_cases.id", "rag_eval_cases.set_id", "rag_eval_cases.tenant_id"],
        ),
        UniqueConstraint("run_id", "case_id"),
        CheckConstraint("duration_ms >= 0", name="duration_nonnegative"),
    )
    tenant_id: Mapped[str] = mapped_column(String(64))
    set_id: Mapped[UUID] = mapped_column()
    run_id: Mapped[UUID] = mapped_column()
    case_id: Mapped[UUID] = mapped_column()
    retrieved: Mapped[list] = mapped_column(JSONB)
    selected_ids: Mapped[list] = mapped_column(JSONB)
    answer_text: Mapped[str | None] = mapped_column(Text)
    actual_action: Mapped[str] = mapped_column(String(24))
    duration_ms: Mapped[int] = mapped_column(Integer)
    metrics: Mapped[dict] = mapped_column(JSONB)
    error_kind: Mapped[str | None] = mapped_column(String(32))

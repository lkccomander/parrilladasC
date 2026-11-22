"""Persistent monitoring findings; no customer content or external notifications."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from parrilladas.db.base import Base, Record


class RagAlert(Record, Base):
    __tablename__ = "rag_alerts"
    __table_args__ = (
        Index("ix_rag_alerts_tenant_created", "tenant_id", "created_at"),
        Index(
            "uq_rag_alert_open",
            "tenant_id",
            "rule_key",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
        ),
        CheckConstraint("severity IN ('watch','breach')", name="severity_allowed"),
    )
    tenant_id: Mapped[str] = mapped_column(String(64))
    rule_key: Mapped[str] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(16))
    message: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict] = mapped_column(JSONB)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RagProbeRun(Record, Base):
    __tablename__ = "rag_probe_runs"
    __table_args__ = (
        Index("ix_rag_probe_runs_tenant_created", "tenant_id", "created_at"),
        CheckConstraint("probes >= 0 AND violations >= 0", name="counts_nonnegative"),
    )
    tenant_id: Mapped[str] = mapped_column(String(64))
    probes: Mapped[int] = mapped_column(Integer)
    violations: Mapped[int] = mapped_column(Integer)


class RagIndexCheck(Record, Base):
    __tablename__ = "rag_index_checks"
    __table_args__ = (Index("ix_rag_index_checks_tenant_created", "tenant_id", "created_at"),)
    tenant_id: Mapped[str] = mapped_column(String(64))
    index_name: Mapped[str] = mapped_column(String(128))
    ef_search: Mapped[int | None] = mapped_column(Integer)
    recall_vs_exact: Mapped[float] = mapped_column(Float)
    p95_ms: Mapped[int] = mapped_column(Integer)
    sample_size: Mapped[int] = mapped_column(Integer)

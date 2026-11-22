"""RAG monitoring alerts, isolation probes and bounded ANN checks.

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    def common():
        return [
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("tenant_id", sa.String(64), nullable=False),
        ]

    op.create_table(
        "rag_alerts",
        *common(),
        sa.Column("rule_key", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("severity IN ('watch','breach')", name="ck_rag_alerts_severity_allowed"),
        sa.PrimaryKeyConstraint("id", name="pk_rag_alerts"),
    )
    op.create_index(
        "uq_rag_alert_open",
        "rag_alerts",
        ["tenant_id", "rule_key"],
        unique=True,
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.create_table(
        "rag_probe_runs",
        *common(),
        sa.Column("probes", sa.Integer(), nullable=False),
        sa.Column("violations", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "probes >= 0 AND violations >= 0", name="ck_rag_probe_runs_counts_nonnegative"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rag_probe_runs"),
    )
    op.create_table(
        "rag_index_checks",
        *common(),
        sa.Column("index_name", sa.String(128), nullable=False),
        sa.Column("ef_search", sa.Integer()),
        sa.Column("recall_vs_exact", sa.Float(), nullable=False),
        sa.Column("p95_ms", sa.Integer(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rag_index_checks"),
    )
    for table in ("rag_alerts", "rag_probe_runs", "rag_index_checks"):
        op.create_index(f"ix_{table}_tenant_created", table, ["tenant_id", "created_at"])


def downgrade():
    for table in ("rag_index_checks", "rag_probe_runs", "rag_alerts"):
        op.drop_table(table)

"""Durable curated RAG evaluations, tenant-enforced foreign keys.

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def record_columns():
    return [
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade():
    op.create_table(
        "rag_eval_sets",
        *record_columns(),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", "version"),
        sa.UniqueConstraint("id", "tenant_id"),
        sa.CheckConstraint("version > 0", name="ck_rag_eval_sets_version_positive"),
    )
    op.create_table(
        "rag_eval_cases",
        *record_columns(),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("set_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(32), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("expected_chunk_ids", pg.JSONB(), nullable=False),
        sa.Column("expected_source_ids", pg.JSONB(), nullable=False),
        sa.Column("expected_action", sa.String(24)),
        sa.ForeignKeyConstraint(
            ["set_id", "tenant_id"], ["rag_eval_sets.id", "rag_eval_sets.tenant_id"]
        ),
        sa.UniqueConstraint("id", "set_id", "tenant_id"),
        sa.UniqueConstraint("set_id", "position"),
    )
    op.create_table(
        "rag_eval_runs",
        *record_columns(),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("set_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("case_count", sa.Integer(), nullable=False),
        sa.Column("completed_cases", sa.Integer(), nullable=False),
        sa.Column("model_calls", sa.Integer(), nullable=False),
        sa.Column("error_kind", sa.String(32)),
        sa.Column("metrics", pg.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["set_id", "tenant_id"], ["rag_eval_sets.id", "rag_eval_sets.tenant_id"]
        ),
        sa.UniqueConstraint("id", "set_id", "tenant_id"),
        sa.CheckConstraint(
            "status IN ('queued','running','completed','failed')",
            name="ck_rag_eval_runs_valid_status",
        ),
        sa.CheckConstraint(
            "model_calls >= 0 AND completed_cases >= 0",
            name="ck_rag_eval_runs_nonnegative_counts",
        ),
    )
    op.create_index("ix_rag_eval_runs_tenant_created", "rag_eval_runs", ["tenant_id", "created_at"])
    op.create_index(
        "uq_rag_eval_pending_tenant",
        "rag_eval_runs",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_table(
        "rag_eval_case_results",
        *record_columns(),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("set_id", sa.UUID(), nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("retrieved", pg.JSONB(), nullable=False),
        sa.Column("selected_ids", pg.JSONB(), nullable=False),
        sa.Column("answer_text", sa.Text()),
        sa.Column("actual_action", sa.String(24), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("metrics", pg.JSONB(), nullable=False),
        sa.Column("error_kind", sa.String(32)),
        sa.ForeignKeyConstraint(
            ["run_id", "set_id", "tenant_id"],
            ["rag_eval_runs.id", "rag_eval_runs.set_id", "rag_eval_runs.tenant_id"],
        ),
        sa.ForeignKeyConstraint(
            ["case_id", "set_id", "tenant_id"],
            ["rag_eval_cases.id", "rag_eval_cases.set_id", "rag_eval_cases.tenant_id"],
        ),
        sa.UniqueConstraint("run_id", "case_id"),
        sa.CheckConstraint(
            "duration_ms >= 0", name="ck_rag_eval_case_results_duration_nonnegative"
        ),
    )


def downgrade():
    for table in ("rag_eval_case_results", "rag_eval_runs", "rag_eval_cases", "rag_eval_sets"):
        op.drop_table(table)

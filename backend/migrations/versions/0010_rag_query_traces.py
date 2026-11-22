"""Privacy-preserving tenant-scoped retrieval traces.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rag_query_traces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("query_hash", sa.String(64), nullable=False),
        sa.Column("embedding_model", sa.String(120), nullable=False),
        sa.Column("embedding_dim", sa.Integer(), nullable=False),
        sa.Column("embed_ms", sa.Integer()),
        sa.Column("search_ms", sa.Integer()),
        sa.Column("total_ms", sa.Integer(), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("score_threshold", sa.Float(), nullable=False),
        sa.Column("results", JSONB(), nullable=False),
        sa.Column("used_count", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("decision_reason", sa.String(32), nullable=False),
        sa.Column("index_mode", sa.String(12), nullable=False),
        sa.Column("unsupported_amounts", sa.Integer()),
        sa.CheckConstraint(
            "total_ms >= 0 AND used_count >= 0",
            name="ck_rag_query_traces_measurements_nonnegative",
        ),
        sa.CheckConstraint("kind IN ('online', 'eval')", name="ck_rag_query_traces_valid_kind"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rag_query_traces_tenant_created", "rag_query_traces", ["tenant_id", "created_at"]
    )
    op.create_index("ix_rag_query_traces_trace_id", "rag_query_traces", ["trace_id"])


def downgrade():
    op.drop_table("rag_query_traces")

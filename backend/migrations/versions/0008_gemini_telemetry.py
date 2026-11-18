"""Numeric Gemini telemetry, without customer content or identifiers.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gemini_telemetry",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(32), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("is_model_call", sa.Boolean(), nullable=False),
        sa.Column("model", sa.String(120)),
        sa.Column("region", sa.String(40)),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error_kind", sa.String(32)),
        sa.Column("http_status", sa.Integer()),
        sa.Column("finish_reason", sa.String(40)),
        *[
            sa.Column(name, sa.BigInteger())
            for name in (
                "input_tokens",
                "output_tokens",
                "thinking_tokens",
                "cached_tokens",
                "tool_tokens",
                "total_tokens",
                "billable_characters",
            )
        ],
        sa.Column("reason", sa.String(32)),
        sa.Column("result_count", sa.Integer()),
        sa.Column("selected_count", sa.Integer()),
        sa.Column("similarity", sa.Float()),
        sa.CheckConstraint("duration_ms >= 0", name="ck_gemini_telemetry_duration_nonnegative"),
        sa.PrimaryKeyConstraint("id", name="pk_gemini_telemetry"),
    )
    op.create_index(
        "ix_gemini_telemetry_tenant_created", "gemini_telemetry", ["tenant_id", "created_at"]
    )


def downgrade():
    op.drop_table("gemini_telemetry")

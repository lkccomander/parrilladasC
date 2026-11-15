"""Persist tenant-scoped assistant preferences, disabled by default.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_preferences",
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column(
            "natural_language_enabled", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["accounts.id"], name="fk_assistant_preferences_updated_by_accounts"
        ),
        sa.PrimaryKeyConstraint("tenant_id", name="pk_assistant_preferences"),
    )


def downgrade() -> None:
    op.drop_table("assistant_preferences")

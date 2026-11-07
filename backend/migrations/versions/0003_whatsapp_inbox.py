"""Durable, deduplicated WhatsApp webhook inbox.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_inbox_events",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_key", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("event_key", name="uq_whatsapp_inbox_events_event_key"),
    )
    op.create_index(
        "ix_whatsapp_inbox_events_processed_at", "whatsapp_inbox_events", ["processed_at"]
    )


def downgrade() -> None:
    op.drop_table("whatsapp_inbox_events")

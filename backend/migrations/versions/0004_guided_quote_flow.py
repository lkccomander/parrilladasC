"""Persist guided WhatsApp flow data and outbound idempotency.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("flow_data", postgresql.JSONB()))
    op.create_unique_constraint(
        "uq_conversations_whatsapp_number", "conversations", ["whatsapp_number"]
    )
    op.add_column("messages", sa.Column("event_key", sa.String(64)))
    op.create_unique_constraint("uq_messages_event_key", "messages", ["event_key"])


def downgrade() -> None:
    op.drop_constraint("uq_messages_event_key", "messages", type_="unique")
    op.drop_column("messages", "event_key")
    op.drop_constraint("uq_conversations_whatsapp_number", "conversations", type_="unique")
    op.drop_column("conversations", "flow_data")

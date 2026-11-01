"""Initial accounts, leads, conversations, quotes and internal reminders.

Revision ID: 0001
Revises: None
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def record_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "accounts",
        *record_columns(),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("email", name="uq_accounts_email"),
    )
    op.create_table(
        "leads",
        *record_columns(),
        sa.Column("contact_name", sa.String(120)),
        sa.Column("whatsapp_number", sa.String(32), nullable=False),
        sa.Column("event_date", sa.Date()),
        sa.Column("time_preference", sa.String(120)),
        sa.Column("location", sa.Text()),
        sa.Column("guest_count", sa.Integer()),
        sa.Column("service_type", sa.String(120)),
        sa.Column("requirements", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("assigned_account_id", sa.Uuid(), sa.ForeignKey("accounts.id")),
        sa.CheckConstraint("guest_count > 0", name="positive_guest_count"),
    )
    op.create_index("ix_leads_whatsapp_number", "leads", ["whatsapp_number"])
    op.create_index("ix_leads_status", "leads", ["status"])
    op.create_table(
        "conversations",
        *record_columns(),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id")),
        sa.Column("whatsapp_number", sa.String(32), nullable=False),
        sa.Column("bot_paused", sa.Boolean(), nullable=False),
        sa.Column("flow_step", sa.String(64), nullable=False),
    )
    op.create_index("ix_conversations_lead_id", "conversations", ["lead_id"])
    op.create_index("ix_conversations_whatsapp_number", "conversations", ["whatsapp_number"])
    op.create_table(
        "messages",
        *record_columns(),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id"), nullable=False),
        sa.Column("external_message_id", sa.String(255)),
        sa.Column("direction", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("delivery_status", sa.String(32), nullable=False),
        sa.UniqueConstraint("external_message_id", name="uq_messages_external_message_id"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])
    op.create_table(
        "quotes",
        *record_columns(),
        sa.Column("lead_id", sa.Uuid(), sa.ForeignKey("leads.id"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("total", sa.Numeric(12, 2)),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("approved_version", sa.Integer()),
        sa.Column("approved_by_id", sa.Uuid(), sa.ForeignKey("accounts.id")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("total >= 0", name="nonnegative_total"),
        sa.CheckConstraint("version > 0", name="positive_version"),
    )
    op.create_index("ix_quotes_lead_id", "quotes", ["lead_id"])
    op.create_table(
        "reminders",
        *record_columns(),
        sa.Column("quote_id", sa.Uuid(), sa.ForeignKey("quotes.id"), nullable=False),
        sa.Column("assigned_account_id", sa.Uuid(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("quote_id", name="uq_reminders_quote_id"),
    )
    op.create_index("ix_reminders_assigned_account_id", "reminders", ["assigned_account_id"])
    op.create_index("ix_reminders_due_at", "reminders", ["due_at"])


def downgrade() -> None:
    for table in ("reminders", "quotes", "messages", "conversations", "leads", "accounts"):
        op.drop_table(table)

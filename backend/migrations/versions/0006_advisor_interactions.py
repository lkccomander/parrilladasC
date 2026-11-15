"""Separate interactions and persist advisor notification configuration/outbox.

Revision ID: 0006
Revises: 0005

Additive upgrade: existing messages retain nullable interaction/recipient fields;
legacy paused/submitted conversations and stored preferences are not rewritten.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assistant_preferences",
        sa.Column("advisor_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    for name, length in [
        ("advisor_name", 80),
        ("advisor_phone", 16),
        ("advisor_template", 100),
        ("advisor_language", 16),
    ]:
        op.add_column("assistant_preferences", sa.Column(name, sa.String(length), nullable=True))
    op.create_table(
        "conversation_interactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(40), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_conversation_interactions_conversation_id_conversations",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversation_interactions"),
        sa.UniqueConstraint("reference", name="uq_conversation_interactions_reference"),
    )
    op.create_index(
        "ix_conversation_interactions_conversation_id",
        "conversation_interactions",
        ["conversation_id"],
    )
    op.create_index(
        "uq_interaction_active_conversation",
        "conversation_interactions",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    for column in [
        sa.Column("interaction_id", sa.Uuid(), nullable=True),
        sa.Column("recipient", sa.String(32), nullable=True),
        sa.Column("purpose", sa.String(32), nullable=False, server_default="customer"),
        sa.Column("depends_on_id", sa.Uuid(), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
    ]:
        op.add_column("messages", column)
    op.create_foreign_key(
        "fk_messages_interaction_id_conversation_interactions",
        "messages",
        "conversation_interactions",
        ["interaction_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_messages_depends_on_id_messages", "messages", "messages", ["depends_on_id"], ["id"]
    )
    op.create_index("ix_messages_interaction_id", "messages", ["interaction_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_interaction_id", table_name="messages")
    op.drop_constraint("fk_messages_depends_on_id_messages", "messages", type_="foreignkey")
    op.drop_constraint(
        "fk_messages_interaction_id_conversation_interactions", "messages", type_="foreignkey"
    )
    for name in ["attempted_at", "depends_on_id", "purpose", "recipient", "interaction_id"]:
        op.drop_column("messages", name)
    op.drop_table("conversation_interactions")
    for name in [
        "advisor_language",
        "advisor_template",
        "advisor_phone",
        "advisor_name",
        "advisor_enabled",
    ]:
        op.drop_column("assistant_preferences", name)

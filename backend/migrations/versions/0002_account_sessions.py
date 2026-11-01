"""Persistent sessions and login throttling, with no default credentials.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id")),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
    )
    op.create_index("ix_auth_sessions_account_id", "auth_sessions", ["account_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "login_attempts",
        sa.Column("key", sa.String(64), nullable=False, primary_key=True),
        sa.Column("window_started", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
    )
    op.create_index("ix_login_attempts_window_started", "login_attempts", ["window_started"])


def downgrade() -> None:
    op.drop_table("login_attempts")
    op.drop_table("auth_sessions")

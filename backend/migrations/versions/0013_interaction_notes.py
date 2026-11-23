"""Add operator notes to conversation interactions.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("conversation_interactions", sa.Column("notes", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("conversation_interactions", "notes")

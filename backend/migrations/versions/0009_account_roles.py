"""Multiple account roles and explicit Dev access; preserve existing privileges.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

ROLE_CHECK = (
    "cardinality(roles) BETWEEN 1 AND 3 AND "
    "roles <@ ARRAY['admin','sales','dev']::varchar[] AND "
    "array_position(roles, NULL) IS NULL AND role = ANY(roles)"
)


def upgrade():
    op.add_column("accounts", sa.Column("roles", postgresql.ARRAY(sa.String(20)), nullable=True))
    op.execute("UPDATE accounts SET roles = ARRAY[role]::varchar[]")
    op.alter_column("accounts", "roles", nullable=False)
    op.create_check_constraint("valid_account_roles", "accounts", ROLE_CHECK)
    # Existing sessions reload roles from the database; nobody receives Dev implicitly.


def downgrade():
    # The previous application has one role; Dev retains its inherited Admin access.
    op.drop_constraint(op.f("ck_accounts_valid_account_roles"), "accounts", type_="check")
    op.execute(
        "UPDATE accounts SET role = CASE "
        "WHEN roles && ARRAY['admin','dev']::varchar[] THEN 'admin' ELSE 'sales' END"
    )
    op.drop_column("accounts", "roles")

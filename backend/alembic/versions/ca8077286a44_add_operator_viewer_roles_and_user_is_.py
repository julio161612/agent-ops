"""add operator viewer roles and user is_active

Revision ID: ca8077286a44
Revises: 496107c9ac1b
Create Date: 2026-08-16 18:00:56.265386

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ca8077286a44'
down_revision: Union[str, None] = '496107c9ac1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Phase 8 replaces the 2-role MEMBER/ADMIN model with a 3-tier
    # VIEWER/OPERATOR/ADMIN hierarchy. Existing MEMBER rows become OPERATOR —
    # the closest match to what MEMBER already did in practice (claiming and
    # responding to escalations, day-to-day agent/config work), not the more
    # restrictive VIEWER.
    op.execute("ALTER TYPE user_role RENAME TO user_role_old")
    new_role_enum = postgresql.ENUM("VIEWER", "OPERATOR", "ADMIN", name="user_role")
    new_role_enum.create(op.get_bind())
    op.execute(
        "ALTER TABLE users ALTER COLUMN role TYPE user_role USING "
        "(CASE role::text WHEN 'MEMBER' THEN 'OPERATOR' ELSE role::text END)::user_role"
    )
    op.execute("DROP TYPE user_role_old")

    op.add_column(
        "users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.alter_column("users", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "is_active")

    op.execute("ALTER TYPE user_role RENAME TO user_role_new")
    old_role_enum = postgresql.ENUM("ADMIN", "MEMBER", name="user_role")
    old_role_enum.create(op.get_bind())
    op.execute(
        "ALTER TABLE users ALTER COLUMN role TYPE user_role USING "
        "(CASE role::text WHEN 'OPERATOR' THEN 'MEMBER' WHEN 'VIEWER' THEN 'MEMBER' "
        "ELSE role::text END)::user_role"
    )
    op.execute("DROP TYPE user_role_new")

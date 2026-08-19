"""add plans tenant subscriptions message count

Revision ID: 9e921bb08c50
Revises: 372b91d71b07
Create Date: 2026-08-17 17:50:54.249154

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9e921bb08c50'
down_revision: Union[str, None] = '372b91d71b07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Keep this migration's seed data self-contained (not imported from
# app.core.plan_seed) — a migration must keep working even if that module's
# contents change later; see every other migration in this project for the
# same "migrations don't import application code" convention.
_PLAN_SEED_DATA = [
    {
        "name": "Free",
        "slug": "free",
        "monthly_price_usd": "0.00",
        "included_messages_per_month": 100,
        "included_active_agents": 1,
        "included_users": 1,
        "included_ai_cost_usd": "5.00",
        "max_messages_per_minute": 10,
        "overage_price_per_1000_messages_usd": None,
        "is_active": True,
    },
    {
        "name": "Starter",
        "slug": "starter",
        "monthly_price_usd": "29.00",
        "included_messages_per_month": 1000,
        "included_active_agents": 3,
        "included_users": 3,
        "included_ai_cost_usd": "15.00",
        "max_messages_per_minute": 30,
        "overage_price_per_1000_messages_usd": "8.00",
        "is_active": True,
    },
    {
        "name": "Growth",
        "slug": "growth",
        "monthly_price_usd": "99.00",
        "included_messages_per_month": 5000,
        "included_active_agents": 10,
        "included_users": 10,
        "included_ai_cost_usd": "75.00",
        "max_messages_per_minute": 60,
        "overage_price_per_1000_messages_usd": "6.00",
        "is_active": True,
    },
    {
        "name": "Enterprise",
        "slug": "enterprise",
        "monthly_price_usd": "499.00",
        "included_messages_per_month": None,
        "included_active_agents": None,
        "included_users": None,
        "included_ai_cost_usd": None,
        "max_messages_per_minute": 300,
        "overage_price_per_1000_messages_usd": None,
        "is_active": True,
    },
]


def upgrade() -> None:
    plans_table = op.create_table(
        'plans',
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('slug', sa.String(length=50), nullable=False),
        sa.Column('monthly_price_usd', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('included_messages_per_month', sa.Integer(), nullable=True),
        sa.Column('included_active_agents', sa.Integer(), nullable=True),
        sa.Column('included_users', sa.Integer(), nullable=True),
        sa.Column('included_ai_cost_usd', sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column('max_messages_per_minute', sa.Integer(), nullable=False),
        sa.Column(
            'overage_price_per_1000_messages_usd', sa.Numeric(precision=10, scale=4), nullable=True
        ),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_plans_slug'), 'plans', ['slug'], unique=True)

    op.bulk_insert(
        plans_table,
        [{**row, "id": uuid.uuid4()} for row in _PLAN_SEED_DATA],
    )

    op.create_table(
        'tenant_subscriptions',
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('plan_id', sa.UUID(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('ACTIVE', 'CANCELED', 'PAST_DUE', name='subscription_status'),
            nullable=False,
        ),
        sa.Column(
            'started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column('overage_enabled', sa.Boolean(), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False
        ),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_tenant_subscriptions_plan_id'), 'tenant_subscriptions', ['plan_id'], unique=False
    )
    op.create_index(
        op.f('ix_tenant_subscriptions_tenant_id'), 'tenant_subscriptions', ['tenant_id'], unique=True
    )

    # Every tenant that predates Phase 10 is enrolled on Free — the safest
    # default (no accidental jump to a paid plan's higher limits).
    op.execute(
        """
        INSERT INTO tenant_subscriptions (id, tenant_id, plan_id, status, overage_enabled)
        SELECT gen_random_uuid(), t.id, (SELECT id FROM plans WHERE slug = 'free'), 'ACTIVE', false
        FROM tenants t
        """
    )

    op.add_column(
        'tenant_limits',
        sa.Column(
            'current_month_message_count', sa.Integer(), nullable=False, server_default='0'
        ),
    )
    op.alter_column('tenant_limits', 'current_month_message_count', server_default=None)

    op.drop_column('tenants', 'plan')
    # tenant_plan was created in Phase 1 for a column that's now gone —
    # nothing else in the schema uses it.
    sa.Enum(name='tenant_plan').drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    tenant_plan_enum = sa.Enum('FREE', 'STARTER', 'PRO', 'ENTERPRISE', name='tenant_plan')
    tenant_plan_enum.create(op.get_bind())
    op.add_column(
        'tenants',
        sa.Column(
            'plan', tenant_plan_enum, nullable=False, server_default='FREE', autoincrement=False
        ),
    )
    op.alter_column('tenants', 'plan', server_default=None)

    op.drop_column('tenant_limits', 'current_month_message_count')

    op.drop_index(op.f('ix_tenant_subscriptions_tenant_id'), table_name='tenant_subscriptions')
    op.drop_index(op.f('ix_tenant_subscriptions_plan_id'), table_name='tenant_subscriptions')
    op.drop_table('tenant_subscriptions')
    sa.Enum(name='subscription_status').drop(op.get_bind(), checkfirst=True)

    op.drop_index(op.f('ix_plans_slug'), table_name='plans')
    op.drop_table('plans')

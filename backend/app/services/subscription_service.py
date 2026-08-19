import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PlanNotActiveError, PlanNotFoundError
from app.models.plan import Plan
from app.models.tenant_limits import TenantLimits
from app.models.tenant_subscription import SubscriptionStatus, TenantSubscription
from app.services import cost_service

_DEFAULT_PLAN_SLUG = "free"


async def get_plan(db: AsyncSession, *, plan_id: uuid.UUID) -> Plan:
    plan = await db.get(Plan, plan_id)
    if plan is None:
        raise PlanNotFoundError(str(plan_id))
    return plan


async def get_plan_by_slug(db: AsyncSession, *, slug: str) -> Plan:
    result = await db.execute(select(Plan).where(Plan.slug == slug))
    plan = result.scalar_one_or_none()
    if plan is None:
        raise PlanNotFoundError(slug)
    return plan


async def list_plans(db: AsyncSession, *, active_only: bool = True) -> list[Plan]:
    stmt = select(Plan).order_by(Plan.monthly_price_usd)
    if active_only:
        stmt = stmt.where(Plan.is_active.is_(True))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_or_create_subscription(
    db: AsyncSession, *, tenant_id: uuid.UUID
) -> TenantSubscription:
    """Every tenant has exactly one subscription row — created lazily here on
    the default (Free) plan for any tenant that doesn't have one yet, same
    pattern as cost_service.get_or_create_tenant_limits.
    """
    result = await db.execute(
        select(TenantSubscription).where(TenantSubscription.tenant_id == tenant_id)
    )
    subscription = result.scalar_one_or_none()
    if subscription is not None:
        return subscription

    free_plan = await get_plan_by_slug(db, slug=_DEFAULT_PLAN_SLUG)
    subscription = TenantSubscription(tenant_id=tenant_id, plan_id=free_plan.id)
    db.add(subscription)
    await db.flush()
    return subscription


async def change_plan(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    plan_id: uuid.UUID,
    overage_enabled: bool | None = None,
) -> TenantSubscription:
    """Switch a tenant's plan, effective immediately — see the Phase 10
    README/summary for why this deliberately does NOT prorate the monthly
    base charge: the new plan's limits (messages/agents/users/rate) apply to
    the very next request, but the invoice for the month this happened in
    bills whatever plan is current at *generation* time, not a day-weighted
    mix of old+new. ``overage_enabled``, if given, is updated in the same
    call — it's a tenant preference independent of which plan they're on,
    but naturally gets set alongside a plan choice in practice.
    """
    plan = await get_plan(db, plan_id=plan_id)
    if not plan.is_active:
        raise PlanNotActiveError(str(plan_id))

    subscription = await get_or_create_subscription(db, tenant_id=tenant_id)
    subscription.plan_id = plan.id
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.started_at = datetime.now(UTC)
    if overage_enabled is not None:
        subscription.overage_enabled = overage_enabled

    await db.commit()
    await db.refresh(subscription)
    return subscription


@dataclass
class EffectiveLimits:
    plan: Plan
    subscription: TenantSubscription
    messages_per_minute_limit: int
    monthly_cost_limit_usd: Decimal | None


def _tighter(a: Decimal | None, b: Decimal | None) -> Decimal | None:
    """The smaller of two optional caps, treating None as "no cap" (+inf)."""
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


async def get_effective_limits(db: AsyncSession, *, tenant_id: uuid.UUID) -> EffectiveLimits:
    """What actually gets enforced right now: the tighter of the tenant's own
    configured TenantLimits and their plan's ceiling on each dimension.

    Computed live rather than stored/migrated on plan change — an admin's
    own values never need rewriting when their plan changes, and a
    downgrade takes effect immediately without a separate migration step.
    """
    subscription = await get_or_create_subscription(db, tenant_id=tenant_id)
    plan = await get_plan(db, plan_id=subscription.plan_id)
    tenant_limits: TenantLimits = await cost_service.get_or_create_tenant_limits(
        db, tenant_id=tenant_id
    )

    return EffectiveLimits(
        plan=plan,
        subscription=subscription,
        messages_per_minute_limit=min(
            tenant_limits.messages_per_minute_limit, plan.max_messages_per_minute
        ),
        monthly_cost_limit_usd=_tighter(
            tenant_limits.monthly_cost_limit_usd, plan.included_ai_cost_usd
        ),
    )

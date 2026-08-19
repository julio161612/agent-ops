import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import TenantLimitsExceedPlanError
from app.models.tenant_limits import TenantLimits
from app.schemas.tenant_limits import TenantLimitsUpdate
from app.services import cost_service, subscription_service


async def get_limits(db: AsyncSession, *, tenant_id: uuid.UUID) -> TenantLimits:
    return await cost_service.get_or_create_tenant_limits(db, tenant_id=tenant_id)


async def update_limits(
    db: AsyncSession, *, tenant_id: uuid.UUID, payload: TenantLimitsUpdate
) -> TenantLimits:
    """An admin can tighten their own limits freely, but never configure
    something looser than their plan allows (Phase 10) — messages_per_minute
    above the plan's ceiling, or a cost cap above (or removing the cap
    entirely, when the plan itself has one below) what the plan includes.
    """
    limits = await cost_service.get_or_create_tenant_limits(db, tenant_id=tenant_id)
    updates = payload.model_dump(exclude_unset=True)

    subscription = await subscription_service.get_or_create_subscription(db, tenant_id=tenant_id)
    plan = await subscription_service.get_plan(db, plan_id=subscription.plan_id)

    requested_rate_limit = updates.get("messages_per_minute_limit")
    if requested_rate_limit is not None and requested_rate_limit > plan.max_messages_per_minute:
        raise TenantLimitsExceedPlanError(
            f"messages_per_minute_limit cannot exceed the '{plan.name}' plan's ceiling "
            f"of {plan.max_messages_per_minute}"
        )
    if "monthly_cost_limit_usd" in updates and plan.included_ai_cost_usd is not None:
        requested = updates["monthly_cost_limit_usd"]
        if requested is None or requested > plan.included_ai_cost_usd:
            raise TenantLimitsExceedPlanError(
                f"monthly_cost_limit_usd cannot exceed the '{plan.name}' plan's included "
                f"AI cost of ${plan.included_ai_cost_usd}"
            )

    for field, value in updates.items():
        setattr(limits, field, value)
    await db.commit()
    await db.refresh(limits)
    return limits

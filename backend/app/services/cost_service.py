import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import TenantCostLimitExceededError
from app.core.pricing import calculate_cost_usd
from app.models.tenant_limits import TenantLimits, current_month_str


async def get_or_create_tenant_limits(db: AsyncSession, *, tenant_id: uuid.UUID) -> TenantLimits:
    """Fetch a tenant's limits row, creating one with the platform defaults if missing.

    Normally created eagerly at registration (see auth_service), so the create
    path here only matters for tenants that predate this feature.
    """
    result = await db.execute(select(TenantLimits).where(TenantLimits.tenant_id == tenant_id))
    limits = result.scalar_one_or_none()
    if limits is None:
        limits = TenantLimits(
            tenant_id=tenant_id,
            messages_per_minute_limit=settings.DEFAULT_MESSAGES_PER_MINUTE_LIMIT,
            monthly_cost_limit_usd=(
                Decimal(str(settings.DEFAULT_MONTHLY_COST_LIMIT_USD))
                if settings.DEFAULT_MONTHLY_COST_LIMIT_USD is not None
                else None
            ),
        )
        db.add(limits)
        await db.flush()
    _roll_over_month_if_needed(limits)
    return limits


def _roll_over_month_if_needed(limits: TenantLimits) -> None:
    month = current_month_str()
    if limits.current_month != month:
        limits.current_month = month
        limits.current_month_cost_usd = Decimal("0")
        limits.current_month_message_count = 0


def raise_if_over_budget(
    *, current_month_cost_usd: Decimal, effective_monthly_cost_limit_usd: Decimal | None
) -> None:
    """Checks against ``effective_monthly_cost_limit_usd`` — since Phase 10 this
    is the tighter of the tenant's own configured cap and their plan's
    included AI cost, computed by subscription_service.get_effective_limits,
    not read directly off TenantLimits.monthly_cost_limit_usd anymore.
    """
    if (
        effective_monthly_cost_limit_usd is not None
        and current_month_cost_usd >= effective_monthly_cost_limit_usd
    ):
        raise TenantCostLimitExceededError(
            f"Monthly cost limit of ${effective_monthly_cost_limit_usd} exceeded "
            f"(spent ${current_month_cost_usd} so far this month)"
        )


async def record_usage(
    db: AsyncSession, *, tenant_id: uuid.UUID, model: str, input_tokens: int, output_tokens: int
) -> Decimal:
    """Add the USD cost of one real Anthropic call to the tenant's running monthly total.

    Called for every Anthropic call that spends tokens on the tenant's behalf —
    agent execution, the routing LLM call, and custom_llm_check guardrails —
    not just the final user-facing reply.
    """
    limits = await get_or_create_tenant_limits(db, tenant_id=tenant_id)
    cost = calculate_cost_usd(model, input_tokens, output_tokens)
    limits.current_month_cost_usd = limits.current_month_cost_usd + cost
    await db.flush()
    return cost

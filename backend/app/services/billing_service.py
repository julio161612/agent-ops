import calendar
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvoiceNotFoundError
from app.models.interaction_trace import InteractionTrace
from app.models.invoice import Invoice, InvoiceStatus
from app.models.plan import Plan
from app.services import subscription_service


def _period_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=UTC)
    last_day = calendar.monthrange(year, month)[1]
    end = datetime(year, month, last_day, 23, 59, 59, 999999, tzinfo=UTC)
    return start, end


@dataclass
class PeriodUsage:
    total_messages: int
    total_ai_cost_usd: Decimal


async def _get_period_usage(
    db: AsyncSession, *, tenant_id: uuid.UUID, year: int, month: int
) -> PeriodUsage:
    """Real usage for the period, read straight from InteractionTrace — the
    permanent record of every send_message call — not from TenantLimits'
    current-month counters, which only reflect the CURRENT calendar month and
    reset on rollover, so they can't answer "how much did October look like"
    once it's November. Uses the tenant_id+created_at index from Phase 7.
    """
    start, end = _period_bounds(year, month)
    result = await db.execute(
        select(
            func.count(InteractionTrace.id),
            func.coalesce(func.sum(InteractionTrace.cost_usd), 0),
        )
        .where(InteractionTrace.tenant_id == tenant_id)
        .where(InteractionTrace.created_at >= start)
        .where(InteractionTrace.created_at <= end)
    )
    count, cost = result.one()
    return PeriodUsage(total_messages=int(count), total_ai_cost_usd=Decimal(cost))


def _compute_overage(plan: Plan, total_messages: int) -> tuple[int, int, Decimal]:
    """Returns (included_messages_consumed, overage_messages, overage_cost_usd)."""
    if plan.included_messages_per_month is None:
        return total_messages, 0, Decimal("0")

    included = min(total_messages, plan.included_messages_per_month)
    overage_messages = total_messages - included
    if overage_messages <= 0 or plan.overage_price_per_1000_messages_usd is None:
        return included, max(overage_messages, 0), Decimal("0")

    overage_cost = (
        Decimal(overage_messages) / Decimal(1000) * plan.overage_price_per_1000_messages_usd
    ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    return included, overage_messages, overage_cost


async def get_existing_invoice(
    db: AsyncSession, *, tenant_id: uuid.UUID, year: int, month: int
) -> Invoice | None:
    result = await db.execute(
        select(Invoice)
        .where(Invoice.tenant_id == tenant_id)
        .where(Invoice.period_year == year)
        .where(Invoice.period_month == month)
    )
    return result.scalar_one_or_none()


async def generate_invoice(
    db: AsyncSession, *, tenant_id: uuid.UUID, year: int, month: int
) -> Invoice:
    """Compute and persist one tenant's invoice for one calendar month, from
    real InteractionTrace rows for that period.

    Bills whichever plan is current for the tenant AT GENERATION TIME (no
    proration — see subscription_service.change_plan) — this only matters if
    an invoice for the current, still-open month is generated on demand via
    GET-adjacent tooling before month end; the monthly batch script only ever
    targets the PREVIOUS, closed month, where "current plan" and "plan that
    was active all period" normally coincide.

    Idempotent: if an invoice already exists for this tenant+period (the
    UniqueConstraint on Invoice), it's returned as-is rather than recomputed
    or duplicated — re-running the monthly batch is always safe.
    """
    existing = await get_existing_invoice(db, tenant_id=tenant_id, year=year, month=month)
    if existing is not None:
        return existing

    subscription = await subscription_service.get_or_create_subscription(db, tenant_id=tenant_id)
    plan = await subscription_service.get_plan(db, plan_id=subscription.plan_id)
    usage = await _get_period_usage(db, tenant_id=tenant_id, year=year, month=month)

    included_messages, overage_messages, overage_cost = _compute_overage(plan, usage.total_messages)
    total_cost = plan.monthly_price_usd + overage_cost

    invoice = Invoice(
        tenant_id=tenant_id,
        period_year=year,
        period_month=month,
        plan_id=plan.id,
        plan_name_snapshot=plan.name,
        base_charge_usd=plan.monthly_price_usd,
        included_messages=included_messages,
        total_messages=usage.total_messages,
        overage_messages=overage_messages,
        overage_cost_usd=overage_cost,
        total_ai_cost_usd=usage.total_ai_cost_usd,
        total_cost_usd=total_cost,
        status=InvoiceStatus.ISSUED,
        issued_at=datetime.now(UTC),
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


async def get_invoice(db: AsyncSession, *, tenant_id: uuid.UUID, invoice_id: uuid.UUID) -> Invoice:
    result = await db.execute(
        select(Invoice).where(Invoice.tenant_id == tenant_id).where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise InvoiceNotFoundError(str(invoice_id))
    return invoice


async def list_invoices(db: AsyncSession, *, tenant_id: uuid.UUID) -> list[Invoice]:
    result = await db.execute(
        select(Invoice)
        .where(Invoice.tenant_id == tenant_id)
        .order_by(Invoice.period_year.desc(), Invoice.period_month.desc())
    )
    return list(result.scalars().all())


@dataclass
class CurrentUsage:
    plan: Plan
    period_year: int
    period_month: int
    messages_used: int
    included_messages: int | None
    overage_messages: int
    overage_cost_usd: Decimal
    ai_cost_usd: Decimal
    included_ai_cost_usd: Decimal | None
    overage_enabled: bool


async def get_current_usage(db: AsyncSession, *, tenant_id: uuid.UUID) -> CurrentUsage:
    """Live, real-time view of "how much have I used this month vs my plan" —
    for a dashboard. Reads the current (still-open) month from InteractionTrace,
    same source of truth generate_invoice uses for closed months, so the
    numbers a tenant sees mid-month match what their eventual invoice will say.
    """
    now = datetime.now(UTC)
    subscription = await subscription_service.get_or_create_subscription(db, tenant_id=tenant_id)
    plan = await subscription_service.get_plan(db, plan_id=subscription.plan_id)
    usage = await _get_period_usage(db, tenant_id=tenant_id, year=now.year, month=now.month)

    _, overage_messages, overage_cost = _compute_overage(plan, usage.total_messages)

    return CurrentUsage(
        plan=plan,
        period_year=now.year,
        period_month=now.month,
        messages_used=usage.total_messages,
        included_messages=plan.included_messages_per_month,
        overage_messages=overage_messages,
        overage_cost_usd=overage_cost,
        ai_cost_usd=usage.total_ai_cost_usd,
        included_ai_cost_usd=plan.included_ai_cost_usd,
        overage_enabled=subscription.overage_enabled,
    )

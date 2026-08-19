from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class SubscriptionStatus(enum.StrEnum):
    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"  # simulated non-payment — no real billing provider behind this


class TenantSubscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant's current plan subscription — one row per tenant (like
    TenantLimits/TenantIntegrations), not a history table.

    Kept as its own table rather than columns on Tenant (see Phase 10
    README/summary for the full reasoning): a subscription has its own
    lifecycle (status, started_at, the overage choice) that's conceptually
    separate from a tenant's core identity, and this mirrors the existing
    one-row-per-tenant pattern already used for limits/integrations instead
    of growing Tenant into a god-table. Superseldes the decorative
    ``Tenant.plan`` enum from Phase 1, which was never actually enforced
    anywhere — real plan enforcement is what this phase adds.

    ``started_at`` resets to "now" on every plan change (see
    subscription_service.change_plan) — it means "since when has the
    CURRENT plan applied", not "since when has this tenant been a
    customer" (Agent Ops doesn't track that separately yet).

    ``overage_enabled`` is the tenant's own choice of what happens when they
    exceed their plan's included monthly messages: ``False`` (default) blocks
    new messages with a clear "upgrade your plan" error; ``True`` lets them
    keep going and bills the excess at the plan's overage rate. Enforced in
    AgentExecutionService._enforce_budget.
    """

    __tablename__ = "tenant_subscriptions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status"),
        nullable=False,
        default=SubscriptionStatus.ACTIVE,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    overage_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

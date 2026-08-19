from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class Plan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A global subscription plan definition — the catalog every tenant
    subscribes to (see TenantSubscription), not tenant-scoped itself.

    ``included_*`` fields are the plan's monthly allowances; ``None`` means
    unlimited on that dimension (only Enterprise uses this — see the Phase 10
    seed data). ``max_messages_per_minute`` has no unlimited option even on
    Enterprise: it's a burst-protection ceiling, not a billing dimension, so
    every plan gets a concrete number.

    ``overage_price_per_1000_messages_usd`` is what a message beyond
    ``included_messages_per_month`` costs once overage is allowed for a
    tenant (see TenantSubscription.overage_enabled) — ``None`` means this
    plan doesn't sell overage at all (Free: must upgrade; Enterprise: no
    ceiling to overage past).

    ``is_active`` lets a plan be retired from new signups without deleting it
    — existing subscriptions and historical invoices keep referencing it.
    """

    __tablename__ = "plans"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    monthly_price_usd: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    included_messages_per_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    included_active_agents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    included_users: Mapped[int | None] = mapped_column(Integer, nullable=True)
    included_ai_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    max_messages_per_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    overage_price_per_1000_messages_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 4), nullable=True
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

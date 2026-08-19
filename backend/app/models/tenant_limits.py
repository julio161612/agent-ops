from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


def current_month_str() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


class TenantLimits(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-tenant rate limit / monthly cost cap configuration and running spend.

    One row per tenant (created automatically at registration — see
    auth_service.register_tenant_and_admin — and lazily by cost_service for any
    tenant that predates this table). ``current_month``/``current_month_cost_usd``/
    ``current_month_message_count`` roll over to 0 the first time a new
    calendar month is observed; there's no scheduled job doing this, it's
    checked on every read/write.

    ``messages_per_minute_limit``/``monthly_cost_limit_usd`` are a tenant's
    OWN configured values (Phase 4) — since Phase 10, the limit actually
    enforced is ``min(this value, the tenant's plan ceiling)``, computed live
    in billing_service.get_effective_limits rather than stored here, so nothing
    needs migrating when a tenant changes plans. ``current_month_message_count``
    (Phase 10) is the running counter behind the plan's included-messages
    quota — a real-time counter for the CURRENT month only, deliberately
    separate from InteractionTrace-based historical aggregates (which is what
    invoice generation reads for past, closed periods — see billing_service).
    """

    __tablename__ = "tenant_limits"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    messages_per_minute_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    monthly_cost_limit_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    current_month: Mapped[str] = mapped_column(String(7), nullable=False, default=current_month_str)
    current_month_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal("0")
    )
    current_month_message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

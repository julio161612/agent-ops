from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class InvoiceStatus(enum.StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"  # simulated — no real payment provider behind this


class Invoice(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """One simulated monthly bill for one tenant, computed from real usage
    data (InteractionTrace for the period) — see billing_service.generate_invoice.

    ``plan_name_snapshot`` denormalizes the plan's name at generation time —
    ``plan_id`` alone isn't enough for historical accuracy if a plan is later
    renamed or retired (is_active=False doesn't delete it, but a rename
    would otherwise silently rewrite old invoices' "what you were billed
    for"). ``plan_id`` itself is nullable with ON DELETE SET NULL for the
    same reason a plan should never be hard-deletable while invoices
    reference it in the first place (see Plan/TenantSubscription FKs) — this
    is defense in depth, not the primary safeguard.

    The (tenant_id, period_year, period_month) uniqueness is the idempotency
    guard the monthly generation script relies on: re-running it for a
    period that already has an invoice is a no-op, not a duplicate.
    """

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "period_year", "period_month", name="uq_invoice_tenant_period"
        ),
    )

    period_year: Mapped[int] = mapped_column(Integer, nullable=False)
    period_month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-12

    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True
    )
    plan_name_snapshot: Mapped[str] = mapped_column(String(100), nullable=False)

    base_charge_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    included_messages: Mapped[int] = mapped_column(Integer, nullable=False)
    total_messages: Mapped[int] = mapped_column(Integer, nullable=False)
    overage_messages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overage_cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, default=Decimal("0")
    )
    total_ai_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    total_cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)

    status: Mapped[InvoiceStatus] = mapped_column(
        Enum(InvoiceStatus, name="invoice_status"), nullable=False, default=InvoiceStatus.ISSUED
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

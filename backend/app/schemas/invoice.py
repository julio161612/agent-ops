import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.invoice import InvoiceStatus
from app.schemas.plan import PlanRead


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    period_year: int
    period_month: int
    plan_id: uuid.UUID | None
    plan_name_snapshot: str
    base_charge_usd: Decimal
    included_messages: int
    total_messages: int
    overage_messages: int
    overage_cost_usd: Decimal
    total_ai_cost_usd: Decimal
    total_cost_usd: Decimal
    status: InvoiceStatus
    issued_at: datetime | None
    created_at: datetime


class CurrentUsageRead(BaseModel):
    plan: PlanRead
    period_year: int
    period_month: int
    messages_used: int
    included_messages: int | None
    overage_messages: int
    overage_cost_usd: Decimal
    ai_cost_usd: Decimal
    included_ai_cost_usd: Decimal | None
    overage_enabled: bool

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class TenantLimitsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    messages_per_minute_limit: int
    monthly_cost_limit_usd: Decimal | None
    current_month: str
    current_month_cost_usd: Decimal
    created_at: datetime
    updated_at: datetime


class TenantLimitsUpdate(BaseModel):
    messages_per_minute_limit: int | None = Field(default=None, gt=0)
    monthly_cost_limit_usd: Decimal | None = Field(
        default=None, description="Set to null to remove the cap (unlimited)."
    )

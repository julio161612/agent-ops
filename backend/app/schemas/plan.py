import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    monthly_price_usd: Decimal
    included_messages_per_month: int | None
    included_active_agents: int | None
    included_users: int | None
    included_ai_cost_usd: Decimal | None
    max_messages_per_minute: int
    overage_price_per_1000_messages_usd: Decimal | None
    is_active: bool
    created_at: datetime

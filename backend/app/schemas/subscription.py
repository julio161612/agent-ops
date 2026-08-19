import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.tenant_subscription import SubscriptionStatus
from app.schemas.plan import PlanRead


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    plan_id: uuid.UUID
    status: SubscriptionStatus
    started_at: datetime
    overage_enabled: bool


class SubscriptionWithPlanRead(SubscriptionRead):
    plan: PlanRead


class ChangePlanRequest(BaseModel):
    plan_id: uuid.UUID
    overage_enabled: bool | None = None

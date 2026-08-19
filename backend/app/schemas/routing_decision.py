import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.routing_decision import RoutingMethod


class RoutingDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    method: RoutingMethod
    matched_rule_id: uuid.UUID | None
    agent_id: uuid.UUID | None
    confidence: float | None
    reasoning: str | None
    created_at: datetime

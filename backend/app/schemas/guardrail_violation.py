import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.guardrail_policy import GuardrailAction, GuardrailRuleType, GuardrailType


class GuardrailViolationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID | None
    policy_id: uuid.UUID | None
    guardrail_type: GuardrailType
    violation_type: GuardrailRuleType
    detail: str
    action_taken: GuardrailAction
    created_at: datetime

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.escalation_case import EscalationReason, EscalationStatus
from app.schemas.message import MessageRead


class EscalationCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    reason: EscalationReason
    status: EscalationStatus
    assigned_to: uuid.UUID | None
    assigned_at: datetime | None
    resolved_at: datetime | None
    resolution_notes: str | None
    created_at: datetime
    updated_at: datetime


class EscalationRespondRequest(BaseModel):
    content: str = Field(min_length=1)


class EscalationRespondResponse(BaseModel):
    case: EscalationCaseRead
    message: MessageRead


class EscalationResolveRequest(BaseModel):
    notes: str | None = None

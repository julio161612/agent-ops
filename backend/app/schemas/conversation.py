import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.conversation import ConversationStatus


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    agent_id: uuid.UUID
    status: ConversationStatus
    created_at: datetime
    updated_at: datetime

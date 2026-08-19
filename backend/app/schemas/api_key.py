import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.api_key import ApiKeyType


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    key_type: ApiKeyType = Field(
        default=ApiKeyType.SERVER,
        description="'server' for backend-to-backend use (can send messages and read session "
        "history); 'widget' for embedding in public page source (send-only, enforced "
        "server-side regardless of can_send_messages).",
    )
    can_send_messages: bool = Field(
        default=True,
        description="Ignored for key_type='widget' — a widget key can always send messages, "
        "that's its only purpose.",
    )


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    key_type: ApiKeyType
    key_prefix: str
    can_send_messages: bool
    is_active: bool
    created_by_user_id: uuid.UUID | None
    last_used_at: datetime | None
    created_at: datetime


class ApiKeyCreateResponse(ApiKeyRead):
    api_key: str = Field(
        description="The full raw key. Shown ONLY in this response — it is never "
        "recoverable again, store it now."
    )

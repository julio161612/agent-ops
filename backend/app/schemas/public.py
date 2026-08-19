import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.conversation import ConversationStatus
from app.models.message import MessageRole


class PublicMessageRequest(BaseModel):
    content: str = Field(min_length=1)
    session_id: uuid.UUID | None = Field(
        default=None,
        description="Omit to start a new session — the response's session_id is the one to "
        "reuse on subsequent calls for the same end user.",
    )
    external_user_id: str = Field(
        min_length=1,
        max_length=255,
        description="An identifier you choose for this end user (your own user id, a visitor "
        "id, an email...). Opaque to Agent Ops — used only so you can tell your own sessions "
        "apart later, never validated against anything.",
    )


class PublicMessageResponse(BaseModel):
    session_id: uuid.UUID
    reply: str | None = Field(
        default=None,
        description="Null only when no agent could be assigned yet (status='unassigned') — "
        "every other outcome, including a guardrail block, still returns a reply.",
    )
    status: ConversationStatus


class PublicMessageRead(BaseModel):
    role: MessageRole
    content: str
    created_at: datetime


class PublicHistoryResponse(BaseModel):
    session_id: uuid.UUID
    messages: list[PublicMessageRead]

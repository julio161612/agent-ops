import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.conversation import ConversationStatus
from app.models.message import MessageRole
from app.schemas.guardrail_violation import GuardrailViolationRead
from app.schemas.routing_decision import RoutingDecisionRead


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: MessageRole
    content: str
    metadata_: dict[str, Any] = Field(alias="message_metadata", serialization_alias="metadata")
    created_at: datetime


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1)
    agent_id: uuid.UUID | None = Field(
        default=None,
        description="Optional explicit agent. If omitted and the conversation has no "
        "agent yet, RoutingService picks one automatically (rules, then the LLM router).",
    )


class SendMessageResponse(BaseModel):
    conversation_id: uuid.UUID
    conversation_status: ConversationStatus
    user_message: MessageRead
    assistant_message: MessageRead | None = Field(
        default=None,
        description="Null when no agent could be assigned to this conversation — "
        "see `routing` for why, and `conversation_status` will be 'unassigned'.",
    )
    routing: RoutingDecisionRead | None = Field(
        default=None, description="Populated only on turns where routing actually ran."
    )
    guardrail_violations: list[GuardrailViolationRead] = Field(
        default_factory=list,
        description="Every guardrail violation (blocked or merely flagged) recorded this turn, "
        "across both the input and output checks.",
    )
    trace_id: uuid.UUID | None = Field(
        default=None,
        description="Id of this turn's InteractionTrace — fetch it via GET /traces/{id} "
        "for the full pipeline breakdown (per-stage latency, cost, etc).",
    )

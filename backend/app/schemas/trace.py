import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.interaction_trace import TraceOutcome
from app.schemas.escalation import EscalationCaseRead
from app.schemas.guardrail_violation import GuardrailViolationRead
from app.schemas.routing_decision import RoutingDecisionRead


class InteractionTraceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID | None
    agent_id: uuid.UUID | None
    routing_decision_id: uuid.UUID | None
    escalation_case_id: uuid.UUID | None
    outcome: TraceOutcome
    cost_usd: Decimal
    input_tokens: int
    output_tokens: int
    total_latency_ms: int
    stage_latencies_ms: dict[str, int]
    created_at: datetime


class InteractionTracePage(BaseModel):
    items: list[InteractionTraceRead]
    total: int
    limit: int
    offset: int


class InteractionTraceDetail(InteractionTraceRead):
    guardrail_violations: list[GuardrailViolationRead] = Field(default_factory=list)
    routing_decision: RoutingDecisionRead | None = None
    escalation_case: EscalationCaseRead | None = None

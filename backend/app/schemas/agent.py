import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.agent import DEFAULT_AGENT_PARAMETERS
from app.models.guardrail_policy import GuardrailAction, GuardrailRuleType, GuardrailType


class AgentParameters(BaseModel):
    """Validated shape of Agent.parameters — everything else is passed through."""

    model_config = ConfigDict(extra="allow")

    temperature: float = Field(default=1.0, ge=0.0, le=1.0)
    max_tokens: int = Field(default=1024, gt=0, le=64_000)


class AgentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    agent_type: str | None = Field(default=None, max_length=100)
    system_prompt: str = Field(min_length=1)
    model: str | None = None
    parameters: AgentParameters = Field(
        default_factory=lambda: AgentParameters(**DEFAULT_AGENT_PARAMETERS)
    )
    is_active: bool = True


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    agent_type: str | None = Field(default=None, max_length=100)
    system_prompt: str | None = Field(default=None, min_length=1)
    model: str | None = None
    parameters: AgentParameters | None = None
    is_active: bool | None = None


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str | None
    agent_type: str | None
    system_prompt: str
    model: str
    parameters: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AgentTestRequest(BaseModel):
    content: str = Field(min_length=1, description="Example message to send to the agent.")


class GuardrailDryRunViolationRead(BaseModel):
    policy_id: uuid.UUID
    guardrail_type: GuardrailType
    violation_type: GuardrailRuleType
    detail: str
    action_taken: GuardrailAction


class AgentTestResponse(BaseModel):
    agent_id: uuid.UUID
    input_blocked: bool
    input_guardrail_violations: list[GuardrailDryRunViolationRead]
    reply: str | None = Field(
        default=None, description="Null when input_blocked — the agent never ran."
    )
    output_blocked: bool
    output_guardrail_violations: list[GuardrailDryRunViolationRead]
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal = Field(
        description="Real cost of this test call — it's a real Anthropic request, so it's "
        "real money, even though nothing about the call is saved as conversation history."
    )
    latency_ms: int

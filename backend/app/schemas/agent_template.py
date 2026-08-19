from typing import Any

from pydantic import BaseModel, Field

from app.models.guardrail_policy import GuardrailAction, GuardrailRuleType, GuardrailType
from app.schemas.agent import AgentRead
from app.schemas.guardrail_policy import GuardrailPolicyRead


class RecommendedGuardrailRead(BaseModel):
    guardrail_type: GuardrailType
    rule_type: GuardrailRuleType
    config: dict[str, Any]
    action_on_violation: GuardrailAction
    rationale: str


class AgentTemplateRead(BaseModel):
    id: str
    name: str
    description: str
    agent_type: str
    system_prompt: str
    suggested_model: str
    suggested_parameters: dict[str, Any]
    recommended_guardrail: RecommendedGuardrailRead


class CreateAgentFromTemplateRequest(BaseModel):
    name: str | None = Field(
        default=None, min_length=1, max_length=255, description="Override the template's name."
    )
    system_prompt: str | None = Field(
        default=None, min_length=1, description="Override the template's system_prompt."
    )
    model: str | None = Field(default=None, description="Override the template's suggested model.")
    apply_recommended_guardrail: bool = Field(
        default=True,
        description="Also create the template's recommended guardrail policy, scoped to this "
        "new agent. On by default — the whole point of a template is shipping with a sane "
        "default, not an unprotected agent.",
    )


class CreateAgentFromTemplateResponse(BaseModel):
    agent: AgentRead
    guardrail_policy: GuardrailPolicyRead | None = Field(
        default=None,
        description="Null only if apply_recommended_guardrail was false.",
    )

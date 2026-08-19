import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_templates import AgentTemplate, get_template, list_templates
from app.core.exceptions import AgentTemplateNotFoundError
from app.models.agent import Agent
from app.models.guardrail_policy import (
    GuardrailAction,
    GuardrailPolicy,
    GuardrailRuleType,
    GuardrailType,
)
from app.schemas.agent import AgentCreate, AgentParameters
from app.schemas.guardrail_policy import GuardrailPolicyCreate
from app.services import agent_service, guardrail_policy_service


def list_agent_templates() -> list[AgentTemplate]:
    return list_templates()


async def create_agent_from_template(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    template_id: str,
    name: str | None,
    system_prompt: str | None,
    model: str | None,
    apply_recommended_guardrail: bool,
) -> tuple[Agent, GuardrailPolicy | None]:
    """Materialize a catalog template into a real tenant Agent (and, by
    default, its recommended GuardrailPolicy scoped to that agent).

    Any of name/system_prompt/model can be overridden; everything else
    (description, agent_type, suggested parameters) always comes from the
    template — those aren't exposed as "guided setup" choices here, just
    starting points a user can still edit afterwards via PATCH /agents/{id}.
    """
    template = get_template(template_id)
    if template is None:
        raise AgentTemplateNotFoundError(template_id)

    agent = await agent_service.create_agent(
        db,
        tenant_id=tenant_id,
        payload=AgentCreate(
            name=name or template.name,
            description=template.description,
            agent_type=template.agent_type,
            system_prompt=system_prompt or template.system_prompt,
            model=model or template.suggested_model,
            parameters=AgentParameters(**template.suggested_parameters),
        ),
    )

    if not apply_recommended_guardrail:
        return agent, None

    recommendation = template.recommended_guardrail
    guardrail_policy = await guardrail_policy_service.create_policy(
        db,
        tenant_id=tenant_id,
        payload=GuardrailPolicyCreate(
            agent_id=agent.id,
            guardrail_type=GuardrailType(recommendation.guardrail_type),
            rule_type=GuardrailRuleType(recommendation.rule_type),
            config=recommendation.config,
            action_on_violation=GuardrailAction(recommendation.action_on_violation),
        ),
    )
    return agent, guardrail_policy

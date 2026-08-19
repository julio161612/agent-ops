from fastapi import APIRouter, Depends

from app.api.deps import require_role
from app.models.user import UserRole
from app.schemas.agent_template import AgentTemplateRead, RecommendedGuardrailRead
from app.services import agent_template_service

router = APIRouter(
    prefix="/agent-templates",
    tags=["agent-templates"],
    dependencies=[Depends(require_role(UserRole.VIEWER))],
)


@router.get("", response_model=list[AgentTemplateRead])
async def list_agent_templates() -> list[AgentTemplateRead]:
    """The platform-wide template catalog — not tenant-scoped, just requires auth."""
    return [
        AgentTemplateRead(
            id=t.id,
            name=t.name,
            description=t.description,
            agent_type=t.agent_type,
            system_prompt=t.system_prompt,
            suggested_model=t.suggested_model,
            suggested_parameters=t.suggested_parameters,
            recommended_guardrail=RecommendedGuardrailRead(
                guardrail_type=t.recommended_guardrail.guardrail_type,
                rule_type=t.recommended_guardrail.rule_type,
                config=t.recommended_guardrail.config,
                action_on_violation=t.recommended_guardrail.action_on_violation,
                rationale=t.recommended_guardrail.rationale,
            ),
        )
        for t in agent_template_service.list_agent_templates()
    ]

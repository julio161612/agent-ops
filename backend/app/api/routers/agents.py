import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id, require_role
from app.core.database import get_db
from app.core.exceptions import (
    AgentNotFoundError,
    AgentRateLimitedError,
    AgentTemplateNotFoundError,
    AgentTimeoutError,
    AgentUpstreamError,
    PlanAgentLimitExceededError,
    TenantCostLimitExceededError,
    TenantMessageQuotaExceededError,
    TenantRateLimitExceededError,
)
from app.models.user import UserRole
from app.schemas.agent import (
    AgentCreate,
    AgentRead,
    AgentTestRequest,
    AgentTestResponse,
    AgentUpdate,
    GuardrailDryRunViolationRead,
)
from app.schemas.agent_template import (
    CreateAgentFromTemplateRequest,
    CreateAgentFromTemplateResponse,
)
from app.schemas.guardrail_policy import GuardrailPolicyRead
from app.services import agent_service, agent_template_service
from app.services.agent_execution_service import AgentExecutionService, get_agent_execution_service

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post(
    "",
    response_model=AgentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.OPERATOR))],
)
async def create_agent(
    payload: AgentCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> AgentRead:
    try:
        agent = await agent_service.create_agent(db, tenant_id=tenant_id, payload=payload)
    except PlanAgentLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return AgentRead.model_validate(agent)


@router.post(
    "/from-template/{template_id}",
    response_model=CreateAgentFromTemplateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.OPERATOR))],
)
async def create_agent_from_template(
    template_id: str,
    payload: CreateAgentFromTemplateRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> CreateAgentFromTemplateResponse:
    try:
        agent, guardrail_policy = await agent_template_service.create_agent_from_template(
            db,
            tenant_id=tenant_id,
            template_id=template_id,
            name=payload.name,
            system_prompt=payload.system_prompt,
            model=payload.model,
            apply_recommended_guardrail=payload.apply_recommended_guardrail,
        )
    except AgentTemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent template not found"
        ) from exc
    except PlanAgentLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return CreateAgentFromTemplateResponse(
        agent=AgentRead.model_validate(agent),
        guardrail_policy=(
            GuardrailPolicyRead.model_validate(guardrail_policy)
            if guardrail_policy is not None
            else None
        ),
    )


@router.get(
    "", response_model=list[AgentRead], dependencies=[Depends(require_role(UserRole.VIEWER))]
)
async def list_agents(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> list[AgentRead]:
    agents = await agent_service.list_agents(db, tenant_id=tenant_id)
    return [AgentRead.model_validate(a) for a in agents]


@router.get(
    "/{agent_id}",
    response_model=AgentRead,
    dependencies=[Depends(require_role(UserRole.VIEWER))],
)
async def get_agent(
    agent_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> AgentRead:
    try:
        agent = await agent_service.get_agent(db, tenant_id=tenant_id, agent_id=agent_id)
    except AgentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        ) from exc
    return AgentRead.model_validate(agent)


@router.patch(
    "/{agent_id}",
    response_model=AgentRead,
    dependencies=[Depends(require_role(UserRole.OPERATOR))],
)
async def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> AgentRead:
    try:
        agent = await agent_service.update_agent(
            db, tenant_id=tenant_id, agent_id=agent_id, payload=payload
        )
    except AgentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        ) from exc
    except PlanAgentLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return AgentRead.model_validate(agent)


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.OPERATOR))],
)
async def delete_agent(
    agent_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await agent_service.soft_delete_agent(db, tenant_id=tenant_id, agent_id=agent_id)
    except AgentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        ) from exc


@router.post(
    "/{agent_id}/test",
    response_model=AgentTestResponse,
    dependencies=[Depends(require_role(UserRole.OPERATOR))],
)
async def test_agent(
    agent_id: uuid.UUID,
    payload: AgentTestRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    service: AgentExecutionService = Depends(get_agent_execution_service),
) -> AgentTestResponse:
    """Send a one-off test message straight to this agent — for validating a
    system_prompt/guardrail setup before real customers see it.

    No Conversation, Message, or InteractionTrace is created — this never
    shows up in conversation history or in /metrics. It IS a real Anthropic
    call, so it costs real money and is still subject to the tenant's rate
    limit and monthly cost cap (see ``cost_usd`` on the response, and
    AgentExecutionService.test_agent's docstring for the full reasoning).
    """
    try:
        result = await service.test_agent(
            tenant_id=tenant_id, agent_id=agent_id, content=payload.content
        )
    except AgentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        ) from exc
    except TenantRateLimitExceededError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except TenantCostLimitExceededError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except TenantMessageQuotaExceededError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except AgentRateLimitedError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except AgentTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except AgentUpstreamError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    def _violation_read(v) -> GuardrailDryRunViolationRead:
        return GuardrailDryRunViolationRead(
            policy_id=v.policy_id,
            guardrail_type=v.guardrail_type,
            violation_type=v.violation_type,
            detail=v.detail,
            action_taken=v.action_taken,
        )

    return AgentTestResponse(
        agent_id=result.agent_id,
        input_blocked=result.input_blocked,
        input_guardrail_violations=[_violation_read(v) for v in result.input_guardrail_violations],
        reply=result.reply,
        output_blocked=result.output_blocked,
        output_guardrail_violations=[
            _violation_read(v) for v in result.output_guardrail_violations
        ],
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
    )

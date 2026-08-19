import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id, require_role
from app.core.database import get_db
from app.core.exceptions import (
    AgentNotFoundError,
    AgentRateLimitedError,
    AgentTimeoutError,
    AgentUpstreamError,
    ConversationNotFoundError,
    TenantCostLimitExceededError,
    TenantMessageQuotaExceededError,
    TenantRateLimitExceededError,
)
from app.models.user import UserRole
from app.schemas.guardrail_violation import GuardrailViolationRead
from app.schemas.message import MessageRead, SendMessageRequest, SendMessageResponse
from app.schemas.routing_decision import RoutingDecisionRead
from app.services import conversation_service
from app.services.agent_execution_service import AgentExecutionService, get_agent_execution_service

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post(
    "/{conversation_id}/messages",
    response_model=SendMessageResponse,
    dependencies=[Depends(require_role(UserRole.OPERATOR))],
)
async def send_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    service: AgentExecutionService = Depends(get_agent_execution_service),
) -> SendMessageResponse:
    """Send a user message to a conversation, running its agent for a real reply.

    Full pipeline: tenant rate limit + monthly cost cap, INPUT guardrails,
    routing (if the conversation has no agent yet), agent execution, OUTPUT
    guardrails. If a BLOCK-level guardrail fires, this still returns 200 with a
    generic substitute reply — see ``guardrail_violations`` and
    ``conversation_status`` (flips to "escalated" if the agent's actual answer
    was blocked). Only the tenant-level budget gate returns 429.
    """
    try:
        result = await service.send_message(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            agent_id=payload.agent_id,
            content=payload.content,
        )
    except TenantRateLimitExceededError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except TenantCostLimitExceededError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except TenantMessageQuotaExceededError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except AgentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        ) from exc
    except AgentRateLimitedError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except AgentTimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=str(exc)) from exc
    except AgentUpstreamError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return SendMessageResponse(
        conversation_id=result.conversation.id,
        conversation_status=result.conversation.status,
        user_message=MessageRead.model_validate(result.user_message),
        assistant_message=(
            MessageRead.model_validate(result.assistant_message)
            if result.assistant_message is not None
            else None
        ),
        routing=(
            RoutingDecisionRead.model_validate(result.routing_decision)
            if result.routing_decision is not None
            else None
        ),
        guardrail_violations=[
            GuardrailViolationRead.model_validate(v) for v in result.guardrail_violations
        ],
        trace_id=result.trace.id if result.trace is not None else None,
    )


@router.get(
    "/{conversation_id}/messages",
    response_model=list[MessageRead],
    dependencies=[Depends(require_role(UserRole.VIEWER))],
)
async def list_messages(
    conversation_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> list[MessageRead]:
    try:
        messages = await conversation_service.list_messages(
            db, tenant_id=tenant_id, conversation_id=conversation_id
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
        ) from exc
    return [MessageRead.model_validate(m) for m in messages]

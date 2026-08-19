import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_send_message_key, require_server_key
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import (
    AgentRateLimitedError,
    AgentTimeoutError,
    AgentUpstreamError,
    ConversationNotFoundError,
    TenantCostLimitExceededError,
    TenantMessageQuotaExceededError,
    TenantRateLimitExceededError,
)
from app.core.redis import get_redis
from app.models.api_key import ApiKey
from app.schemas.public import (
    PublicHistoryResponse,
    PublicMessageRead,
    PublicMessageRequest,
    PublicMessageResponse,
)
from app.services import conversation_service
from app.services.agent_execution_service import AgentExecutionService, get_agent_execution_service
from app.services.rate_limiter import RateLimiter

router = APIRouter(prefix="/public/v1", tags=["public-api"])


@router.post("/messages", response_model=PublicMessageResponse)
async def send_public_message(
    payload: PublicMessageRequest,
    api_key: ApiKey = Depends(require_send_message_key),
    service: AgentExecutionService = Depends(get_agent_execution_service),
    redis_client: Redis = Depends(get_redis),
) -> PublicMessageResponse:
    """End-customer-facing entry point (widget or the tenant's own backend),
    authenticated with an API key instead of a user JWT. Runs the exact same
    pipeline as the internal ``POST /conversations/{id}/messages`` — routing,
    guardrails, cost tracking, escalation — just fronted by a different auth
    mechanism and a stricter, per-key rate limit on top of the tenant-wide one.
    """
    rate_limiter = RateLimiter(redis_client)
    rate_status = await rate_limiter.check_and_increment(
        key=f"public_api_key:{api_key.id}",
        limit_per_minute=settings.PUBLIC_API_RATE_LIMIT_PER_MINUTE,
    )
    if not rate_status.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {rate_status.limit} requests per minute for this API key",
        )

    session_id = payload.session_id or uuid.uuid4()
    try:
        result = await service.send_message(
            tenant_id=api_key.tenant_id,
            conversation_id=session_id,
            agent_id=None,
            content=payload.content,
            external_user_id=payload.external_user_id,
        )
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

    return PublicMessageResponse(
        session_id=result.conversation.id,
        reply=result.assistant_message.content if result.assistant_message is not None else None,
        status=result.conversation.status,
    )


@router.get("/messages/{session_id}", response_model=PublicHistoryResponse)
async def get_public_message_history(
    session_id: uuid.UUID,
    api_key: ApiKey = Depends(require_server_key),
    db: AsyncSession = Depends(get_db),
) -> PublicHistoryResponse:
    """Server-key only — a WIDGET key can never read history, even for a
    session it created itself (see require_server_key). Meant for a tenant's
    own backend to pull a transcript (e.g. into a CRM), not for the widget.
    """
    try:
        messages = await conversation_service.list_messages(
            db, tenant_id=api_key.tenant_id, conversation_id=session_id
        )
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        ) from exc

    return PublicHistoryResponse(
        session_id=session_id,
        messages=[
            PublicMessageRead(role=m.role, content=m.content, created_at=m.created_at)
            for m in messages
        ],
    )

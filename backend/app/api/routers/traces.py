import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id, require_role
from app.core.database import get_db
from app.core.exceptions import InteractionTraceNotFoundError
from app.models.interaction_trace import TraceOutcome
from app.models.user import UserRole
from app.schemas.escalation import EscalationCaseRead
from app.schemas.guardrail_violation import GuardrailViolationRead
from app.schemas.routing_decision import RoutingDecisionRead
from app.schemas.trace import InteractionTraceDetail, InteractionTracePage, InteractionTraceRead
from app.services import trace_service

router = APIRouter(
    prefix="/traces", tags=["traces"], dependencies=[Depends(require_role(UserRole.VIEWER))]
)


@router.get("", response_model=InteractionTracePage)
async def list_traces(
    conversation_id: uuid.UUID | None = Query(default=None),
    outcome: TraceOutcome | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> InteractionTracePage:
    traces, total = await trace_service.list_traces(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        outcome=outcome,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return InteractionTracePage(
        items=[InteractionTraceRead.model_validate(t) for t in traces],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{trace_id}", response_model=InteractionTraceDetail)
async def get_trace(
    trace_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> InteractionTraceDetail:
    try:
        detail = await trace_service.get_trace_detail(db, tenant_id=tenant_id, trace_id=trace_id)
    except InteractionTraceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Trace not found"
        ) from exc

    return InteractionTraceDetail(
        **InteractionTraceRead.model_validate(detail.trace).model_dump(),
        guardrail_violations=[
            GuardrailViolationRead.model_validate(v) for v in detail.guardrail_violations
        ],
        routing_decision=(
            RoutingDecisionRead.model_validate(detail.routing_decision)
            if detail.routing_decision is not None
            else None
        ),
        escalation_case=(
            EscalationCaseRead.model_validate(detail.escalation_case)
            if detail.escalation_case is not None
            else None
        ),
    )

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id, require_role
from app.core.database import get_db
from app.core.exceptions import (
    EscalationCaseAlreadyClaimedError,
    EscalationCaseInvalidStateError,
    EscalationCaseNotFoundError,
    EscalationCaseNotOwnedError,
)
from app.models.escalation_case import EscalationReason, EscalationStatus
from app.models.user import User, UserRole
from app.schemas.escalation import (
    EscalationCaseRead,
    EscalationResolveRequest,
    EscalationRespondRequest,
    EscalationRespondResponse,
)
from app.schemas.message import MessageRead
from app.services import escalation_service

router = APIRouter(prefix="/escalations", tags=["escalations"])


@router.get(
    "",
    response_model=list[EscalationCaseRead],
    dependencies=[Depends(require_role(UserRole.VIEWER))],
)
async def list_escalations(
    status_filter: EscalationStatus | None = Query(default=None, alias="status"),
    reason: EscalationReason | None = Query(default=None),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> list[EscalationCaseRead]:
    cases = await escalation_service.list_cases(
        db, tenant_id=tenant_id, status=status_filter, reason=reason
    )
    return [EscalationCaseRead.model_validate(c) for c in cases]


@router.get(
    "/{case_id}",
    response_model=EscalationCaseRead,
    dependencies=[Depends(require_role(UserRole.VIEWER))],
)
async def get_escalation(
    case_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> EscalationCaseRead:
    try:
        case = await escalation_service.get_case(db, tenant_id=tenant_id, case_id=case_id)
    except EscalationCaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Escalation case not found"
        ) from exc
    return EscalationCaseRead.model_validate(case)


@router.post("/{case_id}/claim", response_model=EscalationCaseRead)
async def claim_escalation(
    case_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    current_user: User = Depends(require_role(UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> EscalationCaseRead:
    try:
        case = await escalation_service.claim_case(
            db, tenant_id=tenant_id, case_id=case_id, user_id=current_user.id
        )
    except EscalationCaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Escalation case not found"
        ) from exc
    except EscalationCaseAlreadyClaimedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return EscalationCaseRead.model_validate(case)


@router.post("/{case_id}/respond", response_model=EscalationRespondResponse)
async def respond_to_escalation(
    case_id: uuid.UUID,
    payload: EscalationRespondRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    current_user: User = Depends(require_role(UserRole.OPERATOR)),
    db: AsyncSession = Depends(get_db),
) -> EscalationRespondResponse:
    try:
        case, message = await escalation_service.respond_to_case(
            db,
            tenant_id=tenant_id,
            case_id=case_id,
            user_id=current_user.id,
            content=payload.content,
        )
    except EscalationCaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Escalation case not found"
        ) from exc
    except EscalationCaseNotOwnedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except EscalationCaseInvalidStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return EscalationRespondResponse(
        case=EscalationCaseRead.model_validate(case), message=MessageRead.model_validate(message)
    )


@router.post(
    "/{case_id}/resolve",
    response_model=EscalationCaseRead,
    dependencies=[Depends(require_role(UserRole.OPERATOR))],
)
async def resolve_escalation(
    case_id: uuid.UUID,
    payload: EscalationResolveRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> EscalationCaseRead:
    try:
        case = await escalation_service.resolve_case(
            db, tenant_id=tenant_id, case_id=case_id, notes=payload.notes
        )
    except EscalationCaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Escalation case not found"
        ) from exc
    except EscalationCaseInvalidStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return EscalationCaseRead.model_validate(case)


@router.post(
    "/{case_id}/release",
    response_model=EscalationCaseRead,
    dependencies=[Depends(require_role(UserRole.OPERATOR))],
)
async def release_escalation(
    case_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> EscalationCaseRead:
    try:
        case = await escalation_service.release_case(db, tenant_id=tenant_id, case_id=case_id)
    except EscalationCaseNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Escalation case not found"
        ) from exc
    except EscalationCaseInvalidStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return EscalationCaseRead.model_validate(case)

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id, require_role
from app.core.database import get_db
from app.core.exceptions import (
    AgentNotFoundError,
    GuardrailPolicyNotFoundError,
    InvalidGuardrailConfigError,
)
from app.models.user import UserRole
from app.schemas.guardrail_policy import (
    GuardrailPolicyCreate,
    GuardrailPolicyRead,
    GuardrailPolicyUpdate,
)
from app.services import guardrail_policy_service

router = APIRouter(prefix="/guardrail-policies", tags=["guardrail-policies"])


@router.post(
    "",
    response_model=GuardrailPolicyRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.OPERATOR))],
)
async def create_policy(
    payload: GuardrailPolicyCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> GuardrailPolicyRead:
    try:
        policy = await guardrail_policy_service.create_policy(
            db, tenant_id=tenant_id, payload=payload
        )
    except AgentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        ) from exc
    return GuardrailPolicyRead.model_validate(policy)


@router.get(
    "",
    response_model=list[GuardrailPolicyRead],
    dependencies=[Depends(require_role(UserRole.VIEWER))],
)
async def list_policies(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> list[GuardrailPolicyRead]:
    policies = await guardrail_policy_service.list_policies(db, tenant_id=tenant_id)
    return [GuardrailPolicyRead.model_validate(p) for p in policies]


@router.get(
    "/{policy_id}",
    response_model=GuardrailPolicyRead,
    dependencies=[Depends(require_role(UserRole.VIEWER))],
)
async def get_policy(
    policy_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> GuardrailPolicyRead:
    try:
        policy = await guardrail_policy_service.get_policy(
            db, tenant_id=tenant_id, policy_id=policy_id
        )
    except GuardrailPolicyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Guardrail policy not found"
        ) from exc
    return GuardrailPolicyRead.model_validate(policy)


@router.patch(
    "/{policy_id}",
    response_model=GuardrailPolicyRead,
    dependencies=[Depends(require_role(UserRole.OPERATOR))],
)
async def update_policy(
    policy_id: uuid.UUID,
    payload: GuardrailPolicyUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> GuardrailPolicyRead:
    try:
        policy = await guardrail_policy_service.update_policy(
            db, tenant_id=tenant_id, policy_id=policy_id, payload=payload
        )
    except GuardrailPolicyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Guardrail policy not found"
        ) from exc
    except AgentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        ) from exc
    except InvalidGuardrailConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return GuardrailPolicyRead.model_validate(policy)


@router.delete(
    "/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.OPERATOR))],
)
async def delete_policy(
    policy_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await guardrail_policy_service.delete_policy(db, tenant_id=tenant_id, policy_id=policy_id)
    except GuardrailPolicyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Guardrail policy not found"
        ) from exc

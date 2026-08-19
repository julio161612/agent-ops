import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id, require_role
from app.core.database import get_db
from app.core.exceptions import TenantLimitsExceedPlanError
from app.models.user import UserRole
from app.schemas.tenant_limits import TenantLimitsRead, TenantLimitsUpdate
from app.services import tenant_limits_service

router = APIRouter(prefix="/tenant-limits", tags=["tenant-limits"])


@router.get(
    "", response_model=TenantLimitsRead, dependencies=[Depends(require_role(UserRole.VIEWER))]
)
async def get_tenant_limits(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> TenantLimitsRead:
    limits = await tenant_limits_service.get_limits(db, tenant_id=tenant_id)
    return TenantLimitsRead.model_validate(limits)


@router.patch(
    "", response_model=TenantLimitsRead, dependencies=[Depends(require_role(UserRole.ADMIN))]
)
async def update_tenant_limits(
    payload: TenantLimitsUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> TenantLimitsRead:
    try:
        limits = await tenant_limits_service.update_limits(db, tenant_id=tenant_id, payload=payload)
    except TenantLimitsExceedPlanError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return TenantLimitsRead.model_validate(limits)

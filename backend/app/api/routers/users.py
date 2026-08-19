import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id, get_current_user, require_role
from app.core.database import get_db
from app.core.exceptions import (
    CannotModifySelfError,
    EmailAlreadyRegisteredError,
    LastActiveAdminError,
    PlanUserLimitExceededError,
    UserNotFoundError,
)
from app.models.user import User, UserRole
from app.schemas.user import UserInvite, UserRead, UserRoleUpdate
from app.services import user_service

router = APIRouter(
    prefix="/users", tags=["users"], dependencies=[Depends(require_role(UserRole.ADMIN))]
)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def invite_user(
    payload: UserInvite,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    try:
        user = await user_service.create_user(db, tenant_id=tenant_id, payload=payload)
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from exc
    except PlanUserLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return UserRead.model_validate(user)


@router.get("", response_model=list[UserRead])
async def list_users(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> list[UserRead]:
    users = await user_service.list_users(db, tenant_id=tenant_id)
    return [UserRead.model_validate(u) for u in users]


@router.patch("/{user_id}", response_model=UserRead)
async def update_user_role(
    user_id: uuid.UUID,
    payload: UserRoleUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    try:
        user = await user_service.update_user_role(
            db, tenant_id=tenant_id, user_id=user_id, new_role=payload.role
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from exc
    except LastActiveAdminError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return UserRead.model_validate(user)


@router.post("/{user_id}/deactivate", response_model=UserRead)
async def deactivate_user(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserRead:
    try:
        user = await user_service.deactivate_user(
            db, tenant_id=tenant_id, user_id=user_id, acting_user_id=current_user.id
        )
    except UserNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found") from exc
    except CannotModifySelfError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except LastActiveAdminError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return UserRead.model_validate(user)

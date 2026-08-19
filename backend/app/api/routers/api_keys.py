import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id, get_current_user, require_role
from app.core.database import get_db
from app.core.exceptions import ApiKeyNotFoundError
from app.models.user import User, UserRole
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreateResponse, ApiKeyRead
from app.services import api_key_service

router = APIRouter(
    prefix="/api-keys", tags=["api-keys"], dependencies=[Depends(require_role(UserRole.ADMIN))]
)


@router.post("", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: ApiKeyCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyCreateResponse:
    """Generate a new API key for the public API. The raw key is returned
    here ONCE — the database only ever stores its hash, so there is no way
    to recover it later, not even for an admin.
    """
    key, raw_key = await api_key_service.create_api_key(
        db,
        tenant_id=tenant_id,
        created_by_user_id=current_user.id,
        name=payload.name,
        key_type=payload.key_type,
        can_send_messages=payload.can_send_messages,
    )
    return ApiKeyCreateResponse(**ApiKeyRead.model_validate(key).model_dump(), api_key=raw_key)


@router.get("", response_model=list[ApiKeyRead])
async def list_api_keys(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> list[ApiKeyRead]:
    keys = await api_key_service.list_api_keys(db, tenant_id=tenant_id)
    return [ApiKeyRead.model_validate(k) for k in keys]


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await api_key_service.revoke_api_key(db, tenant_id=tenant_id, key_id=key_id)
    except ApiKeyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="API key not found"
        ) from exc

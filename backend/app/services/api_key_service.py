import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ApiKeyNotFoundError
from app.core.security import generate_api_key, hash_api_key
from app.models.api_key import API_KEY_PREFIXES, ApiKey, ApiKeyType

_PREFIX_DISPLAY_LENGTH = 12


async def create_api_key(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    name: str,
    key_type: ApiKeyType,
    can_send_messages: bool,
) -> tuple[ApiKey, str]:
    """Create a key and return ``(row, raw_key)`` — the caller must hand
    ``raw_key`` to the user right now; it's never recoverable again.

    A WIDGET key is always ``can_send_messages=True`` regardless of what's
    requested — sending messages is the one thing it exists to do, so a
    widget key that couldn't would just be a useless key, not a more
    restricted one.
    """
    raw_key = generate_api_key(API_KEY_PREFIXES[key_type])
    key = ApiKey(
        tenant_id=tenant_id,
        name=name,
        key_type=key_type,
        key_prefix=raw_key[:_PREFIX_DISPLAY_LENGTH],
        key_hash=hash_api_key(raw_key),
        can_send_messages=True if key_type == ApiKeyType.WIDGET else can_send_messages,
        created_by_user_id=created_by_user_id,
    )
    db.add(key)
    await db.commit()
    await db.refresh(key)
    return key, raw_key


async def list_api_keys(db: AsyncSession, *, tenant_id: uuid.UUID) -> list[ApiKey]:
    result = await db.execute(
        select(ApiKey).where(ApiKey.tenant_id == tenant_id).order_by(ApiKey.created_at)
    )
    return list(result.scalars().all())


async def get_api_key(db: AsyncSession, *, tenant_id: uuid.UUID, key_id: uuid.UUID) -> ApiKey:
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == tenant_id)
    )
    key = result.scalar_one_or_none()
    if key is None:
        raise ApiKeyNotFoundError(str(key_id))
    return key


async def revoke_api_key(db: AsyncSession, *, tenant_id: uuid.UUID, key_id: uuid.UUID) -> ApiKey:
    key = await get_api_key(db, tenant_id=tenant_id, key_id=key_id)
    key.is_active = False
    await db.commit()
    await db.refresh(key)
    return key


async def get_active_key_by_raw_value(db: AsyncSession, *, raw_key: str) -> ApiKey | None:
    """Look up a live key by its raw value — the one place this table is
    queried WITHOUT a tenant_id filter, because the key itself is what
    establishes which tenant a public-API request belongs to (same exception
    as ``get_current_user`` looking up a User by id straight from a JWT,
    before any tenant scope exists to filter by).
    """
    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == hash_api_key(raw_key), ApiKey.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def mark_used(db: AsyncSession, *, api_key: ApiKey) -> None:
    api_key.last_used_at = datetime.now(UTC)
    await db.commit()

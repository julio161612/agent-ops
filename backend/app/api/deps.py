import uuid
from collections.abc import Callable, Coroutine
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import TokenType, decode_token
from app.models.api_key import ApiKey, ApiKeyType
from app.models.user import User, UserRole
from app.services import api_key_service

_bearer_scheme = HTTPBearer(auto_error=True)

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

_INVALID_API_KEY_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid API key"
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decode the access token and load the authenticated user.

    This is the single place that turns a bearer token into a scoped identity:
    every protected route depends on this (directly or via get_current_tenant_id)
    to know which tenant_id it must filter all queries by.
    """
    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise _CREDENTIALS_ERROR from exc

    if payload.get("type") != TokenType.ACCESS.value:
        raise _CREDENTIALS_ERROR

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise _CREDENTIALS_ERROR from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise _CREDENTIALS_ERROR
    return user


async def get_current_tenant_id(current_user: User = Depends(get_current_user)) -> uuid.UUID:
    """Convenience dependency for routes/services that only need the tenant scope."""
    return current_user.tenant_id


# Least to most privileged. Each role includes everything the ones below it
# can do — there's no separate "grant" model, just a minimum bar per route.
_ROLE_RANK: dict[UserRole, int] = {
    UserRole.VIEWER: 0,
    UserRole.OPERATOR: 1,
    UserRole.ADMIN: 2,
}


def require_role(minimum_role: UserRole) -> Callable[[User], Coroutine[Any, Any, User]]:
    """FastAPI dependency factory: 403s unless the caller's role meets ``minimum_role``.

    Use as ``current_user: User = Depends(require_role(UserRole.OPERATOR))`` when
    the handler also needs the User object, or
    ``dependencies=[Depends(require_role(UserRole.OPERATOR))]`` on the route
    decorator when it only needs to gate access.
    """

    async def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if _ROLE_RANK[current_user.role] < _ROLE_RANK[minimum_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role '{minimum_role.value}' or higher "
                f"(current role: '{current_user.role.value}')",
            )
        return current_user

    return _dependency


async def get_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    """The public-API equivalent of get_current_user: turns an ``X-API-Key``
    header into a scoped identity (``api_key.tenant_id``), for routes end
    customers call directly — no JWT, no human user session.

    Touches ``last_used_at`` on every successful call (one extra UPDATE per
    request) — acceptable at this phase's traffic volume; batching/async-izing
    it would be the first thing to revisit if this endpoint gets hot.
    """
    if not x_api_key:
        raise _INVALID_API_KEY_ERROR
    api_key = await api_key_service.get_active_key_by_raw_value(db, raw_key=x_api_key)
    if api_key is None:
        raise _INVALID_API_KEY_ERROR
    await api_key_service.mark_used(db, api_key=api_key)
    return api_key


def require_send_message_key(api_key: ApiKey = Depends(get_api_key)) -> ApiKey:
    if not api_key.can_send_messages:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This API key cannot send messages"
        )
    return api_key


def require_server_key(api_key: ApiKey = Depends(get_api_key)) -> ApiKey:
    """Gate for public-API routes a WIDGET key must never reach (e.g. reading
    session history) — a widget key is meant to sit in public page source, so
    its capabilities are hard-capped at send-message regardless of any other
    permission flag.
    """
    if api_key.key_type != ApiKeyType.SERVER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This action requires a server API key"
        )
    return api_key

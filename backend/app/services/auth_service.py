import re
import uuid
from decimal import Decimal

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidTokenError,
)
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.tenant import Tenant
from app.models.tenant_limits import TenantLimits
from app.models.tenant_subscription import TenantSubscription
from app.models.user import User, UserRole
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services import subscription_service

_SLUG_INVALID_CHARS = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    base = _SLUG_INVALID_CHARS.sub("-", name.strip().lower()).strip("-") or "tenant"
    return f"{base}-{uuid.uuid4().hex[:8]}"


async def register_tenant_and_admin(
    db: AsyncSession, payload: RegisterRequest
) -> tuple[Tenant, User]:
    """Create a new tenant and its first admin user. Raises EmailAlreadyRegisteredError."""
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise EmailAlreadyRegisteredError(payload.email)

    tenant = Tenant(name=payload.company_name, slug=_slugify(payload.company_name))
    db.add(tenant)
    await db.flush()  # populate tenant.id

    user = User(
        tenant_id=tenant.id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=UserRole.ADMIN,
    )
    db.add(user)

    limits = TenantLimits(
        tenant_id=tenant.id,
        messages_per_minute_limit=settings.DEFAULT_MESSAGES_PER_MINUTE_LIMIT,
        monthly_cost_limit_usd=(
            Decimal(str(settings.DEFAULT_MONTHLY_COST_LIMIT_USD))
            if settings.DEFAULT_MONTHLY_COST_LIMIT_USD is not None
            else None
        ),
    )
    db.add(limits)

    free_plan = await subscription_service.get_plan_by_slug(db, slug="free")
    db.add(TenantSubscription(tenant_id=tenant.id, plan_id=free_plan.id))

    await db.commit()
    await db.refresh(tenant)
    await db.refresh(user)
    return tenant, user


async def authenticate_user(db: AsyncSession, payload: LoginRequest) -> User:
    """Verify credentials and return the matching user. Raises InvalidCredentialsError.

    A deactivated user (Phase 8) fails the same way as a wrong password —
    deliberately not a distinct error, so a login probe can't use the
    response to tell "wrong password" apart from "this account was
    deactivated" for a real email.
    """
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.hashed_password)
    ):
        raise InvalidCredentialsError()
    return user


def issue_tokens(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user_id=user.id, tenant_id=user.tenant_id),
        refresh_token=create_refresh_token(user_id=user.id, tenant_id=user.tenant_id),
    )


async def refresh_tokens(db: AsyncSession, *, refresh_token: str) -> TokenResponse:
    """Exchange a still-valid refresh token for a brand new access+refresh pair.

    Rotates the refresh token too (not just the access token) — a refresh
    token is long-lived (7 days), so reusing the same one indefinitely would
    make it as sensitive as a permanent credential; rotating it on every use
    caps how long a leaked-but-unused refresh token stays valid.
    """
    try:
        payload = decode_token(refresh_token)
    except jwt.PyJWTError as exc:
        raise InvalidTokenError() from exc

    if payload.get("type") != TokenType.REFRESH.value:
        raise InvalidTokenError()

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError() from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise InvalidTokenError()
    return issue_tokens(user)

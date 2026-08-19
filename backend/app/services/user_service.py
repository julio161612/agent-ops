import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    CannotModifySelfError,
    EmailAlreadyRegisteredError,
    LastActiveAdminError,
    PlanUserLimitExceededError,
    UserNotFoundError,
)
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.schemas.user import UserInvite
from app.services import subscription_service


async def _count_active_users(db: AsyncSession, *, tenant_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(User)
        .where(User.tenant_id == tenant_id, User.is_active.is_(True))
    )
    return result.scalar_one()


async def create_user(db: AsyncSession, *, tenant_id: uuid.UUID, payload: UserInvite) -> User:
    """Create a user directly in the tenant with an admin-chosen role and password.

    There's no email-invite flow (no outbound mail integration exists yet) —
    "invite" here means an admin sets the new teammate's initial password and
    hands it to them out of band, same as any first-run credential. Gated by
    the tenant's plan (Phase 10) — Enterprise's included_users=None means no
    limit at all; there's no reactivation endpoint (Phase 8), so unlike
    agents there's no "create inactive then flip active" loophole to close.
    """
    effective = await subscription_service.get_effective_limits(db, tenant_id=tenant_id)
    if effective.plan.included_users is not None:
        current_count = await _count_active_users(db, tenant_id=tenant_id)
        if current_count >= effective.plan.included_users:
            raise PlanUserLimitExceededError(
                f"The '{effective.plan.name}' plan includes {effective.plan.included_users} "
                f"user(s); this tenant already has {current_count}. Upgrade your plan to add more."
            )

    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise EmailAlreadyRegisteredError(payload.email)

    user = User(
        tenant_id=tenant_id,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def list_users(db: AsyncSession, *, tenant_id: uuid.UUID) -> list[User]:
    result = await db.execute(
        select(User).where(User.tenant_id == tenant_id).order_by(User.created_at)
    )
    return list(result.scalars().all())


async def get_user(db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id, User.tenant_id == tenant_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise UserNotFoundError(str(user_id))
    return user


async def _is_last_active_admin(
    db: AsyncSession, *, tenant_id: uuid.UUID, excluding_user_id: uuid.UUID
) -> bool:
    result = await db.execute(
        select(func.count())
        .select_from(User)
        .where(
            User.tenant_id == tenant_id,
            User.role == UserRole.ADMIN,
            User.is_active.is_(True),
            User.id != excluding_user_id,
        )
    )
    return result.scalar_one() == 0


async def update_user_role(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, new_role: UserRole
) -> User:
    user = await get_user(db, tenant_id=tenant_id, user_id=user_id)
    if (
        user.role == UserRole.ADMIN
        and new_role != UserRole.ADMIN
        and await _is_last_active_admin(db, tenant_id=tenant_id, excluding_user_id=user.id)
    ):
        raise LastActiveAdminError("Cannot change role: this is the tenant's last active admin")
    user.role = new_role
    await db.commit()
    await db.refresh(user)
    return user


async def deactivate_user(
    db: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID, acting_user_id: uuid.UUID
) -> User:
    """Deactivate a teammate. Never yourself — ask another admin, so a tenant
    can't accidentally lock itself out via a single self-deactivation call.
    """
    if user_id == acting_user_id:
        raise CannotModifySelfError("Cannot deactivate your own account")

    user = await get_user(db, tenant_id=tenant_id, user_id=user_id)
    if user.role == UserRole.ADMIN and await _is_last_active_admin(
        db, tenant_id=tenant_id, excluding_user_id=user.id
    ):
        raise LastActiveAdminError("Cannot deactivate: this is the tenant's last active admin")
    user.is_active = False
    await db.commit()
    await db.refresh(user)
    return user

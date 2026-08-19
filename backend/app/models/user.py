from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class UserRole(enum.StrEnum):
    """Ordered least-to-most privileged — see app.api.deps.require_role for the
    hierarchy this ordering encodes (ADMIN > OPERATOR > VIEWER, each level
    includes everything the levels below it can do).
    """

    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A user belonging to exactly one tenant.

    Note: unlike future platform tables, ``tenant_id`` is declared explicitly here
    (rather than via ``TenantScopedMixin``) because a user's tenant membership is
    part of its identity, not just a scoping column — it is set once at creation
    and used to look up the tenant on login, before any authenticated context
    exists.

    ``email`` is unique platform-wide (not per-tenant): login only takes an email
    and password, with no tenant identifier, so the email must unambiguously
    resolve to a single tenant.

    ``is_active`` (Phase 8): a deactivated user keeps their row (audit trail —
    who did what while they had access) but can no longer authenticate; see
    ``get_current_user``. There's no re-activation endpoint yet — deactivation
    is the only transition exposed, matching what was actually asked for.
    """

    __tablename__ = "users"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), nullable=False, default=UserRole.VIEWER
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    tenant: Mapped[Tenant] = relationship(back_populates="users", lazy="selectin")

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A client company using the platform. Root of the multi-tenant hierarchy.

    Which plan a tenant is on lives in ``TenantSubscription`` (Phase 10), not
    here — this used to have a decorative ``plan`` enum column (Phase 1) that
    was never actually read or enforced anywhere; real plan enforcement
    needed real plan data (price, included quotas, overage pricing), which a
    fixed enum can't hold. Removed rather than kept alongside the new model,
    to avoid two disagreeing answers to "what plan is this tenant on".
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    users: Mapped[list[User]] = relationship(back_populates="tenant", cascade="all, delete-orphan")

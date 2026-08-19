import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKeyMixin:
    """Adds a UUID primary key, generated client-side on insert."""

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """Adds created_at / updated_at columns, managed by the database."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TenantScopedMixin:
    """Marks a model as tenant-scoped data.

    Every table that stores platform data (agents, conversations, runs, guardrail
    events, etc.) MUST inherit this mixin and MUST filter every query by
    ``tenant_id``. There is no row-level security enforced by the database in this
    phase, so isolation is a hard convention: never write a query against a
    tenant-scoped table without a ``tenant_id`` filter derived from the
    authenticated request (see ``app.api.deps.get_current_tenant_id``).
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )


class SoftDeleteMixin:
    """Marks a row as soft-deletable via ``deleted_at`` instead of a physical DELETE.

    Services must filter reads by ``deleted_at IS NULL``; nothing enforces this at
    the database level.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin


class TenantIntegrations(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-tenant external integration config — one row per tenant, created
    lazily (same pattern as TenantLimits), kept separate from it because this
    is about *where things get sent*, not spend/rate configuration, and is
    the natural place to grow more integrations (email, PagerDuty...) without
    overloading TenantLimits.

    ``slack_webhook_url`` is itself a bearer secret (anyone with it can post
    into that Slack channel) — treated with the same care as an API key:
    accepted on write, never returned in full on read (see
    schemas.integrations for the masked read shape).
    """

    __tablename__ = "tenant_integrations"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    slack_webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

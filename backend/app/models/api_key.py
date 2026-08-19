from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ApiKeyType(enum.StrEnum):
    SERVER = "server"  # server-to-server: can send messages and read session history
    WIDGET = "widget"  # meant to sit in public HTML/JS — can only ever send messages


# Distinct, unmistakable prefixes (mirrors the Stripe sk_/pk_ convention) so a
# developer can never accidentally paste a widget key into a server-side
# secret store, or vice versa, and confuse the two at a glance.
API_KEY_PREFIXES: dict[ApiKeyType, str] = {
    ApiKeyType.SERVER: "ao_sk_",
    ApiKeyType.WIDGET: "ao_pk_",
}


class ApiKey(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """A tenant-scoped credential for the public API (``/public/v1/*``), distinct
    from the JWT user auth used everywhere else — this is what lets an
    end-customer's own backend or embedded widget talk to a tenant's agents
    without a human user session.

    The raw key is never stored — only ``key_hash`` (SHA-256 of the full raw
    key, not bcrypt: the key itself is 256 bits of random entropy, so unlike a
    password there's no brute-force risk from a fast, deterministic hash, and
    a deterministic hash is what makes an indexed ``WHERE key_hash = ?``
    lookup possible at all — bcrypt's per-hash random salt would rule that
    out). ``key_prefix`` is the first ~12 characters of the raw key, stored
    only so a listing can show *which* key is which without ever exposing the
    rest of it.

    ``key_type`` is the hard boundary between the two use cases the request
    asked for: SERVER keys can call both send-message and get-history;
    WIDGET keys — safe to embed in public page source — are restricted to
    send-message only, enforced in the public router, not just by convention.
    """

    __tablename__ = "api_keys"
    __table_args__ = (Index("ix_api_keys_tenant_key_type", "tenant_id", "key_type"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_type: Mapped[ApiKeyType] = mapped_column(
        Enum(ApiKeyType, name="api_key_type"), nullable=False, default=ApiKeyType.SERVER
    )
    key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    can_send_messages: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.message import Message


class ConversationStatus(enum.StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    ESCALATED = "escalated"  # wired up for real in Phase 5 (human handoff)
    UNASSIGNED = "unassigned"  # RoutingService couldn't find a confident agent match


class Conversation(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """A single conversation thread between an end user and one tenant Agent.

    ``agent_id`` is nullable: a conversation starts without one whenever the
    caller doesn't pass an explicit agent_id, until RoutingService assigns one
    (status flips from UNASSIGNED to OPEN). It can also stay unassigned forever,
    which Phase 5 will use as the escalate-to-human signal.

    ``external_user_id`` (Phase 9) is an opaque, client-chosen identifier for
    the end customer on the other end of a ``/public/v1/messages`` session —
    null for conversations that never went through the public API (internal
    JWT-authenticated traffic has no notion of "which end customer", only
    "which tenant user is operating the system").
    """

    __tablename__ = "conversations"

    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    status: Mapped[ConversationStatus] = mapped_column(
        Enum(ConversationStatus, name="conversation_status"),
        nullable=False,
        default=ConversationStatus.OPEN,
    )
    external_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    agent: Mapped[Agent | None] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )

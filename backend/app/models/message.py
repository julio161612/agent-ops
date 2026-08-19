from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.conversation import Conversation


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Message(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """A single turn in a Conversation.

    ``tenant_id`` is denormalized from the parent Conversation (rather than
    derived only via a join) so that every tenant-scoped query convention in
    this codebase — "filter by tenant_id" — holds uniformly across all platform
    tables, including this one, without relying on callers to remember to join
    through ``conversations``.
    """

    __tablename__ = "messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")

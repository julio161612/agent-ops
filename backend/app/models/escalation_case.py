from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class EscalationReason(enum.StrEnum):
    UNASSIGNED_ROUTING = "unassigned_routing"
    GUARDRAIL_BLOCKED = "guardrail_blocked"
    MANUAL = "manual"  # reserved for a future "agent asks for help" flow


class EscalationStatus(enum.StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"


class EscalationCase(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """A human-attention queue item for one Conversation.

    Created automatically (see AgentExecutionService) whenever a conversation
    lands in UNASSIGNED (routing couldn't find a confident agent) or ESCALATED
    (an output guardrail blocked the agent's reply) — at most one open
    (PENDING/IN_PROGRESS) case per conversation at a time; see
    escalation_service.create_if_not_exists.
    """

    __tablename__ = "escalation_cases"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reason: Mapped[EscalationReason] = mapped_column(
        Enum(EscalationReason, name="escalation_reason"), nullable=False
    )
    status: Mapped[EscalationStatus] = mapped_column(
        Enum(EscalationStatus, name="escalation_status"),
        nullable=False,
        default=EscalationStatus.PENDING,
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

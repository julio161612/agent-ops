from __future__ import annotations

import enum
import uuid

from sqlalchemy import Enum, Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class RoutingMethod(enum.StrEnum):
    RULE = "rule"
    LLM = "llm"


class RoutingDecision(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """An immutable audit record of one routing decision for a Conversation.

    One conversation can have several of these over time — e.g. a first message
    with no rule/LLM match leaves the conversation UNASSIGNED, and a follow-up
    message that does match creates a second decision. ``agent_id`` is null when
    routing failed to find a confident match. This is the data Phase 4's
    observability dashboard will read from.
    """

    __tablename__ = "routing_decisions"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    method: Mapped[RoutingMethod] = mapped_column(
        Enum(RoutingMethod, name="routing_method"), nullable=False
    )
    matched_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("routing_rules.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

from __future__ import annotations

import uuid

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.guardrail_policy import GuardrailAction, GuardrailRuleType, GuardrailType


class GuardrailViolation(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """An immutable audit record of one guardrail check that actually found something.

    ``detail`` deliberately never contains the raw offending text for
    PII-detection violations (only which pattern types were found) — logging
    the detected PII into the audit trail would defeat the point of detecting
    it. ``message_id`` is nullable and backfilled once the triggering/replaced
    message is persisted (see AgentExecutionService). ``trace_id`` is
    similarly backfilled once that turn's InteractionTrace is written (Phase
    7) — a direct link so trace detail views don't need to join through
    message_id, kept nullable/SET NULL so nothing here depends on Phase 7
    having run for older rows.
    """

    __tablename__ = "guardrail_violations"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trace_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interaction_traces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("guardrail_policies.id", ondelete="SET NULL"), nullable=True
    )
    guardrail_type: Mapped[GuardrailType] = mapped_column(
        Enum(GuardrailType, name="guardrail_type"), nullable=False
    )
    violation_type: Mapped[GuardrailRuleType] = mapped_column(
        Enum(GuardrailRuleType, name="guardrail_rule_type"), nullable=False
    )
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    action_taken: Mapped[GuardrailAction] = mapped_column(
        Enum(GuardrailAction, name="guardrail_action"), nullable=False
    )

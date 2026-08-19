from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.agent import Agent


class GuardrailType(enum.StrEnum):
    INPUT = "input"
    OUTPUT = "output"


class GuardrailRuleType(enum.StrEnum):
    BLOCKLIST_KEYWORDS = "blocklist_keywords"
    PII_DETECTION = "pii_detection"
    MAX_LENGTH = "max_length"
    CUSTOM_LLM_CHECK = "custom_llm_check"


class GuardrailAction(enum.StrEnum):
    BLOCK = "block"
    FLAG = "flag"


class GuardrailPolicy(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """A tenant-configured content/behavior check, run before (INPUT) or after
    (OUTPUT) an agent call. ``agent_id`` null means it applies to every agent
    of the tenant; set, it applies only to that one.
    """

    __tablename__ = "guardrail_policies"

    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    guardrail_type: Mapped[GuardrailType] = mapped_column(
        Enum(GuardrailType, name="guardrail_type"), nullable=False
    )
    rule_type: Mapped[GuardrailRuleType] = mapped_column(
        Enum(GuardrailRuleType, name="guardrail_rule_type"), nullable=False
    )
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    action_on_violation: Mapped[GuardrailAction] = mapped_column(
        Enum(GuardrailAction, name="guardrail_action"),
        nullable=False,
        default=GuardrailAction.BLOCK,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    agent: Mapped[Agent | None] = relationship()

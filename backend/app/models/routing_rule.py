from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Enum, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.agent import Agent


class RoutingRuleType(enum.StrEnum):
    KEYWORD = "keyword"
    CATEGORY = "category"


class RoutingRule(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """A tenant-configured fast-path routing rule, evaluated before the LLM router.

    - ``KEYWORD`` rules match when ``condition["keywords"]`` (a list of strings)
      contains a substring of the incoming message (case-insensitive).
    - ``CATEGORY`` rules match unconditionally on message content — they act as a
      configurable default/fallback for a given ``condition["agent_type"]``,
      matching as long as the target Agent is active and still tagged with that
      agent_type. This lets a tenant define "if nothing more specific matched,
      send it to the general-purpose agent" without spending an LLM call.

    Rules are evaluated ordered by ``priority`` descending (ties broken by
    creation order), and the first match wins.
    """

    __tablename__ = "routing_rules"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rule_type: Mapped[RoutingRuleType] = mapped_column(
        Enum(RoutingRuleType, name="routing_rule_type"), nullable=False
    )
    condition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    agent: Mapped[Agent] = relationship()

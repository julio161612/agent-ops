from __future__ import annotations

import enum
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import Enum, ForeignKey, Index, Integer, Numeric
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class TraceOutcome(enum.StrEnum):
    COMPLETED = "completed"  # the agent replied normally
    BLOCKED = "blocked"  # an INPUT guardrail stopped it before the agent ran
    ESCALATED = "escalated"  # an OUTPUT guardrail stopped the agent's reply from reaching the user
    UNASSIGNED = "unassigned"  # routing couldn't confidently pick an agent


class InteractionTrace(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    """One row per ``AgentExecutionService.send_message`` call — the unified,
    denormalized record observability/metrics queries are built on.

    Why a real table instead of a view over Message/RoutingDecision/
    GuardrailViolation/EscalationCase: two of the requested fields
    (per-stage latency breakdown, and a single true total cost per turn
    spanning routing + guardrail + execution calls) don't exist anywhere in
    those tables today — a view can only reshape data that already exists,
    it can't materialize timings nobody recorded. Since AgentExecutionService
    has to be instrumented to capture that regardless, writing the result
    into one row per turn is the natural, no-extra-cost consequence — not an
    additional design burden. The bigger win is on the read side: /metrics
    aggregates (sum cost, avg/p95 latency, count by outcome, group by agent)
    run as a single indexed scan over one flat table instead of joining
    several one-to-many tables (a message can have multiple guardrail
    violations — joining that naively into a SUM(cost)/AVG(latency) would
    double-count). That trade only gets more worth it as interaction volume
    grows, which is exactly when a view-based approach would start hurting.

    ``cost_usd`` is the interaction's TRUE total spend — read from the delta
    of tenant_limits.current_month_cost_usd across the whole turn, so it
    includes the routing LLM call and any custom_llm_check guardrail calls,
    not just the main agent reply. ``input_tokens``/``output_tokens`` are
    narrower: just the main agent-execution call's tokens (already tracked in
    Message.message_metadata, Phase 2), since that's the dominant, directly
    user-facing number — token counts for routing/guardrail sub-calls aren't
    separately broken out here (their cost still counts in cost_usd).
    """

    __tablename__ = "interaction_traces"
    __table_args__ = (
        Index("ix_interaction_traces_tenant_created", "tenant_id", "created_at"),
        Index("ix_interaction_traces_tenant_outcome", "tenant_id", "outcome"),
        Index("ix_interaction_traces_tenant_agent", "tenant_id", "agent_id"),
    )

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    user_message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    assistant_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    routing_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("routing_decisions.id", ondelete="SET NULL"), nullable=True
    )
    escalation_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("escalation_cases.id", ondelete="SET NULL"), nullable=True
    )
    outcome: Mapped[TraceOutcome] = mapped_column(
        Enum(TraceOutcome, name="trace_outcome"), nullable=False
    )
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False, default=Decimal("0"))
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    stage_latencies_ms: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

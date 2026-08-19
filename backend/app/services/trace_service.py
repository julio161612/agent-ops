import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InteractionTraceNotFoundError
from app.models.agent import Agent
from app.models.escalation_case import EscalationCase
from app.models.guardrail_violation import GuardrailViolation
from app.models.interaction_trace import InteractionTrace, TraceOutcome
from app.models.routing_decision import RoutingDecision

Granularity = Literal["hour", "day"]


@dataclass
class AgentUsageStat:
    agent_id: uuid.UUID | None
    agent_name: str | None
    interaction_count: int
    cost_usd: Decimal


@dataclass
class GuardrailTypeStat:
    violation_type: str
    violation_count: int


@dataclass
class SummaryMetrics:
    date_from: datetime
    date_to: datetime
    total_interactions: int
    completed: int
    blocked: int
    escalated: int
    unassigned: int
    total_cost_usd: Decimal
    latency_ms_avg: float | None
    latency_ms_p95: float | None
    agent_usage: list[AgentUsageStat]
    guardrail_violations_by_type: list[GuardrailTypeStat]

    @property
    def auto_resolution_rate(self) -> float:
        return self.completed / self.total_interactions if self.total_interactions else 0.0

    @property
    def escalation_rate(self) -> float:
        return self.escalated / self.total_interactions if self.total_interactions else 0.0


@dataclass
class TimeseriesBucket:
    bucket_start: datetime
    total_interactions: int
    completed: int
    blocked: int
    escalated: int
    unassigned: int
    total_cost_usd: Decimal
    latency_ms_avg: float | None


@dataclass
class TimeseriesMetrics:
    date_from: datetime
    date_to: datetime
    granularity: Granularity
    buckets: list[TimeseriesBucket] = field(default_factory=list)


async def record_trace(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    user_message_id: uuid.UUID,
    assistant_message_id: uuid.UUID | None,
    agent_id: uuid.UUID | None,
    routing_decision_id: uuid.UUID | None,
    escalation_case_id: uuid.UUID | None,
    outcome: TraceOutcome,
    cost_usd: Decimal,
    input_tokens: int,
    output_tokens: int,
    total_latency_ms: int,
    stage_latencies_ms: dict[str, int],
) -> InteractionTrace:
    """Write one InteractionTrace row for a completed AgentExecutionService.send_message call."""
    trace = InteractionTrace(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        agent_id=agent_id,
        routing_decision_id=routing_decision_id,
        escalation_case_id=escalation_case_id,
        outcome=outcome,
        cost_usd=cost_usd,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_latency_ms=total_latency_ms,
        stage_latencies_ms=stage_latencies_ms,
    )
    db.add(trace)
    await db.flush()
    return trace


async def get_trace(
    db: AsyncSession, *, tenant_id: uuid.UUID, trace_id: uuid.UUID
) -> InteractionTrace:
    result = await db.execute(
        select(InteractionTrace).where(
            InteractionTrace.id == trace_id, InteractionTrace.tenant_id == tenant_id
        )
    )
    trace = result.scalar_one_or_none()
    if trace is None:
        raise InteractionTraceNotFoundError(str(trace_id))
    return trace


@dataclass
class TraceDetail:
    trace: InteractionTrace
    guardrail_violations: list[GuardrailViolation]
    routing_decision: RoutingDecision | None
    escalation_case: EscalationCase | None


async def get_trace_detail(
    db: AsyncSession, *, tenant_id: uuid.UUID, trace_id: uuid.UUID
) -> TraceDetail:
    trace = await get_trace(db, tenant_id=tenant_id, trace_id=trace_id)

    violations_result = await db.execute(
        select(GuardrailViolation)
        .where(GuardrailViolation.tenant_id == tenant_id, GuardrailViolation.trace_id == trace.id)
        .order_by(GuardrailViolation.created_at)
    )
    violations = list(violations_result.scalars().all())

    routing_decision = (
        await db.get(RoutingDecision, trace.routing_decision_id)
        if trace.routing_decision_id is not None
        else None
    )
    escalation_case = (
        await db.get(EscalationCase, trace.escalation_case_id)
        if trace.escalation_case_id is not None
        else None
    )

    return TraceDetail(
        trace=trace,
        guardrail_violations=violations,
        routing_decision=routing_decision,
        escalation_case=escalation_case,
    )


async def list_traces(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    outcome: TraceOutcome | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[InteractionTrace], int]:
    filters = [InteractionTrace.tenant_id == tenant_id]
    if conversation_id is not None:
        filters.append(InteractionTrace.conversation_id == conversation_id)
    if outcome is not None:
        filters.append(InteractionTrace.outcome == outcome)
    if date_from is not None:
        filters.append(InteractionTrace.created_at >= date_from)
    if date_to is not None:
        filters.append(InteractionTrace.created_at <= date_to)

    count_result = await db.execute(
        select(func.count()).select_from(InteractionTrace).where(*filters)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(InteractionTrace)
        .where(*filters)
        .order_by(InteractionTrace.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), total


async def get_summary_metrics(
    db: AsyncSession, *, tenant_id: uuid.UUID, date_from: datetime, date_to: datetime
) -> SummaryMetrics:
    filters = [
        InteractionTrace.tenant_id == tenant_id,
        InteractionTrace.created_at >= date_from,
        InteractionTrace.created_at <= date_to,
    ]

    outcome_result = await db.execute(
        select(InteractionTrace.outcome, func.count())
        .where(*filters)
        .group_by(InteractionTrace.outcome)
    )
    outcome_counts = {outcome.value: count for outcome, count in outcome_result.all()}
    total = sum(outcome_counts.values())

    agg_result = await db.execute(
        select(
            func.coalesce(func.sum(InteractionTrace.cost_usd), 0),
            func.avg(InteractionTrace.total_latency_ms),
            func.percentile_cont(0.95).within_group(InteractionTrace.total_latency_ms),
        ).where(*filters)
    )
    total_cost, latency_avg, latency_p95 = agg_result.one()

    agent_usage_result = await db.execute(
        select(
            InteractionTrace.agent_id,
            Agent.name,
            func.count(),
            func.coalesce(func.sum(InteractionTrace.cost_usd), 0),
        )
        .outerjoin(Agent, Agent.id == InteractionTrace.agent_id)
        .where(*filters)
        .group_by(InteractionTrace.agent_id, Agent.name)
        .order_by(func.count().desc())
    )
    agent_usage = [
        AgentUsageStat(agent_id=agent_id, agent_name=name, interaction_count=count, cost_usd=cost)
        for agent_id, name, count, cost in agent_usage_result.all()
    ]

    violation_result = await db.execute(
        select(GuardrailViolation.violation_type, func.count())
        .where(
            GuardrailViolation.tenant_id == tenant_id,
            GuardrailViolation.created_at >= date_from,
            GuardrailViolation.created_at <= date_to,
        )
        .group_by(GuardrailViolation.violation_type)
        .order_by(func.count().desc())
    )
    guardrail_violations_by_type = [
        GuardrailTypeStat(violation_type=violation_type.value, violation_count=count)
        for violation_type, count in violation_result.all()
    ]

    return SummaryMetrics(
        date_from=date_from,
        date_to=date_to,
        total_interactions=total,
        completed=outcome_counts.get(TraceOutcome.COMPLETED.value, 0),
        blocked=outcome_counts.get(TraceOutcome.BLOCKED.value, 0),
        escalated=outcome_counts.get(TraceOutcome.ESCALATED.value, 0),
        unassigned=outcome_counts.get(TraceOutcome.UNASSIGNED.value, 0),
        total_cost_usd=total_cost,
        latency_ms_avg=float(latency_avg) if latency_avg is not None else None,
        latency_ms_p95=float(latency_p95) if latency_p95 is not None else None,
        agent_usage=agent_usage,
        guardrail_violations_by_type=guardrail_violations_by_type,
    )


async def get_timeseries_metrics(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    date_from: datetime,
    date_to: datetime,
    granularity: Granularity = "day",
) -> TimeseriesMetrics:
    filters = [
        InteractionTrace.tenant_id == tenant_id,
        InteractionTrace.created_at >= date_from,
        InteractionTrace.created_at <= date_to,
    ]
    bucket_expr = func.date_trunc(granularity, InteractionTrace.created_at)

    totals_result = await db.execute(
        select(
            bucket_expr.label("bucket"),
            func.count(),
            func.coalesce(func.sum(InteractionTrace.cost_usd), 0),
            func.avg(InteractionTrace.total_latency_ms),
        )
        .where(*filters)
        .group_by(bucket_expr)
        .order_by(bucket_expr)
    )
    totals_rows = totals_result.all()

    outcome_result = await db.execute(
        select(bucket_expr.label("bucket"), InteractionTrace.outcome, func.count())
        .where(*filters)
        .group_by(bucket_expr, InteractionTrace.outcome)
    )
    outcome_by_bucket: dict[Any, dict[str, int]] = {}
    for bucket_start, outcome, count in outcome_result.all():
        outcome_by_bucket.setdefault(bucket_start, {})[outcome.value] = count

    buckets = [
        TimeseriesBucket(
            bucket_start=bucket_start,
            total_interactions=total,
            completed=outcome_by_bucket.get(bucket_start, {}).get(TraceOutcome.COMPLETED.value, 0),
            blocked=outcome_by_bucket.get(bucket_start, {}).get(TraceOutcome.BLOCKED.value, 0),
            escalated=outcome_by_bucket.get(bucket_start, {}).get(TraceOutcome.ESCALATED.value, 0),
            unassigned=outcome_by_bucket.get(bucket_start, {}).get(
                TraceOutcome.UNASSIGNED.value, 0
            ),
            total_cost_usd=cost,
            latency_ms_avg=float(latency_avg) if latency_avg is not None else None,
        )
        for bucket_start, total, cost, latency_avg in totals_rows
    ]

    return TimeseriesMetrics(
        date_from=date_from, date_to=date_to, granularity=granularity, buckets=buckets
    )

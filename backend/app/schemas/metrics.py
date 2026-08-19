import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class AgentUsageStatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    agent_id: uuid.UUID | None
    agent_name: str | None
    interaction_count: int
    cost_usd: Decimal


class GuardrailTypeStatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    violation_type: str
    violation_count: int


class MetricsSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date_from: datetime
    date_to: datetime
    total_interactions: int
    completed: int
    blocked: int
    escalated: int
    unassigned: int
    auto_resolution_rate: float
    escalation_rate: float
    total_cost_usd: Decimal
    latency_ms_avg: float | None
    latency_ms_p95: float | None
    agent_usage: list[AgentUsageStatRead]
    guardrail_violations_by_type: list[GuardrailTypeStatRead]


class TimeseriesBucketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bucket_start: datetime
    total_interactions: int
    completed: int
    blocked: int
    escalated: int
    unassigned: int
    total_cost_usd: Decimal
    latency_ms_avg: float | None


class MetricsTimeseriesRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    date_from: datetime
    date_to: datetime
    granularity: str
    buckets: list[TimeseriesBucketRead]

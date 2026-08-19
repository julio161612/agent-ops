import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class EvalCaseResultRead(BaseModel):
    id: str
    category: str
    message: str
    conversation_status: str
    assigned_agent: str | None
    routing_method: str | None
    routing_confidence: float | None
    expected_agent: str | None
    routing_correct: bool | None
    violations: list[dict[str, str]]
    guardrail_expected_trigger: bool
    guardrail_correct: bool
    assistant_reply: str | None
    latency_ms: float
    error: str | None
    judge: dict[str, Any] | None


class EvalSummary(BaseModel):
    total_cases: int
    errors: int
    routing_accuracy: float | None
    routing_cases_scored: int
    guardrail_accuracy: float
    guardrail_false_positives: int
    guardrail_false_negatives: int
    latency_ms_avg: float | None
    latency_ms_p95: float | None
    total_cost_usd: float | None
    judged_cases: int
    judge_score_avg: float | None


class RoutingProbeEntry(BaseModel):
    message: str
    conversation_status: str | None = None
    routing: dict[str, Any] | None = None
    error: str | None = None


class EvalRunResponse(BaseModel):
    run_id: str
    started_at: datetime
    finished_at: datetime
    tenant_id: uuid.UUID
    scope: str
    summary: EvalSummary
    results: list[EvalCaseResultRead]
    routing_probe: list[RoutingProbeEntry]

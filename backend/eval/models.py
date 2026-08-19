from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RoutingExpectation:
    agent: str | None = None  # logical agent name, "none", or None (don't score routing)
    routing_method: str | None = None  # "rule" | "llm" | None (don't check the method)


@dataclass
class GuardrailExpectation:
    expect_trigger: bool = False
    rule_type: str | None = None
    expect_action: str | None = None  # "block" | "flag"


@dataclass
class EvalCase:
    id: str
    category: str
    description: str
    message: str
    expected_routing: RoutingExpectation
    guardrail: GuardrailExpectation
    response_quality: str | None = None
    regression_subset: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> EvalCase:
        expected = raw.get("expected") or {}
        guardrail = raw.get("guardrail") or {}
        return cls(
            id=raw["id"],
            category=raw["category"],
            description=raw.get("description", ""),
            message=raw["input"]["message"],
            expected_routing=RoutingExpectation(
                agent=expected.get("agent"),
                routing_method=expected.get("routing_method"),
            ),
            guardrail=GuardrailExpectation(
                expect_trigger=bool(guardrail.get("expect_trigger", False)),
                rule_type=guardrail.get("rule_type"),
                expect_action=guardrail.get("expect_action"),
            ),
            response_quality=raw.get("response_quality"),
            regression_subset=bool(raw.get("regression_subset", False)),
        )


@dataclass
class ViolationRecord:
    rule_type: str
    action: str


@dataclass
class JudgeResult:
    score: int  # 1 (bad) .. 5 (excellent)
    justification: str

    def to_dict(self) -> dict[str, Any]:
        return {"score": self.score, "justification": self.justification}


@dataclass
class CaseResult:
    case: EvalCase
    conversation_status: str
    assigned_agent: str | None  # logical name, or None if unassigned
    routing_method: str | None
    routing_confidence: float | None
    violations: list[ViolationRecord]
    assistant_reply: str | None
    latency_ms: float
    routing_correct: bool | None  # None = not scored (case didn't assert an expected agent)
    guardrail_correct: bool
    error: str | None = None
    judge: JudgeResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.case.id,
            "category": self.case.category,
            "message": self.case.message,
            "conversation_status": self.conversation_status,
            "assigned_agent": self.assigned_agent,
            "routing_method": self.routing_method,
            "routing_confidence": self.routing_confidence,
            "expected_agent": self.case.expected_routing.agent,
            "routing_correct": self.routing_correct,
            "violations": [{"rule_type": v.rule_type, "action": v.action} for v in self.violations],
            "guardrail_expected_trigger": self.case.guardrail.expect_trigger,
            "guardrail_correct": self.guardrail_correct,
            "assistant_reply": self.assistant_reply,
            "latency_ms": round(self.latency_ms, 1),
            "error": self.error,
            "judge": self.judge.to_dict() if self.judge else None,
        }


@dataclass
class EvalReport:
    run_id: str
    started_at: datetime
    finished_at: datetime
    tenant_id: str
    results: list[CaseResult] = field(default_factory=list)

    # --- aggregate metrics, computed lazily from `results` -------------------

    @property
    def total_cases(self) -> int:
        return len(self.results)

    @property
    def routing_scored(self) -> list[CaseResult]:
        return [r for r in self.results if r.routing_correct is not None]

    @property
    def routing_accuracy(self) -> float | None:
        scored = self.routing_scored
        if not scored:
            return None
        return sum(1 for r in scored if r.routing_correct) / len(scored)

    @property
    def guardrail_accuracy(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.guardrail_correct) / len(self.results)

    @property
    def guardrail_false_positives(self) -> int:
        """Triggered when it shouldn't have."""
        return sum(
            1
            for r in self.results
            if not r.guardrail_correct and not r.case.guardrail.expect_trigger
        )

    @property
    def guardrail_false_negatives(self) -> int:
        """Didn't trigger when it should have."""
        return sum(
            1 for r in self.results if not r.guardrail_correct and r.case.guardrail.expect_trigger
        )

    @property
    def latencies_ms(self) -> list[float]:
        return sorted(r.latency_ms for r in self.results if r.error is None)

    @property
    def latency_ms_avg(self) -> float | None:
        lats = self.latencies_ms
        return sum(lats) / len(lats) if lats else None

    @property
    def latency_ms_p95(self) -> float | None:
        lats = self.latencies_ms
        if not lats:
            return None
        index = min(len(lats) - 1, int(round(0.95 * (len(lats) - 1))))
        return lats[index]

    @property
    def judged_results(self) -> list[CaseResult]:
        return [r for r in self.results if r.judge is not None]

    @property
    def judge_score_avg(self) -> float | None:
        judged = self.judged_results
        if not judged:
            return None
        return sum(r.judge.score for r in judged) / len(judged)

    @property
    def errors(self) -> list[CaseResult]:
        return [r for r in self.results if r.error is not None]

    def to_dict(self, *, total_cost_usd: float | None = None) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "tenant_id": self.tenant_id,
            "summary": {
                "total_cases": self.total_cases,
                "errors": len(self.errors),
                "routing_accuracy": self.routing_accuracy,
                "routing_cases_scored": len(self.routing_scored),
                "guardrail_accuracy": self.guardrail_accuracy,
                "guardrail_false_positives": self.guardrail_false_positives,
                "guardrail_false_negatives": self.guardrail_false_negatives,
                "latency_ms_avg": self.latency_ms_avg,
                "latency_ms_p95": self.latency_ms_p95,
                "total_cost_usd": total_cost_usd,
                "judged_cases": len(self.judged_results),
                "judge_score_avg": self.judge_score_avg,
            },
            "results": [r.to_dict() for r in self.results],
        }

    def to_markdown(self, *, total_cost_usd: float | None = None) -> str:
        routing_pct = _fmt_pct(self.routing_accuracy)
        guardrail_pct = _fmt_pct(self.guardrail_accuracy)
        latency_avg = _fmt_ms(self.latency_ms_avg)
        latency_p95 = _fmt_ms(self.latency_ms_p95)
        cost_cell = f"${total_cost_usd:.4f}" if total_cost_usd is not None else "n/a"
        judge_cell = f"{self.judge_score_avg:.2f}/5" if self.judge_score_avg else "n/a"

        lines = [
            f"# Agent Ops — Eval report `{self.run_id}`",
            "",
            f"- Tenant: `{self.tenant_id}`",
            f"- Started: {self.started_at.isoformat()}",
            f"- Finished: {self.finished_at.isoformat()}",
            f"- Total cases: {self.total_cases} ({len(self.errors)} errored)",
            "",
            "## Summary",
            "",
            "| Metric | Value |",
            "|---|---|",
            f"| Routing accuracy | {routing_pct} ({len(self.routing_scored)} scored) |",
            f"| Guardrail accuracy | {guardrail_pct} |",
            f"| Guardrail false positives | {self.guardrail_false_positives} |",
            f"| Guardrail false negatives | {self.guardrail_false_negatives} |",
            f"| Latency avg / p95 | {latency_avg} / {latency_p95} |",
            f"| Total cost (USD) | {cost_cell} |",
            f"| LLM-judge avg score | {judge_cell} ({len(self.judged_results)} judged) |",
            "",
        ]

        if self.errors:
            lines += ["## Errors", ""]
            for r in self.errors:
                lines.append(f"- `{r.case.id}`: {r.error}")
            lines.append("")

        by_category: dict[str, list[CaseResult]] = {}
        for r in self.results:
            by_category.setdefault(r.case.category, []).append(r)

        lines += ["## Cases by category", ""]
        for category, cases in sorted(by_category.items()):
            lines.append(f"### {category} ({len(cases)})")
            lines.append("")
            lines.append("| id | routing | guardrail | judge | latency |")
            lines.append("|---|---|---|---|---|")
            for r in cases:
                routing_cell = (
                    "—" if r.routing_correct is None else ("✅" if r.routing_correct else "❌")
                )
                guardrail_cell = "✅" if r.guardrail_correct else "❌"
                judge_cell = f"{r.judge.score}/5" if r.judge else "—"
                lines.append(
                    f"| {r.case.id} | {routing_cell} | {guardrail_cell} | {judge_cell} "
                    f"| {r.latency_ms:.0f}ms |"
                )
            lines.append("")

        return "\n".join(lines)


def _fmt_pct(value: float | None) -> str:
    return f"{value * 100:.1f}%" if value is not None else "n/a"


def _fmt_ms(value: float | None) -> str:
    return f"{value:.0f}ms" if value is not None else "n/a"

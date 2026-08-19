"""Golden-dataset evaluation engine for Agent Ops.

Runs against the real FastAPI app **in-process** (httpx + ASGITransport)
rather than requiring a separately-running server. This was a deliberate
choice over spinning up `uvicorn` and hitting it over real HTTP:

- It exercises the exact same code path a real client would (routing,
  guardrails, cost tracking, persistence) — ASGITransport calls the actual
  ASGI app, it isn't a shortcut around it.
- No process/port management, no "is the server up yet" polling, no extra
  moving part to keep alive during a CI run — just `python -m eval.runner`.
- It's the same pattern already used by every manual verification pass in
  this project's phases 2-5, so there's nothing new to learn here.

It still needs Postgres + Redis reachable (`docker compose up -d postgres
redis`) and a real `ANTHROPIC_API_KEY`, because this evaluates real model
behavior — there is no mocked mode for the full run (see
tests/test_eval_regression.py for the fast, free, mocked subset).
"""

import argparse
import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import anthropic
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from eval.environment import create_environment
from eval.judge import judge_response
from eval.models import CaseResult, EvalCase, EvalReport, ViolationRecord

DATASET_PATH = Path(__file__).parent / "data" / "golden_dataset.yaml"
REPORTS_DIR = Path(__file__).parent / "reports"

# Categories safe to run against an arbitrary tenant's own agents (see
# run_tenant_eval): these are all evaluated at the INPUT stage, before
# routing, so they never depend on which (if any) agent gets assigned.
# routing_keyword/routing_llm/routing_none assert a specific *logical* agent
# name from eval/environment.py's fixture — meaningless against a real
# tenant's own agent naming. guardrail_custom_llm_check is an OUTPUT check,
# so it only fires if some agent actually runs — too fragile to rely on
# without controlling routing, so it's excluded from tenant-scoped runs too.
TENANT_SAFE_CATEGORIES = {
    "guardrail_blocklist",
    "guardrail_pii",
    "guardrail_max_length",
    "edge_case",
}

_ROUTING_PROBE_MESSAGES = [
    "Tengo una pregunta sobre mi cuenta.",
    "¿Podéis ayudarme con un problema general?",
    "Necesito hablar con alguien del equipo de soporte.",
]


def load_dataset(path: Path = DATASET_PATH) -> list[EvalCase]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [EvalCase.from_dict(item) for item in raw]


def _score_guardrail(case: EvalCase, violations: list[ViolationRecord]) -> bool:
    expectation = case.guardrail
    if not expectation.expect_trigger:
        return len(violations) == 0
    return any(
        v.rule_type == expectation.rule_type
        and (expectation.expect_action is None or v.action == expectation.expect_action)
        for v in violations
    )


async def _get_tenant_cost_usd(client: AsyncClient, headers: dict[str, str]) -> Decimal:
    response = await client.get("/api/v1/tenant-limits", headers=headers)
    response.raise_for_status()
    return Decimal(str(response.json()["current_month_cost_usd"]))


async def _run_single_case(
    *,
    client: AsyncClient,
    headers: dict[str, str],
    case: EvalCase,
    agent_name_by_id: dict[str, str],
    score_routing: bool,
) -> CaseResult:
    conversation_id = uuid.uuid4()
    started = time.monotonic()
    try:
        response = await client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"content": case.message},
            headers=headers,
        )
        latency_ms = (time.monotonic() - started) * 1000
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 — a failed case is a result, not a crash
        latency_ms = (time.monotonic() - started) * 1000
        return CaseResult(
            case=case,
            conversation_status="error",
            assigned_agent=None,
            routing_method=None,
            routing_confidence=None,
            violations=[],
            assistant_reply=None,
            latency_ms=latency_ms,
            routing_correct=None,
            guardrail_correct=False,
            error=str(exc),
        )

    body = response.json()
    routing = body.get("routing") or {}
    assigned_agent_id = routing.get("agent_id")
    assigned_agent = None
    if assigned_agent_id is not None:
        assigned_agent = (
            agent_name_by_id.get(assigned_agent_id, assigned_agent_id)
            if score_routing
            else assigned_agent_id
        )

    routing_correct = None
    if score_routing and case.expected_routing.agent is not None:
        routing_correct = case.expected_routing.agent == (assigned_agent or "none")

    violations = [
        ViolationRecord(rule_type=v["violation_type"], action=v["action_taken"])
        for v in body.get("guardrail_violations", [])
    ]
    assistant_message = body.get("assistant_message")

    return CaseResult(
        case=case,
        conversation_status=body["conversation_status"],
        assigned_agent=assigned_agent,
        routing_method=routing.get("method"),
        routing_confidence=routing.get("confidence"),
        violations=violations,
        assistant_reply=assistant_message["content"] if assistant_message else None,
        latency_ms=latency_ms,
        routing_correct=routing_correct,
        guardrail_correct=_score_guardrail(case, violations),
    )


async def run_cases(
    *,
    client: AsyncClient,
    headers: dict[str, str],
    tenant_id: uuid.UUID,
    cases: list[EvalCase],
    agent_name_by_id: dict[str, str] | None = None,
    score_routing: bool = True,
    run_judge: bool = True,
    anthropic_client: anthropic.AsyncAnthropic | None = None,
    db: AsyncSession | None = None,
) -> EvalReport:
    """Run ``cases`` and score them.

    ``anthropic_client`` is used only for the LLM-judge step (the HTTP calls
    to send messages always go through the app's own dependency-injected
    client — this parameter exists so tests/test_eval_regression.py can pass
    the same fake client used for the HTTP-level mock into the judge step
    too, since a direct function call like this bypasses FastAPI's
    ``dependency_overrides`` entirely). Defaults to the real cached client.

    ``db`` is used only to record judge-call cost. If given, it's reused
    as-is for every judge call — the /eval/run endpoint passes its own
    request-scoped, dependency-injected session, which is what makes this
    safe to call from inside a live request. If omitted (the CLI runner's
    case), a fresh session bound to ``settings.DATABASE_URL`` is opened per
    judge call.
    """
    from app.core.anthropic_client import get_anthropic_client
    from app.core.database import AsyncSessionLocal

    started_at = datetime.now(UTC)
    anthropic_client = anthropic_client or get_anthropic_client()
    results: list[CaseResult] = []

    for case in cases:
        result = await _run_single_case(
            client=client,
            headers=headers,
            case=case,
            agent_name_by_id=agent_name_by_id or {},
            score_routing=score_routing,
        )
        if run_judge and case.response_quality and result.assistant_reply and result.error is None:
            try:
                if db is not None:
                    result.judge = await judge_response(
                        anthropic_client=anthropic_client,
                        db=db,
                        tenant_id=tenant_id,
                        user_message=case.message,
                        assistant_reply=result.assistant_reply,
                        criterion=case.response_quality,
                    )
                else:
                    async with AsyncSessionLocal() as fresh_db:
                        result.judge = await judge_response(
                            anthropic_client=anthropic_client,
                            db=fresh_db,
                            tenant_id=tenant_id,
                            user_message=case.message,
                            assistant_reply=result.assistant_reply,
                            criterion=case.response_quality,
                        )
            except Exception:  # noqa: BLE001 — a failed judge call shouldn't kill the run
                result.judge = None
        results.append(result)

    return EvalReport(
        run_id=f"eval-{started_at.strftime('%Y%m%d-%H%M%S')}",
        started_at=started_at,
        finished_at=datetime.now(UTC),
        tenant_id=str(tenant_id),
        results=results,
    )


@dataclass
class TenantEvalOutcome:
    report: EvalReport
    routing_probe: list[dict[str, Any]]
    total_cost_usd: float


async def run_tenant_eval(
    *,
    client: AsyncClient,
    headers: dict[str, str],
    tenant_id: uuid.UUID,
    dataset_path: Path = DATASET_PATH,
    db: AsyncSession | None = None,
) -> TenantEvalOutcome:
    """Evaluate guardrail behavior + basic robustness against the CALLING
    tenant's OWN configured agents/policies — see TENANT_SAFE_CATEGORIES for
    why routing isn't scored here. Never touches the tenant's rate/cost
    limits; if those are tight enough to reject some eval traffic, that's
    real signal, not a run-time obstacle to route around.

    ``db``: see run_cases — the /eval/run endpoint passes its own
    request-scoped session through here.
    """
    cases = [c for c in load_dataset(dataset_path) if c.category in TENANT_SAFE_CATEGORIES]

    cost_before = await _get_tenant_cost_usd(client, headers)
    report = await run_cases(
        client=client,
        headers=headers,
        tenant_id=tenant_id,
        cases=cases,
        agent_name_by_id=None,
        score_routing=False,
        run_judge=True,
        db=db,
    )

    routing_probe: list[dict[str, Any]] = []
    for message in _ROUTING_PROBE_MESSAGES:
        response = await client.post(
            f"/api/v1/conversations/{uuid.uuid4()}/messages",
            json={"content": message},
            headers=headers,
        )
        if response.status_code == 200:
            body = response.json()
            routing_probe.append(
                {
                    "message": message,
                    "conversation_status": body["conversation_status"],
                    "routing": body.get("routing"),
                }
            )
        else:
            routing_probe.append({"message": message, "error": response.text})

    cost_after = await _get_tenant_cost_usd(client, headers)
    return TenantEvalOutcome(
        report=report, routing_probe=routing_probe, total_cost_usd=float(cost_after - cost_before)
    )


@dataclass
class FullEvalOutcome:
    report: EvalReport
    total_cost_usd: float
    json_path: Path
    md_path: Path


async def run_full_eval(
    *, dataset_path: Path = DATASET_PATH, output_dir: Path = REPORTS_DIR
) -> FullEvalOutcome:
    """CLI entry point's core: fresh eval-only tenant, full canonical
    environment (eval/environment.py), full dataset, real Anthropic calls.
    """
    from app.main import app

    cases = load_dataset(dataset_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://eval") as client:
        register = await client.post(
            "/api/v1/auth/register",
            json={
                "company_name": f"Eval Tenant {uuid.uuid4().hex[:8]}",
                "email": f"eval-{uuid.uuid4().hex[:8]}@example.com",
                "password": "supersecret123",
            },
        )
        register.raise_for_status()
        headers = {"Authorization": f"Bearer {register.json()['access_token']}"}
        me = (await client.get("/api/v1/auth/me", headers=headers)).json()
        tenant_id = uuid.UUID(me["tenant"]["id"])

        # Throwaway tenant created solely for this run — every tenant starts
        # on Free (Phase 10: 1 agent, 10 msg/min, 100 msg/month included),
        # which the golden dataset's 3-agent environment and full run blow
        # through immediately. Move it to Enterprise (no plan ceilings) before
        # touching tenant-limits or creating agents.
        plans = (await client.get("/api/v1/plans", headers=headers)).json()
        enterprise_plan_id = next(p["id"] for p in plans if p["slug"] == "enterprise")
        await client.post(
            "/api/v1/subscription/change-plan",
            json={"plan_id": enterprise_plan_id},
            headers=headers,
        )
        await client.patch(
            "/api/v1/tenant-limits", json={"messages_per_minute_limit": 1000}, headers=headers
        )

        environment = await create_environment(client, headers)
        agent_name_by_id = {v: k for k, v in environment.agent_ids.items()}

        cost_before = await _get_tenant_cost_usd(client, headers)
        report = await run_cases(
            client=client,
            headers=headers,
            tenant_id=tenant_id,
            cases=cases,
            agent_name_by_id=agent_name_by_id,
            score_routing=True,
            run_judge=True,
        )
        cost_after = await _get_tenant_cost_usd(client, headers)

    total_cost_usd = float(cost_after - cost_before)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{report.run_id}.json"
    md_path = output_dir / f"{report.run_id}.md"
    json_path.write_text(
        json.dumps(report.to_dict(total_cost_usd=total_cost_usd), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    md_path.write_text(report.to_markdown(total_cost_usd=total_cost_usd), encoding="utf-8")

    return FullEvalOutcome(
        report=report, total_cost_usd=total_cost_usd, json_path=json_path, md_path=md_path
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Agent Ops golden-dataset evaluation.")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    parser.add_argument("--output-dir", type=Path, default=REPORTS_DIR)
    args = parser.parse_args()

    outcome = asyncio.run(run_full_eval(dataset_path=args.dataset, output_dir=args.output_dir))
    print(outcome.report.to_markdown(total_cost_usd=outcome.total_cost_usd))
    print(f"\nFull JSON report: {outcome.json_path}")
    print(f"Markdown report:  {outcome.md_path}")


if __name__ == "__main__":
    main()

"""Fast, free, deterministic regression check for the eval pipeline's plumbing.

Runs a small hand-picked subset of eval/data/golden_dataset.yaml (the cases
tagged `regression_subset: true`) against the SAME fixture environment used
by the real evaluation (eval/environment.py), through the real routing and
guardrail pipeline — but with the Anthropic client mocked, via
ScriptedAnthropicClient (see tests/helpers.py), so it costs nothing and needs
no network. This is not a test of AI quality — it can't be, without a real
model — it's a regression guard for the mechanics: did a code change silently
break how routing/guardrail signals flow through the pipeline. The real
quality signal only comes from `python -m eval.runner` against the live API.
"""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from eval.environment import create_environment
from eval.runner import load_dataset, run_cases
from tests.helpers import (
    ScriptedAnthropicClient,
    auth_headers,
    register_tenant,
    upgrade_to_enterprise_plan,
)


async def test_regression_subset_routing_and_guardrails(
    client: AsyncClient,
    scripted_anthropic_client: ScriptedAnthropicClient,
    db_session: AsyncSession,
) -> None:
    cases = [c for c in load_dataset() if c.regression_subset]
    assert 5 <= len(cases) <= 8, "keep the regression subset small and fast"

    tokens = await register_tenant(client)
    headers = auth_headers(tokens["access_token"])
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    tenant_id = uuid.UUID(me["tenant"]["id"])
    # eval/environment.py's canonical fixture needs 3 agents — Free's
    # included_active_agents=1 (Phase 10) would block that immediately.
    await upgrade_to_enterprise_plan(client, tokens["access_token"])

    environment = await create_environment(client, headers)
    agent_name_by_id = {v: k for k, v in environment.agent_ids.items()}

    # Script the two LLM-routing decisions and the one "no agent fits" case —
    # everything else in the subset resolves via keyword rules or gets
    # blocked before routing ever runs, so it needs no script at all.
    scripted_anthropic_client.route(
        "Mi cuenta no me deja iniciar sesión desde ayer.",
        agent_id=environment.agent_ids["support"],
        confidence=0.9,
    )
    scripted_anthropic_client.route(
        "Mi correo es maria.garcia@example.com",
        agent_id=environment.agent_ids["support"],
        confidence=0.85,
    )
    scripted_anthropic_client.route(
        "¿Podéis recomendarme un buen abogado para un tema personal?",
        agent_id="",
        confidence=0.1,
    )

    report = await run_cases(
        client=client,
        headers=headers,
        tenant_id=tenant_id,
        cases=cases,
        agent_name_by_id=agent_name_by_id,
        score_routing=True,
        run_judge=True,
        anthropic_client=scripted_anthropic_client,
        db=db_session,
    )

    failures = [
        (r.case.id, r.routing_correct, r.guardrail_correct, r.error)
        for r in report.results
        if r.error is not None or r.routing_correct is False or not r.guardrail_correct
    ]
    assert failures == [], f"regression subset failures: {failures}"

    assert report.routing_accuracy == 1.0
    assert report.guardrail_accuracy == 1.0
    assert len(report.errors) == 0
    # Judged cases (the ones with response_quality) should all have gotten the
    # scripted score back, proving the judge step itself ran end-to-end too.
    assert all(r.judge.score == 5 for r in report.judged_results)
    scripted_anthropic_client.messages.create.assert_awaited()

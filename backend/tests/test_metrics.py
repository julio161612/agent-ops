import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pricing import calculate_cost_usd
from app.core.security import decode_token
from app.models.conversation import Conversation, ConversationStatus
from app.models.interaction_trace import InteractionTrace, TraceOutcome
from app.models.message import Message, MessageRole
from tests.helpers import FakeAnthropicClient, auth_headers, make_text_response, register_tenant

AGENT_PAYLOAD = {
    "name": "Support Agent",
    "system_prompt": "You are a helpful support agent.",
    "model": "claude-sonnet-4-6",
}


async def _create_agent(client: AsyncClient, token: str, **overrides) -> dict:
    response = await client.post(
        "/api/v1/agents", json={**AGENT_PAYLOAD, **overrides}, headers=auth_headers(token)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _send(
    client: AsyncClient, token: str, content: str, *, agent_id=None, conversation_id=None
) -> dict:
    conversation_id = conversation_id or uuid.uuid4()
    body = {"content": content}
    if agent_id is not None:
        body["agent_id"] = agent_id
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json=body,
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


def _tenant_id_from_token(access_token: str) -> uuid.UUID:
    return uuid.UUID(decode_token(access_token)["tenant_id"])


# --- summary math correctness -----------------------------------------------------------


async def test_summary_metrics_are_mathematically_correct(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    token = tokens["access_token"]
    agent = await _create_agent(client, token)

    completed_costs = []
    for input_tokens, output_tokens in [(42, 13), (100, 50), (10, 5)]:
        fake_anthropic_client.messages.create.return_value = make_text_response(
            input_tokens=input_tokens, output_tokens=output_tokens
        )
        await _send(client, token, "hola, necesito ayuda", agent_id=agent["id"])
        completed_costs.append(calculate_cost_usd("claude-sonnet-4-6", input_tokens, output_tokens))

    await client.post(
        "/api/v1/guardrail-policies",
        json={
            "guardrail_type": "input",
            "rule_type": "blocklist_keywords",
            "config": {"keywords": ["idiota"]},
            "action_on_violation": "block",
        },
        headers=auth_headers(token),
    )
    await _send(client, token, "eres un idiota", agent_id=agent["id"])

    response = await client.get(
        "/api/v1/metrics/summary",
        params={"date_from": "2020-01-01T00:00:00Z"},
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    summary = response.json()

    assert summary["total_interactions"] == 4
    assert summary["completed"] == 3
    assert summary["blocked"] == 1
    assert summary["escalated"] == 0
    assert summary["unassigned"] == 0
    assert summary["auto_resolution_rate"] == 3 / 4
    assert summary["escalation_rate"] == 0.0

    expected_total_cost = sum(completed_costs, Decimal("0"))
    assert Decimal(summary["total_cost_usd"]) == expected_total_cost

    # The blocked interaction never reaches routing/agent-binding (INPUT
    # guardrails run first), so it lands in the agent_id=None bucket — only
    # the 3 completed turns are attributed to the real agent.
    usage_by_agent = {entry["agent_id"]: entry for entry in summary["agent_usage"]}
    assert len(usage_by_agent) == 2
    assert usage_by_agent[agent["id"]]["interaction_count"] == 3
    assert Decimal(usage_by_agent[agent["id"]]["cost_usd"]) == expected_total_cost
    assert usage_by_agent[None]["interaction_count"] == 1
    assert Decimal(usage_by_agent[None]["cost_usd"]) == Decimal("0")

    assert len(summary["guardrail_violations_by_type"]) == 1
    assert summary["guardrail_violations_by_type"][0]["violation_type"] == "blocklist_keywords"
    assert summary["guardrail_violations_by_type"][0]["violation_count"] == 1

    assert summary["latency_ms_avg"] is not None
    assert summary["latency_ms_p95"] is not None
    assert summary["latency_ms_avg"] >= 0


async def test_summary_metrics_date_range_excludes_out_of_range_interactions(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    token = tokens["access_token"]
    agent = await _create_agent(client, token)
    await _send(client, token, "hola", agent_id=agent["id"])

    future_from = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    future_to = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    response = await client.get(
        "/api/v1/metrics/summary",
        params={"date_from": future_from, "date_to": future_to},
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["total_interactions"] == 0


async def test_summary_metrics_default_window_is_last_7_days(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    token = tokens["access_token"]
    agent = await _create_agent(client, token)
    await _send(client, token, "hola", agent_id=agent["id"])

    response = await client.get("/api/v1/metrics/summary", headers=auth_headers(token))
    summary = response.json()
    assert summary["total_interactions"] == 1
    date_from = datetime.fromisoformat(summary["date_from"])
    date_to = datetime.fromisoformat(summary["date_to"])
    assert 6.9 <= (date_to - date_from).total_seconds() / 86400 <= 7.1


# --- timeseries -----------------------------------------------------------------------


async def test_timeseries_bucket_totals_match_summary(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    token = tokens["access_token"]
    agent = await _create_agent(client, token)
    for _ in range(3):
        await _send(client, token, "hola", agent_id=agent["id"])

    summary_response = await client.get(
        "/api/v1/metrics/summary",
        params={"date_from": "2020-01-01T00:00:00Z"},
        headers=auth_headers(token),
    )
    summary = summary_response.json()

    timeseries_response = await client.get(
        "/api/v1/metrics/timeseries",
        params={"date_from": "2020-01-01T00:00:00Z", "granularity": "hour"},
        headers=auth_headers(token),
    )
    assert timeseries_response.status_code == 200, timeseries_response.text
    timeseries = timeseries_response.json()

    assert timeseries["granularity"] == "hour"
    total_from_buckets = sum(b["total_interactions"] for b in timeseries["buckets"])
    completed_from_buckets = sum(b["completed"] for b in timeseries["buckets"])
    cost_from_buckets = sum(Decimal(b["total_cost_usd"]) for b in timeseries["buckets"])

    assert total_from_buckets == summary["total_interactions"]
    assert completed_from_buckets == summary["completed"]
    assert cost_from_buckets == Decimal(summary["total_cost_usd"])


# --- multi-tenant isolation -------------------------------------------------------------


async def test_metrics_are_isolated_between_tenants(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    agent_a = await _create_agent(client, tenant_a["access_token"])
    for _ in range(2):
        await _send(client, tenant_a["access_token"], "hola", agent_id=agent_a["id"])

    response_a = await client.get(
        "/api/v1/metrics/summary",
        params={"date_from": "2020-01-01T00:00:00Z"},
        headers=auth_headers(tenant_a["access_token"]),
    )
    response_b = await client.get(
        "/api/v1/metrics/summary",
        params={"date_from": "2020-01-01T00:00:00Z"},
        headers=auth_headers(tenant_b["access_token"]),
    )

    assert response_a.json()["total_interactions"] == 2
    assert response_b.json()["total_interactions"] == 0


# --- performance ------------------------------------------------------------------------


async def test_metrics_summary_stays_fast_with_moderate_synthetic_volume(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient, db_session: AsyncSession
) -> None:
    tokens = await register_tenant(client)
    token = tokens["access_token"]
    tenant_id = _tenant_id_from_token(token)
    agent = await _create_agent(client, token)
    agent_id = uuid.UUID(agent["id"])

    conversation = Conversation(
        tenant_id=tenant_id, agent_id=agent_id, status=ConversationStatus.OPEN
    )
    db_session.add(conversation)
    await db_session.flush()
    message = Message(
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        role=MessageRole.USER,
        content="synthetic",
        message_metadata={},
    )
    db_session.add(message)
    await db_session.flush()

    now = datetime.now(UTC)
    outcomes = [
        TraceOutcome.COMPLETED,
        TraceOutcome.COMPLETED,
        TraceOutcome.COMPLETED,
        TraceOutcome.BLOCKED,
        TraceOutcome.UNASSIGNED,
    ]
    for i in range(500):
        db_session.add(
            InteractionTrace(
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                user_message_id=message.id,
                assistant_message_id=None,
                agent_id=agent_id,
                routing_decision_id=None,
                escalation_case_id=None,
                outcome=outcomes[i % len(outcomes)],
                cost_usd=Decimal("0.000321"),
                input_tokens=42,
                output_tokens=13,
                total_latency_ms=100 + (i % 50),
                stage_latencies_ms={
                    "rate_limit_check": 1,
                    "input_guardrails": 5,
                    "routing": 0,
                    "agent_execution": 90,
                    "output_guardrails": 4,
                },
                created_at=now - timedelta(minutes=i),
            )
        )
    await db_session.commit()

    started_at = time.monotonic()
    response = await client.get(
        "/api/v1/metrics/summary",
        params={"date_from": "2020-01-01T00:00:00Z"},
        headers=auth_headers(token),
    )
    elapsed_seconds = time.monotonic() - started_at

    assert response.status_code == 200, response.text
    summary = response.json()
    assert summary["total_interactions"] == 500
    assert elapsed_seconds < 2.0, f"metrics/summary took {elapsed_seconds:.3f}s for 500 rows"

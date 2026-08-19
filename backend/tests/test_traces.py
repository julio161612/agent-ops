import uuid
from decimal import Decimal

from httpx import AsyncClient

from app.core.pricing import calculate_cost_usd
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


async def _create_policy(client: AsyncClient, token: str, **overrides) -> dict:
    payload = {
        "guardrail_type": "input",
        "rule_type": "blocklist_keywords",
        "config": {"keywords": ["x"]},
        "action_on_violation": "block",
        "is_active": True,
        **overrides,
    }
    response = await client.post(
        "/api/v1/guardrail-policies", json=payload, headers=auth_headers(token)
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


# --- trace correctness ---------------------------------------------------------------


async def test_completed_interaction_creates_queryable_trace_with_correct_data(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])

    body = await _send(client, tokens["access_token"], "Hola, necesito ayuda", agent_id=agent["id"])
    assert body["trace_id"] is not None

    response = await client.get(
        f"/api/v1/traces/{body['trace_id']}", headers=auth_headers(tokens["access_token"])
    )
    assert response.status_code == 200, response.text
    trace = response.json()

    assert trace["outcome"] == "completed"
    assert trace["conversation_id"] == body["conversation_id"]
    assert trace["user_message_id"] == body["user_message"]["id"]
    assert trace["assistant_message_id"] == body["assistant_message"]["id"]
    assert trace["agent_id"] == agent["id"]
    assert trace["escalation_case_id"] is None
    assert trace["input_tokens"] == 42
    assert trace["output_tokens"] == 13
    expected_cost = calculate_cost_usd("claude-sonnet-4-6", 42, 13)
    assert Decimal(trace["cost_usd"]) == expected_cost
    assert trace["total_latency_ms"] >= 0
    assert set(trace["stage_latencies_ms"]) == {
        "rate_limit_check",
        "input_guardrails",
        "routing",
        "agent_execution",
        "output_guardrails",
    }
    assert trace["guardrail_violations"] == []
    assert trace["routing_decision"] is None


async def test_auto_routed_interaction_links_routing_decision(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    rule = await client.post(
        "/api/v1/routing-rules",
        json={
            "rule_type": "keyword",
            "condition": {"keywords": ["factura"]},
            "agent_id": agent["id"],
            "priority": 10,
        },
        headers=auth_headers(tokens["access_token"]),
    )
    assert rule.status_code == 201, rule.text

    body = await _send(client, tokens["access_token"], "tengo un problema con mi factura")

    response = await client.get(
        f"/api/v1/traces/{body['trace_id']}", headers=auth_headers(tokens["access_token"])
    )
    trace = response.json()
    assert trace["outcome"] == "completed"
    assert trace["agent_id"] == agent["id"]
    assert trace["routing_decision_id"] is not None
    assert trace["routing_decision"]["method"] == "rule"
    assert trace["routing_decision"]["agent_id"] == agent["id"]


async def test_blocked_interaction_creates_trace(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_policy(
        client, tokens["access_token"], config={"keywords": ["idiota"]}, action_on_violation="block"
    )

    body = await _send(client, tokens["access_token"], "eres un idiota", agent_id=agent["id"])

    response = await client.get(
        f"/api/v1/traces/{body['trace_id']}", headers=auth_headers(tokens["access_token"])
    )
    trace = response.json()
    assert trace["outcome"] == "blocked"
    assert trace["cost_usd"] == "0.000000"
    assert trace["input_tokens"] == 0
    assert trace["output_tokens"] == 0
    assert trace["assistant_message_id"] is not None
    assert len(trace["guardrail_violations"]) == 1
    assert trace["guardrail_violations"][0]["action_taken"] == "block"


async def test_unassigned_interaction_creates_trace(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)

    body = await _send(client, tokens["access_token"], "hola, hay alguien?")

    response = await client.get(
        f"/api/v1/traces/{body['trace_id']}", headers=auth_headers(tokens["access_token"])
    )
    trace = response.json()
    assert trace["outcome"] == "unassigned"
    assert trace["agent_id"] is None
    assert trace["assistant_message_id"] is None
    assert trace["escalation_case_id"] is not None


async def test_escalated_interaction_creates_trace(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    policy = await client.post(
        "/api/v1/guardrail-policies",
        json={
            "guardrail_type": "output",
            "rule_type": "blocklist_keywords",
            "config": {"keywords": ["gratis"]},
            "action_on_violation": "block",
        },
        headers=auth_headers(tokens["access_token"]),
    )
    assert policy.status_code == 201, policy.text
    fake_anthropic_client.messages.create.return_value = make_text_response(
        text="Te lo regalamos gratis, sin coste alguno!"
    )

    body = await _send(
        client, tokens["access_token"], "Que promociones tenéis?", agent_id=agent["id"]
    )

    response = await client.get(
        f"/api/v1/traces/{body['trace_id']}", headers=auth_headers(tokens["access_token"])
    )
    trace = response.json()
    assert trace["outcome"] == "escalated"
    assert trace["escalation_case_id"] is not None
    assert trace["escalation_case"]["reason"] == "guardrail_blocked"
    assert trace["input_tokens"] == 42
    assert trace["output_tokens"] == 13
    assert len(trace["guardrail_violations"]) == 1


# --- listing / filters -----------------------------------------------------------------


async def test_list_traces_filters_by_conversation_and_outcome(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])

    completed = await _send(client, tokens["access_token"], "hola", agent_id=agent["id"])
    unassigned_conv = uuid.uuid4()
    unassigned = await _send(
        client, tokens["access_token"], "hola de nuevo", conversation_id=unassigned_conv
    )
    del unassigned

    response = await client.get("/api/v1/traces", headers=auth_headers(tokens["access_token"]))
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] == 2
    assert len(page["items"]) == 2

    response = await client.get(
        "/api/v1/traces",
        params={"conversation_id": completed["conversation_id"]},
        headers=auth_headers(tokens["access_token"]),
    )
    page = response.json()
    assert page["total"] == 1
    assert page["items"][0]["conversation_id"] == completed["conversation_id"]

    response = await client.get(
        "/api/v1/traces",
        params={"outcome": "unassigned"},
        headers=auth_headers(tokens["access_token"]),
    )
    page = response.json()
    assert page["total"] == 1
    assert page["items"][0]["outcome"] == "unassigned"


async def test_list_traces_pagination(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    for i in range(3):
        await _send(client, tokens["access_token"], f"mensaje {i}", agent_id=agent["id"])

    response = await client.get(
        "/api/v1/traces",
        params={"limit": 2, "offset": 0},
        headers=auth_headers(tokens["access_token"]),
    )
    page = response.json()
    assert page["total"] == 3
    assert len(page["items"]) == 2

    response = await client.get(
        "/api/v1/traces",
        params={"limit": 2, "offset": 2},
        headers=auth_headers(tokens["access_token"]),
    )
    page = response.json()
    assert len(page["items"]) == 1


async def test_get_trace_not_found(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    response = await client.get(
        f"/api/v1/traces/{uuid.uuid4()}", headers=auth_headers(tokens["access_token"])
    )
    assert response.status_code == 404


# --- multi-tenant isolation ------------------------------------------------------------


async def test_traces_are_isolated_between_tenants(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    agent_a = await _create_agent(client, tenant_a["access_token"])

    body = await _send(client, tenant_a["access_token"], "hola", agent_id=agent_a["id"])

    response = await client.get("/api/v1/traces", headers=auth_headers(tenant_b["access_token"]))
    assert response.json()["total"] == 0

    response = await client.get(
        f"/api/v1/traces/{body['trace_id']}", headers=auth_headers(tenant_b["access_token"])
    )
    assert response.status_code == 404

import uuid

from httpx import AsyncClient

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


async def test_test_agent_returns_real_reply(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])

    response = await client.post(
        f"/api/v1/agents/{agent['id']}/test",
        json={"content": "Hola, ¿qué tal?"},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["agent_id"] == agent["id"]
    assert body["reply"] == "Hello! How can I help you today?"  # FakeAnthropicClient default
    assert body["input_blocked"] is False
    assert body["output_blocked"] is False
    assert body["input_tokens"] == 42
    assert body["output_tokens"] == 13
    assert float(body["cost_usd"]) > 0


async def test_test_agent_does_not_create_conversation_or_appear_in_history(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])

    await client.post(
        f"/api/v1/agents/{agent['id']}/test",
        json={"content": "mensaje de prueba"},
        headers=auth_headers(tokens["access_token"]),
    )

    traces = await client.get("/api/v1/traces", headers=auth_headers(tokens["access_token"]))
    assert traces.json()["total"] == 0


async def test_test_agent_does_not_affect_real_metrics(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])

    for _ in range(3):
        await client.post(
            f"/api/v1/agents/{agent['id']}/test",
            json={"content": "mensaje de prueba"},
            headers=auth_headers(tokens["access_token"]),
        )

    summary = await client.get(
        "/api/v1/metrics/summary",
        params={"date_from": "2020-01-01T00:00:00Z"},
        headers=auth_headers(tokens["access_token"]),
    )
    assert summary.json()["total_interactions"] == 0


async def test_test_agent_still_charges_real_cost_to_tenant(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])

    limits_before = await client.get(
        "/api/v1/tenant-limits", headers=auth_headers(tokens["access_token"])
    )
    cost_before = float(limits_before.json()["current_month_cost_usd"])

    await client.post(
        f"/api/v1/agents/{agent['id']}/test",
        json={"content": "mensaje de prueba"},
        headers=auth_headers(tokens["access_token"]),
    )

    limits_after = await client.get(
        "/api/v1/tenant-limits", headers=auth_headers(tokens["access_token"])
    )
    cost_after = float(limits_after.json()["current_month_cost_usd"])
    assert cost_after > cost_before


async def test_test_agent_input_blocked_never_calls_agent(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await client.post(
        "/api/v1/guardrail-policies",
        json={
            "guardrail_type": "input",
            "rule_type": "blocklist_keywords",
            "config": {"keywords": ["idiota"]},
            "action_on_violation": "block",
        },
        headers=auth_headers(tokens["access_token"]),
    )

    response = await client.post(
        f"/api/v1/agents/{agent['id']}/test",
        json={"content": "eres un idiota"},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["input_blocked"] is True
    assert body["reply"] is None
    assert body["input_tokens"] == 0
    assert len(body["input_guardrail_violations"]) == 1
    assert float(body["cost_usd"]) == 0.0


async def test_test_agent_output_guardrail_reported_but_not_persisted(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await client.post(
        "/api/v1/guardrail-policies",
        json={
            "guardrail_type": "output",
            "rule_type": "blocklist_keywords",
            "config": {"keywords": ["gratis"]},
            "action_on_violation": "block",
        },
        headers=auth_headers(tokens["access_token"]),
    )
    fake_anthropic_client.messages.create.return_value = make_text_response(
        text="Te lo regalamos gratis!"
    )

    response = await client.post(
        f"/api/v1/agents/{agent['id']}/test",
        json={"content": "que promociones tenéis?"},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["output_blocked"] is True
    assert body["reply"] == "Te lo regalamos gratis!"  # reply still returned for inspection
    assert len(body["output_guardrail_violations"]) == 1

    violations = await client.get(
        "/api/v1/guardrail-violations", headers=auth_headers(tokens["access_token"])
    )
    assert violations.json() == []

    escalations = await client.get(
        "/api/v1/escalations", headers=auth_headers(tokens["access_token"])
    )
    assert escalations.json() == []


async def test_test_agent_unknown_agent_returns_404(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)

    response = await client.post(
        f"/api/v1/agents/{uuid.uuid4()}/test",
        json={"content": "hola"},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 404

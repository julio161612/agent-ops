import uuid

from httpx import AsyncClient

from tests.helpers import FakeAnthropicClient, auth_headers, register_tenant

AGENT_PAYLOAD = {
    "name": "Support Agent",
    "system_prompt": "You are a helpful support agent.",
    "model": "claude-sonnet-4-6",
}


async def _create_agent(client: AsyncClient, token: str) -> dict:
    response = await client.post("/api/v1/agents", json=AGENT_PAYLOAD, headers=auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()


async def test_new_tenant_gets_default_limits(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    response = await client.get(
        "/api/v1/tenant-limits", headers=auth_headers(tokens["access_token"])
    )

    assert response.status_code == 200
    body = response.json()
    assert body["messages_per_minute_limit"] == 60
    assert body["monthly_cost_limit_usd"] is None
    assert float(body["current_month_cost_usd"]) == 0.0


async def test_patch_tenant_limits(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    response = await client.patch(
        "/api/v1/tenant-limits",
        # Values within the default Free plan's ceiling (10/min, $5 AI cost
        # included) — Phase 10 rejects tenant_limits above what the plan allows.
        json={"messages_per_minute_limit": 5, "monthly_cost_limit_usd": "3.50"},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["messages_per_minute_limit"] == 5
    assert float(body["monthly_cost_limit_usd"]) == 3.50


async def test_tenant_limits_isolated_by_tenant(client: AsyncClient) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )

    await client.patch(
        "/api/v1/tenant-limits",
        json={"messages_per_minute_limit": 5},
        headers=auth_headers(tenant_a["access_token"]),
    )

    response_b = await client.get(
        "/api/v1/tenant-limits", headers=auth_headers(tenant_b["access_token"])
    )

    assert response_b.json()["messages_per_minute_limit"] == 60  # untouched default


async def test_rate_limit_blocks_after_exceeding_messages_per_minute(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await client.patch(
        "/api/v1/tenant-limits",
        json={"messages_per_minute_limit": 2},
        headers=auth_headers(tokens["access_token"]),
    )

    responses = []
    for _ in range(3):
        responses.append(
            await client.post(
                f"/api/v1/conversations/{uuid.uuid4()}/messages",
                json={"content": "hi", "agent_id": agent["id"]},
                headers=auth_headers(tokens["access_token"]),
            )
        )

    statuses = [r.status_code for r in responses]
    assert statuses == [200, 200, 429]
    assert "Rate limit" in responses[2].json()["detail"]


async def test_rate_limit_isolated_by_tenant(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    agent_a = await _create_agent(client, tenant_a["access_token"])
    agent_b = await _create_agent(client, tenant_b["access_token"])
    await client.patch(
        "/api/v1/tenant-limits",
        json={"messages_per_minute_limit": 1},
        headers=auth_headers(tenant_a["access_token"]),
    )

    # Tenant A immediately exhausts its own limit...
    await client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        json={"content": "hi", "agent_id": agent_a["id"]},
        headers=auth_headers(tenant_a["access_token"]),
    )
    exhausted = await client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        json={"content": "hi", "agent_id": agent_a["id"]},
        headers=auth_headers(tenant_a["access_token"]),
    )
    assert exhausted.status_code == 429

    # ...but Tenant B, with its own (default, much higher) limit, is unaffected.
    unaffected = await client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        json={"content": "hi", "agent_id": agent_b["id"]},
        headers=auth_headers(tenant_b["access_token"]),
    )
    assert unaffected.status_code == 200


async def test_monthly_cost_limit_blocks_new_messages_once_exceeded(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    # The fake response's default usage (42 input + 13 output tokens) at
    # claude-sonnet-4-6 pricing costs a bit over $0.0003 — set the cap just
    # below that so a single real call is enough to exceed it.
    await client.patch(
        "/api/v1/tenant-limits",
        json={"monthly_cost_limit_usd": "0.0001"},
        headers=auth_headers(tokens["access_token"]),
    )

    first = await client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        json={"content": "hi", "agent_id": agent["id"]},
        headers=auth_headers(tokens["access_token"]),
    )
    assert first.status_code == 200

    second = await client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        json={"content": "hi again", "agent_id": agent["id"]},
        headers=auth_headers(tokens["access_token"]),
    )

    assert second.status_code == 429
    assert "cost limit" in second.json()["detail"].lower()

    limits = await client.get("/api/v1/tenant-limits", headers=auth_headers(tokens["access_token"]))
    assert float(limits.json()["current_month_cost_usd"]) > 0

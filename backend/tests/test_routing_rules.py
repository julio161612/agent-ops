import uuid

from httpx import AsyncClient

from tests.helpers import auth_headers, register_tenant

AGENT_PAYLOAD = {
    "name": "Billing Agent",
    "agent_type": "billing",
    "system_prompt": "You handle billing questions.",
    "model": "claude-sonnet-4-6",
}


async def _create_agent(client: AsyncClient, token: str, **overrides) -> dict:
    response = await client.post(
        "/api/v1/agents", json={**AGENT_PAYLOAD, **overrides}, headers=auth_headers(token)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_rule(client: AsyncClient, token: str, agent_id: str, **overrides) -> dict:
    payload = {
        "agent_id": agent_id,
        "rule_type": "keyword",
        "condition": {"keywords": ["factura", "cobro"]},
        "priority": 0,
        "is_active": True,
        **overrides,
    }
    response = await client.post("/api/v1/routing-rules", json=payload, headers=auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_keyword_rule(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])

    body = await _create_rule(client, tokens["access_token"], agent["id"])

    assert body["rule_type"] == "keyword"
    assert body["condition"] == {"keywords": ["factura", "cobro"]}
    assert body["agent_id"] == agent["id"]
    assert body["is_active"] is True


async def test_create_category_rule(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])

    body = await _create_rule(
        client,
        tokens["access_token"],
        agent["id"],
        rule_type="category",
        condition={"agent_type": "billing"},
    )

    assert body["rule_type"] == "category"
    assert body["condition"] == {"agent_type": "billing"}


async def test_create_keyword_rule_with_empty_keywords_returns_422(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])

    response = await client.post(
        "/api/v1/routing-rules",
        json={
            "agent_id": agent["id"],
            "rule_type": "keyword",
            "condition": {"keywords": []},
        },
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 422


async def test_create_category_rule_without_agent_type_returns_422(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])

    response = await client.post(
        "/api/v1/routing-rules",
        json={"agent_id": agent["id"], "rule_type": "category", "condition": {}},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 422


async def test_create_rule_with_unknown_agent_returns_404(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    response = await client.post(
        "/api/v1/routing-rules",
        json={
            "agent_id": str(uuid.uuid4()),
            "rule_type": "keyword",
            "condition": {"keywords": ["hola"]},
        },
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 404


async def test_list_routing_rules_returns_only_own_tenant(client: AsyncClient) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    agent_a = await _create_agent(client, tenant_a["access_token"])
    agent_b = await _create_agent(client, tenant_b["access_token"])
    await _create_rule(client, tenant_a["access_token"], agent_a["id"])
    await _create_rule(client, tenant_b["access_token"], agent_b["id"])

    response_a = await client.get(
        "/api/v1/routing-rules", headers=auth_headers(tenant_a["access_token"])
    )

    assert len(response_a.json()) == 1
    assert response_a.json()[0]["agent_id"] == agent_a["id"]


async def test_cannot_get_another_tenants_routing_rule(client: AsyncClient) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    agent_a = await _create_agent(client, tenant_a["access_token"])
    rule = await _create_rule(client, tenant_a["access_token"], agent_a["id"])

    response = await client.get(
        f"/api/v1/routing-rules/{rule['id']}", headers=auth_headers(tenant_b["access_token"])
    )

    assert response.status_code == 404


async def test_cannot_update_another_tenants_routing_rule(client: AsyncClient) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    agent_a = await _create_agent(client, tenant_a["access_token"])
    rule = await _create_rule(client, tenant_a["access_token"], agent_a["id"])

    response = await client.patch(
        f"/api/v1/routing-rules/{rule['id']}",
        json={"priority": 99},
        headers=auth_headers(tenant_b["access_token"]),
    )

    assert response.status_code == 404


async def test_cannot_delete_another_tenants_routing_rule(client: AsyncClient) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    agent_a = await _create_agent(client, tenant_a["access_token"])
    rule = await _create_rule(client, tenant_a["access_token"], agent_a["id"])

    response = await client.delete(
        f"/api/v1/routing-rules/{rule['id']}", headers=auth_headers(tenant_b["access_token"])
    )

    assert response.status_code == 404


async def test_update_routing_rule_changes_priority(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    rule = await _create_rule(client, tokens["access_token"], agent["id"])

    response = await client.patch(
        f"/api/v1/routing-rules/{rule['id']}",
        json={"priority": 10, "is_active": False},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["priority"] == 10
    assert body["is_active"] is False


async def test_update_rule_type_to_category_without_matching_condition_returns_422(
    client: AsyncClient,
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    rule = await _create_rule(client, tokens["access_token"], agent["id"])  # keyword rule

    response = await client.patch(
        f"/api/v1/routing-rules/{rule['id']}",
        json={"rule_type": "category"},  # condition still has "keywords", not "agent_type"
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 422


async def test_delete_routing_rule_hard_deletes(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    rule = await _create_rule(client, tokens["access_token"], agent["id"])

    delete_response = await client.delete(
        f"/api/v1/routing-rules/{rule['id']}", headers=auth_headers(tokens["access_token"])
    )
    assert delete_response.status_code == 204

    get_response = await client.get(
        f"/api/v1/routing-rules/{rule['id']}", headers=auth_headers(tokens["access_token"])
    )
    assert get_response.status_code == 404

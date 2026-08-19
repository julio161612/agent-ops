import uuid

from httpx import AsyncClient

from tests.helpers import auth_headers, register_tenant

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
        "config": {"keywords": ["idiota"]},
        "action_on_violation": "block",
        "is_active": True,
        **overrides,
    }
    response = await client.post(
        "/api/v1/guardrail-policies", json=payload, headers=auth_headers(token)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_blocklist_policy(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    body = await _create_policy(client, tokens["access_token"])

    assert body["rule_type"] == "blocklist_keywords"
    assert body["guardrail_type"] == "input"
    assert body["action_on_violation"] == "block"
    assert body["agent_id"] is None


async def test_create_policy_scoped_to_agent(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])

    body = await _create_policy(client, tokens["access_token"], agent_id=agent["id"])

    assert body["agent_id"] == agent["id"]


async def test_create_policy_with_unknown_agent_returns_404(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    response = await client.post(
        "/api/v1/guardrail-policies",
        json={
            "agent_id": str(uuid.uuid4()),
            "guardrail_type": "input",
            "rule_type": "blocklist_keywords",
            "config": {"keywords": ["x"]},
        },
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 404


async def test_create_blocklist_policy_with_empty_keywords_returns_422(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    response = await client.post(
        "/api/v1/guardrail-policies",
        json={
            "guardrail_type": "input",
            "rule_type": "blocklist_keywords",
            "config": {"keywords": []},
        },
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 422


async def test_create_max_length_policy_without_max_characters_returns_422(
    client: AsyncClient,
) -> None:
    tokens = await register_tenant(client)

    response = await client.post(
        "/api/v1/guardrail-policies",
        json={"guardrail_type": "input", "rule_type": "max_length", "config": {}},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 422


async def test_create_pii_policy_with_invalid_pattern_name_returns_422(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    response = await client.post(
        "/api/v1/guardrail-policies",
        json={
            "guardrail_type": "input",
            "rule_type": "pii_detection",
            "config": {"patterns": ["not_a_real_pattern"]},
        },
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 422


async def test_create_custom_llm_check_without_instruction_returns_422(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    response = await client.post(
        "/api/v1/guardrail-policies",
        json={"guardrail_type": "output", "rule_type": "custom_llm_check", "config": {}},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 422


async def test_list_policies_returns_only_own_tenant(client: AsyncClient) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    await _create_policy(client, tenant_a["access_token"])
    await _create_policy(client, tenant_b["access_token"])

    response_a = await client.get(
        "/api/v1/guardrail-policies", headers=auth_headers(tenant_a["access_token"])
    )

    assert len(response_a.json()) == 1


async def test_cannot_get_another_tenants_policy(client: AsyncClient) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    policy = await _create_policy(client, tenant_a["access_token"])

    response = await client.get(
        f"/api/v1/guardrail-policies/{policy['id']}", headers=auth_headers(tenant_b["access_token"])
    )

    assert response.status_code == 404


async def test_cannot_update_another_tenants_policy(client: AsyncClient) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    policy = await _create_policy(client, tenant_a["access_token"])

    response = await client.patch(
        f"/api/v1/guardrail-policies/{policy['id']}",
        json={"is_active": False},
        headers=auth_headers(tenant_b["access_token"]),
    )

    assert response.status_code == 404


async def test_cannot_delete_another_tenants_policy(client: AsyncClient) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    policy = await _create_policy(client, tenant_a["access_token"])

    response = await client.delete(
        f"/api/v1/guardrail-policies/{policy['id']}", headers=auth_headers(tenant_b["access_token"])
    )

    assert response.status_code == 404


async def test_update_policy_action(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    policy = await _create_policy(client, tokens["access_token"])

    response = await client.patch(
        f"/api/v1/guardrail-policies/{policy['id']}",
        json={"action_on_violation": "flag"},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 200
    assert response.json()["action_on_violation"] == "flag"


async def test_update_config_incompatible_with_rule_type_returns_422(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    policy = await _create_policy(client, tokens["access_token"])  # blocklist_keywords

    response = await client.patch(
        f"/api/v1/guardrail-policies/{policy['id']}",
        json={"rule_type": "max_length"},  # config still has "keywords", not "max_characters"
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 422


async def test_delete_policy_removes_it(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    policy = await _create_policy(client, tokens["access_token"])

    delete_response = await client.delete(
        f"/api/v1/guardrail-policies/{policy['id']}", headers=auth_headers(tokens["access_token"])
    )
    assert delete_response.status_code == 204

    get_response = await client.get(
        f"/api/v1/guardrail-policies/{policy['id']}", headers=auth_headers(tokens["access_token"])
    )
    assert get_response.status_code == 404

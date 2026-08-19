from httpx import AsyncClient

from tests.helpers import auth_headers, register_tenant


async def test_catalog_has_at_least_five_templates(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    response = await client.get(
        "/api/v1/agent-templates", headers=auth_headers(tokens["access_token"])
    )

    assert response.status_code == 200, response.text
    templates = response.json()
    assert len(templates) >= 5
    ids = {t["id"] for t in templates}
    assert len(ids) == len(templates)  # unique ids
    for template in templates:
        assert template["system_prompt"]
        assert template["agent_type"]
        assert template["recommended_guardrail"]["rule_type"]
        assert template["recommended_guardrail"]["rationale"]


async def test_create_agent_from_template_applies_recommended_guardrail(
    client: AsyncClient,
) -> None:
    tokens = await register_tenant(client)
    catalog = (
        await client.get("/api/v1/agent-templates", headers=auth_headers(tokens["access_token"]))
    ).json()
    template = catalog[0]

    response = await client.post(
        f"/api/v1/agents/from-template/{template['id']}",
        json={},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["agent"]["name"] == template["name"]
    assert body["agent"]["system_prompt"] == template["system_prompt"]
    assert body["agent"]["agent_type"] == template["agent_type"]
    assert body["guardrail_policy"] is not None
    assert body["guardrail_policy"]["agent_id"] == body["agent"]["id"]
    assert body["guardrail_policy"]["rule_type"] == template["recommended_guardrail"]["rule_type"]

    # actually persisted, not just returned
    agents = await client.get("/api/v1/agents", headers=auth_headers(tokens["access_token"]))
    assert any(a["id"] == body["agent"]["id"] for a in agents.json())
    policies = await client.get(
        "/api/v1/guardrail-policies", headers=auth_headers(tokens["access_token"])
    )
    assert any(p["id"] == body["guardrail_policy"]["id"] for p in policies.json())


async def test_create_agent_from_template_allows_overrides(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    catalog = (
        await client.get("/api/v1/agent-templates", headers=auth_headers(tokens["access_token"]))
    ).json()
    template = catalog[0]

    response = await client.post(
        f"/api/v1/agents/from-template/{template['id']}",
        json={"name": "My Custom Name", "system_prompt": "Custom prompt override."},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["agent"]["name"] == "My Custom Name"
    assert body["agent"]["system_prompt"] == "Custom prompt override."


async def test_create_agent_from_template_can_skip_guardrail(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    catalog = (
        await client.get("/api/v1/agent-templates", headers=auth_headers(tokens["access_token"]))
    ).json()
    template = catalog[0]

    response = await client.post(
        f"/api/v1/agents/from-template/{template['id']}",
        json={"apply_recommended_guardrail": False},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 201, response.text
    assert response.json()["guardrail_policy"] is None


async def test_create_agent_from_unknown_template_returns_404(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    response = await client.post(
        "/api/v1/agents/from-template/does-not-exist",
        json={},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 404

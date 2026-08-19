import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from tests.helpers import auth_headers, register_tenant

AGENT_PAYLOAD = {
    "name": "Support Agent",
    "description": "Handles tier-1 support questions",
    "agent_type": "soporte",
    "system_prompt": "You are a helpful support agent for Acme Corp.",
    "model": "claude-sonnet-4-6",
    "parameters": {"temperature": 0.5, "max_tokens": 512},
}


async def _create_agent(client: AsyncClient, token: str, **overrides) -> dict:
    response = await client.post(
        "/api/v1/agents", json={**AGENT_PAYLOAD, **overrides}, headers=auth_headers(token)
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_agent_returns_configured_fields(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    body = await _create_agent(client, tokens["access_token"])

    assert body["name"] == AGENT_PAYLOAD["name"]
    assert body["agent_type"] == "soporte"
    assert body["model"] == "claude-sonnet-4-6"
    assert body["parameters"] == {"temperature": 0.5, "max_tokens": 512}
    assert body["is_active"] is True


async def test_create_agent_without_model_uses_default(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    payload = {k: v for k, v in AGENT_PAYLOAD.items() if k != "model"}

    response = await client.post(
        "/api/v1/agents", json=payload, headers=auth_headers(tokens["access_token"])
    )

    assert response.status_code == 201, response.text
    assert response.json()["model"]  # falls back to settings.ANTHROPIC_DEFAULT_MODEL


async def test_list_agents_returns_only_own_tenant_agents(client: AsyncClient) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    await _create_agent(client, tenant_a["access_token"], name="A's Agent")
    await _create_agent(client, tenant_b["access_token"], name="B's Agent")

    response_a = await client.get("/api/v1/agents", headers=auth_headers(tenant_a["access_token"]))
    response_b = await client.get("/api/v1/agents", headers=auth_headers(tenant_b["access_token"]))

    assert [a["name"] for a in response_a.json()] == ["A's Agent"]
    assert [a["name"] for a in response_b.json()] == ["B's Agent"]


async def test_cannot_get_another_tenants_agent(client: AsyncClient) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    agent = await _create_agent(client, tenant_a["access_token"])

    response = await client.get(
        f"/api/v1/agents/{agent['id']}", headers=auth_headers(tenant_b["access_token"])
    )

    assert response.status_code == 404


async def test_cannot_update_another_tenants_agent(client: AsyncClient) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    agent = await _create_agent(client, tenant_a["access_token"])

    response = await client.patch(
        f"/api/v1/agents/{agent['id']}",
        json={"name": "Hijacked"},
        headers=auth_headers(tenant_b["access_token"]),
    )

    assert response.status_code == 404


async def test_cannot_delete_another_tenants_agent(client: AsyncClient) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    agent = await _create_agent(client, tenant_a["access_token"])

    response = await client.delete(
        f"/api/v1/agents/{agent['id']}", headers=auth_headers(tenant_b["access_token"])
    )

    assert response.status_code == 404


async def test_get_unknown_agent_returns_404(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    response = await client.get(
        f"/api/v1/agents/{uuid.uuid4()}", headers=auth_headers(tokens["access_token"])
    )

    assert response.status_code == 404


async def test_update_agent_partially_changes_only_given_fields(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])

    response = await client.patch(
        f"/api/v1/agents/{agent['id']}",
        json={"is_active": False},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_active"] is False
    assert body["name"] == AGENT_PAYLOAD["name"]  # untouched


async def test_delete_agent_soft_deletes_not_hard_deletes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])

    response = await client.delete(
        f"/api/v1/agents/{agent['id']}", headers=auth_headers(tokens["access_token"])
    )
    assert response.status_code == 204

    # Gone from the API...
    get_response = await client.get(
        f"/api/v1/agents/{agent['id']}", headers=auth_headers(tokens["access_token"])
    )
    assert get_response.status_code == 404
    list_response = await client.get("/api/v1/agents", headers=auth_headers(tokens["access_token"]))
    assert list_response.json() == []

    # ...but the row is still physically present, just marked deleted.
    result = await db_session.execute(select(Agent).where(Agent.id == uuid.UUID(agent["id"])))
    row = result.scalar_one()
    assert row.deleted_at is not None
    assert row.is_active is False

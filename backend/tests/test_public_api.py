from httpx import AsyncClient

from app.core.config import settings
from tests.helpers import FakeAnthropicClient, auth_headers, register_tenant

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


async def _create_keyword_rule(
    client: AsyncClient, token: str, agent_id: str, keyword: str
) -> dict:
    response = await client.post(
        "/api/v1/routing-rules",
        json={"agent_id": agent_id, "rule_type": "keyword", "condition": {"keywords": [keyword]}},
        headers=auth_headers(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_server_key(client: AsyncClient, token: str, **overrides) -> dict:
    payload = {"name": "Server key", "key_type": "server", **overrides}
    response = await client.post("/api/v1/api-keys", json=payload, headers=auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()


async def _create_widget_key(client: AsyncClient, token: str, **overrides) -> dict:
    payload = {"name": "Widget key", "key_type": "widget", **overrides}
    response = await client.post("/api/v1/api-keys", json=payload, headers=auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()


async def test_send_public_message_runs_full_pipeline(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_keyword_rule(client, tokens["access_token"], agent["id"], "factura")
    server_key = await _create_server_key(client, tokens["access_token"])

    response = await client.post(
        "/public/v1/messages",
        json={"content": "tengo una duda con mi factura", "external_user_id": "customer-42"},
        headers={"X-API-Key": server_key["api_key"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_id"]
    assert body["reply"] == "Hello! How can I help you today?"
    assert body["status"] == "open"


async def test_send_public_message_without_agents_is_unassigned(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    server_key = await _create_server_key(client, tokens["access_token"])

    response = await client.post(
        "/public/v1/messages",
        json={"content": "hola, hay alguien?", "external_user_id": "customer-1"},
        headers={"X-API-Key": server_key["api_key"]},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reply"] is None
    assert body["status"] == "unassigned"


async def test_reusing_session_id_continues_same_conversation(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_keyword_rule(client, tokens["access_token"], agent["id"], "hola")
    server_key = await _create_server_key(client, tokens["access_token"])

    first = await client.post(
        "/public/v1/messages",
        json={"content": "hola", "external_user_id": "customer-7", "session_id": None},
        headers={"X-API-Key": server_key["api_key"]},
    )
    session_id = first.json()["session_id"]

    second = await client.post(
        "/public/v1/messages",
        json={
            "content": "otra pregunta",
            "external_user_id": "customer-7",
            "session_id": session_id,
        },
        headers={"X-API-Key": server_key["api_key"]},
    )
    assert second.status_code == 200, second.text
    assert second.json()["session_id"] == session_id

    history = await client.get(
        f"/public/v1/messages/{session_id}", headers={"X-API-Key": server_key["api_key"]}
    )
    assert history.status_code == 200, history.text
    roles = [m["role"] for m in history.json()["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"]


async def test_widget_key_can_send_but_not_read_history(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    await _create_agent(client, tokens["access_token"])
    widget_key = await _create_widget_key(client, tokens["access_token"])

    send = await client.post(
        "/public/v1/messages",
        json={"content": "hola", "external_user_id": "customer-9"},
        headers={"X-API-Key": widget_key["api_key"]},
    )
    assert send.status_code == 200, send.text
    session_id = send.json()["session_id"]

    history = await client.get(
        f"/public/v1/messages/{session_id}", headers={"X-API-Key": widget_key["api_key"]}
    )
    assert history.status_code == 403


async def test_public_api_isolated_between_tenants(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    key_a = await _create_server_key(client, tenant_a["access_token"])
    key_b = await _create_server_key(client, tenant_b["access_token"])

    send_a = await client.post(
        "/public/v1/messages",
        json={"content": "hola desde A", "external_user_id": "customer-a"},
        headers={"X-API-Key": key_a["api_key"]},
    )
    session_a = send_a.json()["session_id"]

    # tenant B's key can't read tenant A's session
    cross_tenant_read = await client.get(
        f"/public/v1/messages/{session_a}", headers={"X-API-Key": key_b["api_key"]}
    )
    assert cross_tenant_read.status_code == 404

    # tenant B's own sessions never show up when tenant A lists its own
    send_b = await client.post(
        "/public/v1/messages",
        json={"content": "hola desde B", "external_user_id": "customer-b"},
        headers={"X-API-Key": key_b["api_key"]},
    )
    session_b = send_b.json()["session_id"]
    assert session_b != session_a
    cross_tenant_read_2 = await client.get(
        f"/public/v1/messages/{session_b}", headers={"X-API-Key": key_a["api_key"]}
    )
    assert cross_tenant_read_2.status_code == 404


async def test_public_api_rate_limit_is_per_key_and_stricter(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "PUBLIC_API_RATE_LIMIT_PER_MINUTE", 2)
    tokens = await register_tenant(client)
    await _create_agent(client, tokens["access_token"])
    server_key = await _create_server_key(client, tokens["access_token"])

    for _ in range(2):
        response = await client.post(
            "/public/v1/messages",
            json={"content": "hola", "external_user_id": "customer-1"},
            headers={"X-API-Key": server_key["api_key"]},
        )
        assert response.status_code == 200, response.text

    third = await client.post(
        "/public/v1/messages",
        json={"content": "hola otra vez", "external_user_id": "customer-1"},
        headers={"X-API-Key": server_key["api_key"]},
    )
    assert third.status_code == 429

import uuid

from httpx import AsyncClient

from tests.helpers import (
    FakeAnthropicClient,
    auth_headers,
    make_rate_limit_error,
    make_timeout_error,
    register_tenant,
)

AGENT_PAYLOAD = {
    "name": "Support Agent",
    "system_prompt": "You are a helpful support agent for Acme Corp.",
    "model": "claude-sonnet-4-6",
    "parameters": {"temperature": 0.5, "max_tokens": 512},
}


async def _create_agent(client: AsyncClient, token: str) -> dict:
    response = await client.post("/api/v1/agents", json=AGENT_PAYLOAD, headers=auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()


async def test_send_message_creates_conversation_and_returns_reply(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    conversation_id = uuid.uuid4()

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "Hi, I need help with my order.", "agent_id": agent["id"]},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["conversation_id"] == str(conversation_id)
    assert body["user_message"]["content"] == "Hi, I need help with my order."
    assert body["user_message"]["role"] == "user"
    assert body["assistant_message"]["role"] == "assistant"
    assert body["assistant_message"]["content"] == "Hello! How can I help you today?"

    metadata = body["assistant_message"]["metadata"]
    assert metadata["model"] == "claude-sonnet-4-6"
    assert metadata["input_tokens"] == 42
    assert metadata["output_tokens"] == 13
    assert metadata["stop_reason"] == "end_turn"
    assert isinstance(metadata["latency_ms"], int)


async def test_send_message_calls_anthropic_with_agent_config(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    conversation_id = uuid.uuid4()

    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "Hi there", "agent_id": agent["id"]},
        headers=auth_headers(tokens["access_token"]),
    )
    assert response.status_code == 200, response.text

    fake_anthropic_client.messages.create.assert_awaited_once_with(
        model="claude-sonnet-4-6",
        system=AGENT_PAYLOAD["system_prompt"],
        max_tokens=512,
        temperature=0.5,
        messages=[{"role": "user", "content": "Hi there"}],
    )


async def test_second_message_includes_prior_history(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    conversation_id = uuid.uuid4()

    await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "What's your return policy?", "agent_id": agent["id"]},
        headers=auth_headers(tokens["access_token"]),
    )
    await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "And for electronics specifically?"},
        headers=auth_headers(tokens["access_token"]),
    )

    second_call_kwargs = fake_anthropic_client.messages.create.await_args_list[1].kwargs
    assert second_call_kwargs["messages"] == [
        {"role": "user", "content": "What's your return policy?"},
        {"role": "assistant", "content": "Hello! How can I help you today?"},
        {"role": "user", "content": "And for electronics specifically?"},
    ]


async def test_send_message_with_unknown_agent_id_returns_404(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)

    response = await client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        json={"content": "Hello?", "agent_id": str(uuid.uuid4())},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 404


async def test_get_messages_returns_full_history(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    conversation_id = uuid.uuid4()
    await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "Hi there", "agent_id": agent["id"]},
        headers=auth_headers(tokens["access_token"]),
    )

    response = await client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 200
    roles = [m["role"] for m in response.json()]
    assert roles == ["user", "assistant"]


async def test_get_messages_for_unknown_conversation_returns_404(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)

    response = await client.get(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 404


async def test_conversation_is_isolated_by_tenant(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    agent_a = await _create_agent(client, tenant_a["access_token"])
    conversation_id = uuid.uuid4()
    await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "Hi there", "agent_id": agent_a["id"]},
        headers=auth_headers(tenant_a["access_token"]),
    )

    response = await client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=auth_headers(tenant_b["access_token"]),
    )

    assert response.status_code == 404


async def test_send_message_handles_rate_limit_error(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    fake_anthropic_client.messages.create.side_effect = make_rate_limit_error()

    response = await client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        json={"content": "Hi there", "agent_id": agent["id"]},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 429


async def test_send_message_handles_timeout_error(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    fake_anthropic_client.messages.create.side_effect = make_timeout_error()

    response = await client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        json={"content": "Hi there", "agent_id": agent["id"]},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 504

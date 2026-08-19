import asyncio
import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import (
    FakeAnthropicClient,
    auth_headers,
    create_extra_user_token,
    make_text_response,
    register_tenant,
)

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


async def _force_unassigned_conversation(
    client: AsyncClient, token: str, conversation_id=None
) -> dict:
    """Tenant has zero agents -> routing always fails -> conversation stays unassigned."""
    return await _send(client, token, "hello, is anyone there?", conversation_id=conversation_id)


async def _force_output_block(
    client: AsyncClient, token: str, fake_anthropic_client: FakeAnthropicClient, agent_id: str
) -> dict:
    policy = await client.post(
        "/api/v1/guardrail-policies",
        json={
            "guardrail_type": "output",
            "rule_type": "blocklist_keywords",
            "config": {"keywords": ["gratis"]},
            "action_on_violation": "block",
        },
        headers=auth_headers(token),
    )
    assert policy.status_code == 201, policy.text
    fake_anthropic_client.messages.create.return_value = make_text_response(
        text="Te lo regalamos gratis, sin coste alguno!"
    )
    return await _send(client, token, "Que promociones tenéis?", agent_id=agent_id)


# --- automatic creation --------------------------------------------------------------


async def test_unassigned_routing_creates_pending_escalation_case(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)

    body = await _force_unassigned_conversation(client, tokens["access_token"])
    assert body["conversation_status"] == "unassigned"

    response = await client.get("/api/v1/escalations", headers=auth_headers(tokens["access_token"]))
    cases = response.json()
    assert len(cases) == 1
    assert cases[0]["conversation_id"] == body["conversation_id"]
    assert cases[0]["reason"] == "unassigned_routing"
    assert cases[0]["status"] == "pending"
    assert cases[0]["assigned_to"] is None


async def test_output_guardrail_block_creates_escalation_case(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])

    body = await _force_output_block(
        client, tokens["access_token"], fake_anthropic_client, agent["id"]
    )
    assert body["conversation_status"] == "escalated"

    response = await client.get(
        "/api/v1/escalations",
        params={"reason": "guardrail_blocked"},
        headers=auth_headers(tokens["access_token"]),
    )
    cases = response.json()
    assert len(cases) == 1
    assert cases[0]["conversation_id"] == body["conversation_id"]
    assert cases[0]["status"] == "pending"


async def test_no_duplicate_case_for_repeated_unassigned_messages(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    conversation_id = uuid.uuid4()

    await _force_unassigned_conversation(
        client, tokens["access_token"], conversation_id=conversation_id
    )
    await _send(client, tokens["access_token"], "still nobody?", conversation_id=conversation_id)
    await _send(client, tokens["access_token"], "hello??", conversation_id=conversation_id)

    response = await client.get("/api/v1/escalations", headers=auth_headers(tokens["access_token"]))
    cases = [c for c in response.json() if c["conversation_id"] == str(conversation_id)]
    assert len(cases) == 1


# --- claim -----------------------------------------------------------------------------


async def test_claim_pending_case_assigns_current_user(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    body = await _force_unassigned_conversation(client, tokens["access_token"])
    case_id = (
        await client.get("/api/v1/escalations", headers=auth_headers(tokens["access_token"]))
    ).json()[0]["id"]
    me = await client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"]))
    my_user_id = me.json()["user"]["id"]

    response = await client.post(
        f"/api/v1/escalations/{case_id}/claim", headers=auth_headers(tokens["access_token"])
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "in_progress"
    assert body["assigned_to"] == my_user_id
    assert body["assigned_at"] is not None


async def test_claim_already_claimed_case_returns_409(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    await _force_unassigned_conversation(client, tokens["access_token"])
    case_id = (
        await client.get("/api/v1/escalations", headers=auth_headers(tokens["access_token"]))
    ).json()[0]["id"]
    await client.post(
        f"/api/v1/escalations/{case_id}/claim", headers=auth_headers(tokens["access_token"])
    )

    second_attempt = await client.post(
        f"/api/v1/escalations/{case_id}/claim", headers=auth_headers(tokens["access_token"])
    )

    assert second_attempt.status_code == 409


async def test_claim_race_condition_only_one_of_two_concurrent_attempts_succeeds(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    await _force_unassigned_conversation(client, tokens["access_token"])
    case_id = (
        await client.get("/api/v1/escalations", headers=auth_headers(tokens["access_token"]))
    ).json()[0]["id"]

    responses = await asyncio.gather(
        client.post(
            f"/api/v1/escalations/{case_id}/claim", headers=auth_headers(tokens["access_token"])
        ),
        client.post(
            f"/api/v1/escalations/{case_id}/claim", headers=auth_headers(tokens["access_token"])
        ),
    )

    statuses = sorted(r.status_code for r in responses)
    assert statuses == [200, 409]


async def test_claim_unknown_case_returns_404(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    response = await client.post(
        f"/api/v1/escalations/{uuid.uuid4()}/claim", headers=auth_headers(tokens["access_token"])
    )

    assert response.status_code == 404


# --- full flow: claim -> respond -> resolve --------------------------------------------


async def test_full_flow_claim_respond_resolve(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    sent = await _force_unassigned_conversation(client, tokens["access_token"])
    conversation_id = sent["conversation_id"]
    case_id = (
        await client.get("/api/v1/escalations", headers=auth_headers(tokens["access_token"]))
    ).json()[0]["id"]

    claim_response = await client.post(
        f"/api/v1/escalations/{case_id}/claim", headers=auth_headers(tokens["access_token"])
    )
    assert claim_response.status_code == 200

    respond_response = await client.post(
        f"/api/v1/escalations/{case_id}/respond",
        json={"content": "Hi, a human here — happy to help!"},
        headers=auth_headers(tokens["access_token"]),
    )
    assert respond_response.status_code == 200
    respond_body = respond_response.json()
    assert respond_body["message"]["role"] == "assistant"
    assert respond_body["message"]["content"] == "Hi, a human here — happy to help!"
    assert respond_body["message"]["metadata"]["author"] == "human"
    assert respond_body["message"]["metadata"]["responded_by_user_id"]

    resolve_response = await client.post(
        f"/api/v1/escalations/{case_id}/resolve",
        json={"notes": "Answered manually, routing had no matching agent."},
        headers=auth_headers(tokens["access_token"]),
    )
    assert resolve_response.status_code == 200
    resolve_body = resolve_response.json()
    assert resolve_body["status"] == "resolved"
    assert resolve_body["resolved_at"] is not None
    assert resolve_body["resolution_notes"] == "Answered manually, routing had no matching agent."

    # The human's reply must show up in the conversation history, correctly tagged.
    history = await client.get(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=auth_headers(tokens["access_token"]),
    )
    messages = history.json()
    human_messages = [m for m in messages if m["metadata"].get("author") == "human"]
    assert len(human_messages) == 1
    assert human_messages[0]["content"] == "Hi, a human here — happy to help!"

    # Resolving un-stuck the conversation.
    convo_status = (
        await client.get(
            f"/api/v1/escalations/{case_id}", headers=auth_headers(tokens["access_token"])
        )
    ).json()
    assert convo_status["status"] == "resolved"


async def test_resolve_reopens_conversation_status(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    sent = await _force_output_block(
        client, tokens["access_token"], fake_anthropic_client, agent["id"]
    )
    assert sent["conversation_status"] == "escalated"
    case_id = (
        await client.get("/api/v1/escalations", headers=auth_headers(tokens["access_token"]))
    ).json()[0]["id"]
    await client.post(
        f"/api/v1/escalations/{case_id}/claim", headers=auth_headers(tokens["access_token"])
    )

    await client.post(
        f"/api/v1/escalations/{case_id}/resolve",
        json={},
        headers=auth_headers(tokens["access_token"]),
    )

    messages = await client.get(
        f"/api/v1/conversations/{sent['conversation_id']}/messages",
        headers=auth_headers(tokens["access_token"]),
    )
    assert messages.status_code == 200  # conversation is reachable/normal again


async def test_cannot_respond_before_claiming(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    await _force_unassigned_conversation(client, tokens["access_token"])
    case_id = (
        await client.get("/api/v1/escalations", headers=auth_headers(tokens["access_token"]))
    ).json()[0]["id"]

    response = await client.post(
        f"/api/v1/escalations/{case_id}/respond",
        json={"content": "trying to skip the queue"},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 409


async def test_cannot_respond_to_case_claimed_by_another_user(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient, db_session: AsyncSession
) -> None:
    tokens = await register_tenant(client)
    me = await client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"]))
    tenant_id = uuid.UUID(me.json()["tenant"]["id"])
    other_token = await create_extra_user_token(db_session, tenant_id=tenant_id)

    await _force_unassigned_conversation(client, tokens["access_token"])
    case_id = (
        await client.get("/api/v1/escalations", headers=auth_headers(tokens["access_token"]))
    ).json()[0]["id"]
    await client.post(
        f"/api/v1/escalations/{case_id}/claim", headers=auth_headers(tokens["access_token"])
    )

    response = await client.post(
        f"/api/v1/escalations/{case_id}/respond",
        json={"content": "I'll just jump in here"},
        headers=auth_headers(other_token),
    )

    assert response.status_code == 403


async def test_release_case_returns_it_to_pending(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    await _force_unassigned_conversation(client, tokens["access_token"])
    case_id = (
        await client.get("/api/v1/escalations", headers=auth_headers(tokens["access_token"]))
    ).json()[0]["id"]
    await client.post(
        f"/api/v1/escalations/{case_id}/claim", headers=auth_headers(tokens["access_token"])
    )

    response = await client.post(
        f"/api/v1/escalations/{case_id}/release", headers=auth_headers(tokens["access_token"])
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["assigned_to"] is None
    assert body["assigned_at"] is None


async def test_release_case_not_in_progress_returns_409(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    await _force_unassigned_conversation(client, tokens["access_token"])
    case_id = (
        await client.get("/api/v1/escalations", headers=auth_headers(tokens["access_token"]))
    ).json()[0]["id"]

    response = await client.post(
        f"/api/v1/escalations/{case_id}/release", headers=auth_headers(tokens["access_token"])
    )

    assert response.status_code == 409


# --- listing / filters -----------------------------------------------------------------


async def test_list_escalations_filters_by_status(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    await _force_unassigned_conversation(client, tokens["access_token"])
    case_id = (
        await client.get("/api/v1/escalations", headers=auth_headers(tokens["access_token"]))
    ).json()[0]["id"]
    await client.post(
        f"/api/v1/escalations/{case_id}/claim", headers=auth_headers(tokens["access_token"])
    )

    pending = await client.get(
        "/api/v1/escalations",
        params={"status": "pending"},
        headers=auth_headers(tokens["access_token"]),
    )
    in_progress = await client.get(
        "/api/v1/escalations",
        params={"status": "in_progress"},
        headers=auth_headers(tokens["access_token"]),
    )

    assert pending.json() == []
    assert len(in_progress.json()) == 1


# --- isolation ---------------------------------------------------------------------------


async def test_escalations_isolated_by_tenant(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    await _force_unassigned_conversation(client, tenant_a["access_token"])
    case_id = (
        await client.get("/api/v1/escalations", headers=auth_headers(tenant_a["access_token"]))
    ).json()[0]["id"]

    list_b = await client.get("/api/v1/escalations", headers=auth_headers(tenant_b["access_token"]))
    assert list_b.json() == []

    get_b = await client.get(
        f"/api/v1/escalations/{case_id}", headers=auth_headers(tenant_b["access_token"])
    )
    assert get_b.status_code == 404

    claim_b = await client.post(
        f"/api/v1/escalations/{case_id}/claim", headers=auth_headers(tenant_b["access_token"])
    )
    assert claim_b.status_code == 404

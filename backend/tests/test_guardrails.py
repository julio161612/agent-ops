import uuid

from httpx import AsyncClient

from tests.helpers import (
    FakeAnthropicClient,
    auth_headers,
    make_text_response,
    make_tool_use_response,
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


# --- blocklist_keywords -------------------------------------------------------------


async def test_blocklist_keyword_blocks_input_and_never_calls_agent(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_policy(
        client, tokens["access_token"], config={"keywords": ["idiota"]}, action_on_violation="block"
    )

    body = await _send(client, tokens["access_token"], "eres un idiota", agent_id=agent["id"])

    assert body["assistant_message"]["metadata"]["guardrail_blocked"] is True
    assert body["assistant_message"]["metadata"]["stage"] == "input"
    violations = body["guardrail_violations"]
    assert len(violations) == 1
    assert violations[0]["violation_type"] == "blocklist_keywords"
    assert violations[0]["action_taken"] == "block"
    assert violations[0]["guardrail_type"] == "input"
    fake_anthropic_client.messages.create.assert_not_awaited()


async def test_blocklist_keyword_with_flag_action_still_runs_agent(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_policy(
        client, tokens["access_token"], config={"keywords": ["tonto"]}, action_on_violation="flag"
    )

    body = await _send(client, tokens["access_token"], "no seas tonto", agent_id=agent["id"])

    assert body["assistant_message"]["content"] == "Hello! How can I help you today?"
    assert len(body["guardrail_violations"]) == 1
    assert body["guardrail_violations"][0]["action_taken"] == "flag"
    fake_anthropic_client.messages.create.assert_awaited_once()


# --- max_length ---------------------------------------------------------------------


async def test_max_length_blocks_long_input(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_policy(
        client,
        tokens["access_token"],
        rule_type="max_length",
        config={"max_characters": 10},
        action_on_violation="block",
    )

    body = await _send(
        client,
        tokens["access_token"],
        "This message is way longer than ten characters",
        agent_id=agent["id"],
    )

    assert body["assistant_message"]["metadata"]["stage"] == "input"
    assert body["guardrail_violations"][0]["violation_type"] == "max_length"


async def test_max_length_allows_short_input(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_policy(
        client,
        tokens["access_token"],
        rule_type="max_length",
        config={"max_characters": 1000},
        action_on_violation="block",
    )

    body = await _send(client, tokens["access_token"], "short", agent_id=agent["id"])

    assert body["guardrail_violations"] == []
    assert body["assistant_message"]["content"] == "Hello! How can I help you today?"


# --- pii_detection --------------------------------------------------------------------


async def test_pii_email_is_detected_and_not_leaked_into_detail(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_policy(
        client,
        tokens["access_token"],
        rule_type="pii_detection",
        config={},
        action_on_violation="flag",
    )

    body = await _send(
        client,
        tokens["access_token"],
        "Contactame en juan.perez@example.com porfa",
        agent_id=agent["id"],
    )

    violation = body["guardrail_violations"][0]
    assert violation["violation_type"] == "pii_detection"
    assert "email" in violation["detail"]
    assert "juan.perez@example.com" not in violation["detail"]


async def test_pii_credit_card_is_detected(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_policy(
        client,
        tokens["access_token"],
        rule_type="pii_detection",
        config={},
        action_on_violation="flag",
    )

    body = await _send(
        client,
        tokens["access_token"],
        "Mi tarjeta es 4111 1111 1111 1111 gracias",
        agent_id=agent["id"],
    )

    assert "credit_card" in body["guardrail_violations"][0]["detail"]


async def test_pii_phone_is_detected(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_policy(
        client,
        tokens["access_token"],
        rule_type="pii_detection",
        config={},
        action_on_violation="flag",
    )

    body = await _send(
        client, tokens["access_token"], "Llamame al 612345678 cuando puedas", agent_id=agent["id"]
    )

    assert "phone" in body["guardrail_violations"][0]["detail"]


async def test_pii_spanish_dni_is_detected(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_policy(
        client,
        tokens["access_token"],
        rule_type="pii_detection",
        config={},
        action_on_violation="flag",
    )

    body = await _send(
        client, tokens["access_token"], "Mi DNI es 12345678Z para el tramite", agent_id=agent["id"]
    )

    assert "spanish_dni" in body["guardrail_violations"][0]["detail"]


async def test_pii_scoped_to_specific_pattern_only(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_policy(
        client,
        tokens["access_token"],
        rule_type="pii_detection",
        config={"patterns": ["email"]},
        action_on_violation="flag",
    )

    # Contains a DNI-shaped string but the policy only checks for emails.
    body = await _send(client, tokens["access_token"], "Mi DNI es 12345678Z", agent_id=agent["id"])

    assert body["guardrail_violations"] == []


# --- custom_llm_check -----------------------------------------------------------------


async def test_custom_llm_check_violation_blocks_output_and_escalates(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_policy(
        client,
        tokens["access_token"],
        guardrail_type="output",
        rule_type="custom_llm_check",
        config={"instruction": "Must not promise refunds"},
        action_on_violation="block",
    )
    fake_anthropic_client.messages.create.side_effect = [
        make_text_response(text="Sure, I'll refund you 100% right now, no questions asked!"),
        make_tool_use_response(
            tool_name="evaluate_policy",
            tool_input={"violates": True, "reason": "Promised an unauthorized refund"},
        ),
    ]

    body = await _send(client, tokens["access_token"], "Can I get a refund?", agent_id=agent["id"])

    assert body["conversation_status"] == "escalated"
    assert "refund" not in body["assistant_message"]["content"].lower()
    assert body["assistant_message"]["metadata"]["stage"] == "output"
    violation = body["guardrail_violations"][0]
    assert violation["violation_type"] == "custom_llm_check"
    assert violation["action_taken"] == "block"
    assert violation["detail"] == "Promised an unauthorized refund"

    # The original (blocked) reply must never surface via the history endpoint either —
    # only the user's own question is allowed to mention "refund".
    history = await client.get(
        f"/api/v1/conversations/{body['conversation_id']}/messages",
        headers=auth_headers(tokens["access_token"]),
    )
    assistant_messages = [m for m in history.json() if m["role"] == "assistant"]
    assert assistant_messages
    assert all("refund" not in m["content"].lower() for m in assistant_messages)


async def test_custom_llm_check_no_violation_passes_through(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_policy(
        client,
        tokens["access_token"],
        guardrail_type="output",
        rule_type="custom_llm_check",
        config={"instruction": "Must not promise refunds"},
        action_on_violation="block",
    )
    fake_anthropic_client.messages.create.side_effect = [
        make_text_response(text="Our return policy allows refunds within 30 days."),
        make_tool_use_response(
            tool_name="evaluate_policy",
            tool_input={"violates": False, "reason": "Accurate policy statement"},
        ),
    ]

    body = await _send(
        client, tokens["access_token"], "What's your refund policy?", agent_id=agent["id"]
    )

    assert body["conversation_status"] == "open"
    assert (
        body["assistant_message"]["content"] == "Our return policy allows refunds within 30 days."
    )
    assert body["guardrail_violations"] == []


async def test_custom_llm_check_malformed_response_flags_instead_of_blocking(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_policy(
        client,
        tokens["access_token"],
        guardrail_type="output",
        rule_type="custom_llm_check",
        config={"instruction": "Must not promise refunds"},
        action_on_violation="block",
    )
    # Second call (the guardrail check itself) returns plain text, no tool_use block —
    # simulates the model ignoring the forced tool call / an inconclusive check.
    fake_anthropic_client.messages.create.side_effect = [
        make_text_response(text="Here is some helpful information."),
        make_text_response(text="I'm not sure how to answer that."),
    ]

    body = await _send(client, tokens["access_token"], "Tell me something", agent_id=agent["id"])

    # Fails OPEN: never blocks on an inconclusive check, regardless of the policy's action.
    assert body["conversation_status"] == "open"
    assert body["assistant_message"]["content"] == "Here is some helpful information."
    violation = body["guardrail_violations"][0]
    assert violation["action_taken"] == "flag"
    assert "inconclusive" in violation["detail"]


# --- output blocklist (non-LLM output guardrail) --------------------------------------


async def test_output_blocklist_blocks_and_escalates(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_policy(
        client,
        tokens["access_token"],
        guardrail_type="output",
        config={"keywords": ["gratis"]},
        action_on_violation="block",
    )
    fake_anthropic_client.messages.create.return_value = make_text_response(
        text="Te lo regalamos completamente gratis, sin coste alguno!"
    )

    body = await _send(
        client, tokens["access_token"], "Que promociones tenéis?", agent_id=agent["id"]
    )

    assert body["conversation_status"] == "escalated"
    assert "gratis" not in body["assistant_message"]["content"].lower()


# --- listing & isolation ---------------------------------------------------------------


async def test_list_guardrail_violations_filters_by_conversation(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_policy(client, tokens["access_token"], config={"keywords": ["idiota"]})
    conversation_a = uuid.uuid4()
    conversation_b = uuid.uuid4()
    await _send(
        client,
        tokens["access_token"],
        "eres un idiota",
        agent_id=agent["id"],
        conversation_id=conversation_a,
    )
    await _send(
        client,
        tokens["access_token"],
        "eres un idiota",
        agent_id=agent["id"],
        conversation_id=conversation_b,
    )

    response = await client.get(
        "/api/v1/guardrail-violations",
        params={"conversation_id": str(conversation_a)},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["conversation_id"] == str(conversation_a)


async def test_guardrail_violations_isolated_by_tenant(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    agent_a = await _create_agent(client, tenant_a["access_token"])
    await _create_policy(client, tenant_a["access_token"], config={"keywords": ["idiota"]})
    await _send(client, tenant_a["access_token"], "eres un idiota", agent_id=agent_a["id"])

    response = await client.get(
        "/api/v1/guardrail-violations", headers=auth_headers(tenant_b["access_token"])
    )

    assert response.json() == []

import uuid

from httpx import AsyncClient

from tests.helpers import (
    FakeAnthropicClient,
    auth_headers,
    make_text_response,
    make_tool_use_response,
    register_tenant,
    upgrade_to_enterprise_plan,
)


async def _create_agent(client: AsyncClient, token: str, **overrides) -> dict:
    payload = {
        "name": "Agent",
        "system_prompt": "You are a helpful agent.",
        "model": "claude-sonnet-4-6",
        **overrides,
    }
    response = await client.post("/api/v1/agents", json=payload, headers=auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()


async def _create_rule(client: AsyncClient, token: str, **overrides) -> dict:
    payload = {"rule_type": "keyword", "condition": {"keywords": []}, "priority": 0, **overrides}
    response = await client.post("/api/v1/routing-rules", json=payload, headers=auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()


async def _send(client: AsyncClient, token: str, content: str, conversation_id=None) -> dict:
    conversation_id = conversation_id or uuid.uuid4()
    response = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": content},
        headers=auth_headers(token),
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- Level 1: rule-based routing --------------------------------------------------


async def test_keyword_rule_routes_message_to_configured_agent(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    billing_agent = await _create_agent(
        client, tokens["access_token"], name="Billing", agent_type="billing"
    )
    await _create_rule(
        client,
        tokens["access_token"],
        agent_id=billing_agent["id"],
        condition={"keywords": ["factura", "cobro"]},
    )

    body = await _send(client, tokens["access_token"], "Tengo una duda con mi factura de este mes")

    assert body["conversation_status"] == "open"
    assert body["routing"]["method"] == "rule"
    assert body["routing"]["agent_id"] == billing_agent["id"]
    assert body["routing"]["matched_rule_id"] is not None
    assert body["routing"]["confidence"] is None
    assert body["assistant_message"] is not None
    # Only the execution call happened, no LLM routing call.
    fake_anthropic_client.messages.create.assert_awaited_once()


async def test_category_rule_routes_unconditionally_for_matching_agent_type(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    billing_agent = await _create_agent(
        client, tokens["access_token"], name="Billing", agent_type="billing"
    )
    await _create_rule(
        client,
        tokens["access_token"],
        agent_id=billing_agent["id"],
        rule_type="category",
        condition={"agent_type": "billing"},
    )

    body = await _send(client, tokens["access_token"], "asdkjf random text with no keywords at all")

    assert body["routing"]["method"] == "rule"
    assert body["routing"]["agent_id"] == billing_agent["id"]


async def test_higher_priority_rule_wins_on_tie(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    await upgrade_to_enterprise_plan(client, tokens["access_token"])
    low_agent = await _create_agent(client, tokens["access_token"], name="Low")
    high_agent = await _create_agent(client, tokens["access_token"], name="High")
    await _create_rule(
        client,
        tokens["access_token"],
        agent_id=low_agent["id"],
        condition={"keywords": ["ayuda"]},
        priority=1,
    )
    await _create_rule(
        client,
        tokens["access_token"],
        agent_id=high_agent["id"],
        condition={"keywords": ["ayuda"]},
        priority=5,
    )

    body = await _send(client, tokens["access_token"], "necesito ayuda por favor")

    assert body["routing"]["agent_id"] == high_agent["id"]


async def test_inactive_rule_is_skipped(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    await upgrade_to_enterprise_plan(client, tokens["access_token"])
    rule_agent = await _create_agent(client, tokens["access_token"], name="RuleAgent")
    llm_agent = await _create_agent(client, tokens["access_token"], name="LLMAgent")
    await _create_rule(
        client,
        tokens["access_token"],
        agent_id=rule_agent["id"],
        condition={"keywords": ["ayuda"]},
        is_active=False,
    )
    fake_anthropic_client.messages.create.side_effect = [
        make_tool_use_response(
            tool_name="select_agent",
            tool_input={"agent_id": llm_agent["id"], "confidence": 0.9, "reasoning": "best fit"},
        ),
        make_text_response(text="Sure, I can help."),
    ]

    body = await _send(client, tokens["access_token"], "necesito ayuda por favor")

    assert body["routing"]["method"] == "llm"
    assert body["routing"]["agent_id"] == llm_agent["id"]


# --- Level 2: LLM router -----------------------------------------------------------


async def test_llm_router_high_confidence_selects_agent_and_replies(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    support_agent = await _create_agent(client, tokens["access_token"], name="Support")
    fake_anthropic_client.messages.create.side_effect = [
        make_tool_use_response(
            tool_name="select_agent",
            tool_input={
                "agent_id": support_agent["id"],
                "confidence": 0.87,
                "reasoning": "General support question",
            },
        ),
        make_text_response(text="Happy to help with that!"),
    ]

    body = await _send(client, tokens["access_token"], "My app keeps crashing, can you help?")

    assert body["conversation_status"] == "open"
    assert body["routing"]["method"] == "llm"
    assert body["routing"]["agent_id"] == support_agent["id"]
    assert body["routing"]["confidence"] == 0.87
    assert body["routing"]["reasoning"] == "General support question"
    assert body["assistant_message"]["content"] == "Happy to help with that!"


async def test_llm_router_low_confidence_leaves_conversation_unassigned(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    await _create_agent(client, tokens["access_token"], name="Support")
    fake_anthropic_client.messages.create.side_effect = [
        make_tool_use_response(
            tool_name="select_agent",
            tool_input={
                "agent_id": "",
                "confidence": 0.2,
                "reasoning": "Not sure this fits any agent",
            },
        ),
    ]

    body = await _send(client, tokens["access_token"], "asdkjfhaslkdjfh???")

    assert body["conversation_status"] == "unassigned"
    assert body["assistant_message"] is None
    assert body["routing"]["method"] == "llm"
    assert body["routing"]["agent_id"] is None
    assert body["routing"]["confidence"] == 0.2
    # Never runs the (nonexistent) agent.
    fake_anthropic_client.messages.create.assert_awaited_once()


async def test_llm_router_malformed_response_without_tool_use_is_handled_gracefully(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    await _create_agent(client, tokens["access_token"], name="Support")
    # Default FakeAnthropicClient response is a plain text block, no tool_use — simulates
    # the model ignoring the forced tool call.

    body = await _send(client, tokens["access_token"], "Hello?")

    assert body["conversation_status"] == "unassigned"
    assert body["assistant_message"] is None
    assert body["routing"]["agent_id"] is None
    assert "structured decision" in body["routing"]["reasoning"]


async def test_llm_router_agent_id_outside_candidates_is_rejected(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    await _create_agent(client, tokens["access_token"], name="Support")
    fake_anthropic_client.messages.create.side_effect = [
        make_tool_use_response(
            tool_name="select_agent",
            tool_input={
                "agent_id": str(uuid.uuid4()),  # not one of the tenant's agents
                "confidence": 0.95,
                "reasoning": "hallucinated agent id",
            },
        ),
    ]

    body = await _send(client, tokens["access_token"], "Hello?")

    assert body["conversation_status"] == "unassigned"
    assert body["routing"]["agent_id"] is None


async def test_no_active_agents_skips_llm_call_entirely(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)

    body = await _send(client, tokens["access_token"], "Hello, is anyone there?")

    assert body["conversation_status"] == "unassigned"
    assert body["routing"]["reasoning"] == "No active agents are configured for this tenant"
    fake_anthropic_client.messages.create.assert_not_awaited()


# --- Full flow / persistence --------------------------------------------------------


async def test_second_message_reuses_assigned_agent_without_rerouting(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"], name="Support")
    await _create_rule(
        client, tokens["access_token"], agent_id=agent["id"], condition={"keywords": ["ayuda"]}
    )
    conversation_id = uuid.uuid4()

    first = await _send(client, tokens["access_token"], "necesito ayuda", conversation_id)
    assert first["routing"]["method"] == "rule"

    second = await _send(client, tokens["access_token"], "gracias por la ayuda", conversation_id)

    assert second["routing"] is None  # no re-routing — conversation already has an agent
    assert second["conversation_status"] == "open"


async def test_routing_isolated_by_tenant(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    agent_a = await _create_agent(client, tenant_a["access_token"], name="A-Agent")
    await _create_rule(
        client,
        tenant_a["access_token"],
        agent_id=agent_a["id"],
        condition={"keywords": ["ayuda"]},
    )
    # Tenant B has no agents and no rules — its own request must not see Tenant A's rule.

    body = await _send(client, tenant_b["access_token"], "necesito ayuda")

    assert body["conversation_status"] == "unassigned"
    fake_anthropic_client.messages.create.assert_not_awaited()

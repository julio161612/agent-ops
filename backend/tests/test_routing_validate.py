from httpx import AsyncClient

from tests.helpers import auth_headers, register_tenant, upgrade_to_enterprise_plan

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


async def test_validate_matching_message_reports_winning_rule(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    rule = await _create_rule(client, tokens["access_token"], agent["id"])

    response = await client.post(
        "/api/v1/routing-rules/validate",
        json={"content": "tengo un problema con mi factura"},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["would_use_llm_router"] is False
    assert body["resulting_agent_id"] == agent["id"]
    assert body["resulting_agent_name"] == agent["name"]
    assert len(body["matched_rules"]) == 1
    assert body["matched_rules"][0]["rule_id"] == rule["id"]
    assert body["matched_rules"][0]["would_win"] is True


async def test_validate_no_match_falls_through_to_llm_router(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_rule(client, tokens["access_token"], agent["id"])

    response = await client.post(
        "/api/v1/routing-rules/validate",
        json={"content": "mensaje totalmente distinto sin relación"},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["would_use_llm_router"] is True
    assert body["resulting_agent_id"] is None
    assert body["matched_rules"] == []


async def test_validate_multiple_matches_only_highest_priority_wins(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    await upgrade_to_enterprise_plan(client, tokens["access_token"])
    agent_low = await _create_agent(client, tokens["access_token"], name="Low priority agent")
    agent_high = await _create_agent(client, tokens["access_token"], name="High priority agent")
    rule_low = await _create_rule(
        client,
        tokens["access_token"],
        agent_low["id"],
        condition={"keywords": ["factura"]},
        priority=1,
    )
    rule_high = await _create_rule(
        client,
        tokens["access_token"],
        agent_high["id"],
        condition={"keywords": ["factura"]},
        priority=10,
    )

    response = await client.post(
        "/api/v1/routing-rules/validate",
        json={"content": "duda sobre mi factura"},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["matched_rules"]) == 2
    assert body["resulting_agent_id"] == agent_high["id"]
    winners = {m["rule_id"]: m["would_win"] for m in body["matched_rules"]}
    assert winners[rule_high["id"]] is True
    assert winners[rule_low["id"]] is False


async def test_validate_never_creates_a_real_routing_decision(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    await _create_rule(client, tokens["access_token"], agent["id"])

    await client.post(
        "/api/v1/routing-rules/validate",
        json={"content": "tengo un problema con mi factura"},
        headers=auth_headers(tokens["access_token"]),
    )

    traces = await client.get("/api/v1/traces", headers=auth_headers(tokens["access_token"]))
    assert traces.json()["total"] == 0

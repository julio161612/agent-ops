from httpx import AsyncClient

from tests.helpers import auth_headers, register_tenant, upgrade_to_enterprise_plan

AGENT_PAYLOAD = {
    "name": "Support Agent",
    "system_prompt": "You are a helpful support agent.",
    "model": "claude-sonnet-4-6",
}


def _by_key(items: list[dict], key: str) -> dict:
    return next(i for i in items if i["key"] == key)


async def test_fresh_tenant_has_nothing_done(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    response = await client.get(
        "/api/v1/onboarding/status", headers=auth_headers(tokens["access_token"])
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["is_complete"] is False
    assert body["completed_count"] == 0
    assert _by_key(body["items"], "active_agent")["done"] is False
    assert _by_key(body["items"], "routing")["done"] is False
    assert _by_key(body["items"], "guardrails")["done"] is False
    assert _by_key(body["items"], "tenant_limits")["done"] is False
    assert _by_key(body["items"], "team")["done"] is False


async def test_onboarding_progresses_as_tenant_configures_itself(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    token = tokens["access_token"]
    # Free's included_users=1 (just the admin) would block the invite below —
    # this test is about onboarding progress, not plan limits themselves.
    await upgrade_to_enterprise_plan(client, token)

    agent = await client.post("/api/v1/agents", json=AGENT_PAYLOAD, headers=auth_headers(token))
    assert agent.status_code == 201, agent.text
    agent_id = agent.json()["id"]

    status_after_agent = (
        await client.get("/api/v1/onboarding/status", headers=auth_headers(token))
    ).json()
    assert _by_key(status_after_agent["items"], "active_agent")["done"] is True
    # no explicit rule yet, but an active agent means the LLM router can act
    assert _by_key(status_after_agent["items"], "routing")["done"] is True

    rule = await client.post(
        "/api/v1/routing-rules",
        json={
            "agent_id": agent_id,
            "rule_type": "keyword",
            "condition": {"keywords": ["factura"]},
        },
        headers=auth_headers(token),
    )
    assert rule.status_code == 201, rule.text

    policy = await client.post(
        "/api/v1/guardrail-policies",
        json={
            "guardrail_type": "input",
            "rule_type": "blocklist_keywords",
            "config": {"keywords": ["idiota"]},
            "action_on_violation": "block",
        },
        headers=auth_headers(token),
    )
    assert policy.status_code == 201, policy.text

    limits = await client.patch(
        "/api/v1/tenant-limits",
        json={"monthly_cost_limit_usd": "3.00"},
        headers=auth_headers(token),
    )
    assert limits.status_code == 200, limits.text

    invite = await client.post(
        "/api/v1/users",
        json={
            "email": "teammate@acme-corp.example.com",
            "password": "supersecret123",
            "role": "operator",
        },
        headers=auth_headers(token),
    )
    assert invite.status_code == 201, invite.text

    final_status = (
        await client.get("/api/v1/onboarding/status", headers=auth_headers(token))
    ).json()

    assert final_status["is_complete"] is True
    assert final_status["completed_count"] == final_status["total_count"]
    for item in final_status["items"]:
        assert item["done"] is True, item

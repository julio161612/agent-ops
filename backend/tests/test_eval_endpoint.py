from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import (
    FakeAnthropicClient,
    auth_headers,
    create_extra_user_token,
    register_tenant,
)


async def test_eval_run_requires_admin_role(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient, db_session: AsyncSession
) -> None:
    tokens = await register_tenant(client)
    me = await client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"]))
    tenant_id = me.json()["tenant"]["id"]
    member_token = await create_extra_user_token(db_session, tenant_id=tenant_id)

    response = await client.post("/api/v1/eval/run", headers=auth_headers(member_token))

    assert response.status_code == 403


async def test_eval_run_as_admin_returns_scoped_report(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient
) -> None:
    tokens = await register_tenant(client)

    response = await client.post("/api/v1/eval/run", headers=auth_headers(tokens["access_token"]))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"]["total_cases"] > 0
    # Only input-stage guardrail + edge_case categories, never the fixed-dataset
    # routing categories (their "expected agent" is meaningless here).
    assert all(
        r["category"]
        in {"guardrail_blocklist", "guardrail_pii", "guardrail_max_length", "edge_case"}
        for r in body["results"]
    )
    assert all(r["routing_correct"] is None for r in body["results"])
    assert len(body["routing_probe"]) == 3
    assert body["summary"]["total_cost_usd"] is not None

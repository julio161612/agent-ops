import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.anthropic_client import get_anthropic_client
from app.main import app
from app.models.interaction_trace import InteractionTrace
from app.models.invoice import Invoice
from app.models.plan import Plan
from app.services import billing_service
from tests.helpers import (
    FakeAnthropicClient,
    auth_headers,
    register_tenant,
    upgrade_to_enterprise_plan,
)

AGENT_PAYLOAD = {
    "name": "Support Agent",
    "system_prompt": "You are a helpful support agent.",
    "model": "claude-sonnet-4-6",
}


async def _create_agent(client: AsyncClient, token: str, *, name: str = "Support Agent") -> dict:
    payload = {**AGENT_PAYLOAD, "name": name}
    response = await client.post("/api/v1/agents", json=payload, headers=auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()


async def _tenant_id(client: AsyncClient, token: str) -> uuid.UUID:
    me = (await client.get("/api/v1/auth/me", headers=auth_headers(token))).json()
    return uuid.UUID(me["tenant"]["id"])


async def test_free_plan_blocks_creating_more_agents_than_included(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    await _create_agent(client, tokens["access_token"])  # Free includes exactly 1

    blocked = await client.post(
        "/api/v1/agents",
        json={**AGENT_PAYLOAD, "name": "Second Agent"},
        headers=auth_headers(tokens["access_token"]),
    )

    assert blocked.status_code == 422
    assert "Free" in blocked.json()["detail"]


async def test_message_quota_blocks_unless_overage_enabled(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient, db_session: AsyncSession
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    headers = auth_headers(tokens["access_token"])

    # A tiny custom plan keeps this test fast and independent of the seeded
    # catalog's real quotas (Free's 100/month would need 100+ real calls to
    # exercise the same boundary) while still exercising the real enforcement
    # path in agent_execution_service._enforce_budget.
    tiny_plan = Plan(
        name="Tiny Test Plan",
        slug="tiny-test-quota",
        monthly_price_usd=Decimal("10.00"),
        included_messages_per_month=2,
        included_active_agents=5,
        included_users=5,
        included_ai_cost_usd=None,
        max_messages_per_minute=60,
        overage_price_per_1000_messages_usd=Decimal("5.00"),
        is_active=True,
    )
    db_session.add(tiny_plan)
    await db_session.commit()
    await db_session.refresh(tiny_plan)

    change = await client.post(
        "/api/v1/subscription/change-plan",
        json={"plan_id": str(tiny_plan.id)},
        headers=headers,
    )
    assert change.status_code == 200, change.text

    conversation_id = uuid.uuid4()
    for _ in range(2):
        response = await client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"content": "hi", "agent_id": agent["id"]},
            headers=headers,
        )
        assert response.status_code == 200, response.text

    blocked = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "hi again", "agent_id": agent["id"]},
        headers=headers,
    )
    assert blocked.status_code == 429
    assert "quota" in blocked.json()["detail"].lower()

    # Switch the same plan into overage mode — the next message should now
    # go through instead of being blocked, and the excess gets recorded.
    enable_overage = await client.post(
        "/api/v1/subscription/change-plan",
        json={"plan_id": str(tiny_plan.id), "overage_enabled": True},
        headers=headers,
    )
    assert enable_overage.status_code == 200

    allowed = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"content": "hi once more", "agent_id": agent["id"]},
        headers=headers,
    )
    assert allowed.status_code == 200, allowed.text

    usage = await client.get("/api/v1/billing/current-usage", headers=headers)
    assert usage.status_code == 200
    usage_body = usage.json()
    assert usage_body["messages_used"] == 3
    assert usage_body["overage_messages"] == 1
    assert Decimal(str(usage_body["overage_cost_usd"])) > Decimal("0")


async def test_change_plan_has_immediate_effect_on_agent_limit(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    headers = auth_headers(tokens["access_token"])
    await _create_agent(client, tokens["access_token"], name="Agent One")

    still_free = await client.post(
        "/api/v1/agents", json={**AGENT_PAYLOAD, "name": "Agent Two"}, headers=headers
    )
    assert still_free.status_code == 422

    plans = (await client.get("/api/v1/plans", headers=headers)).json()
    starter_plan_id = next(p["id"] for p in plans if p["slug"] == "starter")
    change = await client.post(
        "/api/v1/subscription/change-plan", json={"plan_id": starter_plan_id}, headers=headers
    )
    assert change.status_code == 200
    assert change.json()["plan"]["slug"] == "starter"

    now_allowed = await client.post(
        "/api/v1/agents", json={**AGENT_PAYLOAD, "name": "Agent Two"}, headers=headers
    )
    assert now_allowed.status_code == 201


async def test_invoice_generation_matches_real_usage(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tokens = await register_tenant(client)
    await upgrade_to_enterprise_plan(client, tokens["access_token"])
    agent = await _create_agent(client, tokens["access_token"])
    headers = auth_headers(tokens["access_token"])
    tenant_id = await _tenant_id(client, tokens["access_token"])

    # Several interactions with distinct token counts -> distinct real costs,
    # each going through the real pipeline (routing/guardrails/execution),
    # not hand-inserted trace rows.
    token_counts = [(50, 20), (400, 150), (10, 5)]
    for input_tokens, output_tokens in token_counts:
        fake_client = FakeAnthropicClient(input_tokens=input_tokens, output_tokens=output_tokens)
        app.dependency_overrides[get_anthropic_client] = lambda fc=fake_client: fc
        response = await client.post(
            f"/api/v1/conversations/{uuid.uuid4()}/messages",
            json={"content": "hi", "agent_id": agent["id"]},
            headers=headers,
        )
        assert response.status_code == 200, response.text
    app.dependency_overrides.pop(get_anthropic_client, None)

    trace_costs = (
        (
            await db_session.execute(
                select(InteractionTrace.cost_usd).where(InteractionTrace.tenant_id == tenant_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(trace_costs) == 3
    assert len(set(trace_costs)) == 3, "the three calls should have produced three distinct costs"
    expected_total_cost = sum(trace_costs, Decimal("0"))

    now = datetime.now(UTC)
    invoice = await billing_service.generate_invoice(
        db_session, tenant_id=tenant_id, year=now.year, month=now.month
    )

    assert invoice.total_messages == 3
    assert invoice.plan_name_snapshot == "Enterprise"
    assert invoice.base_charge_usd == Decimal("499.00")
    assert invoice.included_messages == 3  # Enterprise has no monthly cap
    assert invoice.overage_messages == 0
    assert invoice.overage_cost_usd == Decimal("0")
    assert invoice.total_ai_cost_usd == expected_total_cost
    assert invoice.total_cost_usd == invoice.base_charge_usd + invoice.overage_cost_usd

    # Re-generating for the same period is idempotent, not a duplicate.
    again = await billing_service.generate_invoice(
        db_session, tenant_id=tenant_id, year=now.year, month=now.month
    )
    assert again.id == invoice.id

    count_result = await db_session.execute(
        select(func.count()).select_from(Invoice).where(Invoice.tenant_id == tenant_id)
    )
    assert count_result.scalar_one() == 1


async def test_invoice_generation_with_overage_computes_correct_charge(
    client: AsyncClient,
    fake_anthropic_client: FakeAnthropicClient,
    db_session: AsyncSession,
) -> None:
    tokens = await register_tenant(client)
    agent = await _create_agent(client, tokens["access_token"])
    headers = auth_headers(tokens["access_token"])
    tenant_id = await _tenant_id(client, tokens["access_token"])

    tiny_plan = Plan(
        name="Tiny Overage Plan",
        slug="tiny-overage-plan",
        monthly_price_usd=Decimal("20.00"),
        included_messages_per_month=1,
        included_active_agents=5,
        included_users=5,
        included_ai_cost_usd=None,
        max_messages_per_minute=60,
        overage_price_per_1000_messages_usd=Decimal("10.00"),
        is_active=True,
    )
    db_session.add(tiny_plan)
    await db_session.commit()
    await db_session.refresh(tiny_plan)

    await client.post(
        "/api/v1/subscription/change-plan",
        json={"plan_id": str(tiny_plan.id), "overage_enabled": True},
        headers=headers,
    )

    conversation_id = uuid.uuid4()
    for i in range(3):  # 1 included + 2 overage
        response = await client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"content": f"message {i}", "agent_id": agent["id"]},
            headers=headers,
        )
        assert response.status_code == 200, response.text

    now = datetime.now(UTC)
    invoice = await billing_service.generate_invoice(
        db_session, tenant_id=tenant_id, year=now.year, month=now.month
    )

    assert invoice.total_messages == 3
    assert invoice.included_messages == 1
    assert invoice.overage_messages == 2
    # 2 messages / 1000 * $10.00 per 1000
    expected_overage = (Decimal(2) / Decimal(1000) * Decimal("10.00")).quantize(
        Decimal("0.000001"), rounding=ROUND_HALF_UP
    )
    assert invoice.overage_cost_usd == expected_overage
    assert invoice.total_cost_usd == invoice.base_charge_usd + invoice.overage_cost_usd
    assert invoice.total_cost_usd == Decimal("20.00") + expected_overage


async def test_billing_isolated_by_tenant(client: AsyncClient, db_session: AsyncSession) -> None:
    tenant_a = await register_tenant(
        client, company_name="Tenant A", email="admin@tenant-a.example.com"
    )
    tenant_b = await register_tenant(
        client, company_name="Tenant B", email="admin@tenant-b.example.com"
    )
    tenant_a_id = await _tenant_id(client, tenant_a["access_token"])
    tenant_b_id = await _tenant_id(client, tenant_b["access_token"])

    now = datetime.now(UTC)
    invoice_a = await billing_service.generate_invoice(
        db_session, tenant_id=tenant_a_id, year=now.year, month=now.month
    )
    await billing_service.generate_invoice(
        db_session, tenant_id=tenant_b_id, year=now.year, month=now.month
    )

    # Tenant B can't see tenant A's invoices list or fetch it by id.
    list_b = await client.get(
        "/api/v1/billing/invoices", headers=auth_headers(tenant_b["access_token"])
    )
    assert list_b.status_code == 200
    assert all(inv["tenant_id"] == str(tenant_b_id) for inv in list_b.json())

    fetch_a_from_b = await client.get(
        f"/api/v1/billing/invoices/{invoice_a.id}", headers=auth_headers(tenant_b["access_token"])
    )
    assert fetch_a_from_b.status_code == 404

    fetch_a_from_a = await client.get(
        f"/api/v1/billing/invoices/{invoice_a.id}", headers=auth_headers(tenant_a["access_token"])
    )
    assert fetch_a_from_a.status_code == 200

    usage_a = await client.get(
        "/api/v1/billing/current-usage", headers=auth_headers(tenant_a["access_token"])
    )
    usage_b = await client.get(
        "/api/v1/billing/current-usage", headers=auth_headers(tenant_b["access_token"])
    )
    assert usage_a.status_code == 200
    assert usage_b.status_code == 200

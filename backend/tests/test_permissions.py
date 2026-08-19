import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserRole
from tests.helpers import (
    auth_headers,
    create_extra_user_token,
    register_tenant,
    upgrade_to_enterprise_plan,
)

AGENT_PAYLOAD = {
    "name": "Support Agent",
    "system_prompt": "You are a helpful support agent.",
    "model": "claude-sonnet-4-6",
}


async def test_viewer_cannot_create_agent(client: AsyncClient, db_session: AsyncSession) -> None:
    tokens = await register_tenant(client)
    admin = await client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"]))
    tenant_id = admin.json()["tenant"]["id"]
    viewer_token = await create_extra_user_token(
        db_session, tenant_id=tenant_id, email="viewer@acme-corp.example.com", role=UserRole.VIEWER
    )

    response = await client.post(
        "/api/v1/agents", json=AGENT_PAYLOAD, headers=auth_headers(viewer_token)
    )

    assert response.status_code == 403


async def test_viewer_can_list_agents(client: AsyncClient, db_session: AsyncSession) -> None:
    tokens = await register_tenant(client)
    admin = await client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"]))
    tenant_id = admin.json()["tenant"]["id"]
    viewer_token = await create_extra_user_token(
        db_session, tenant_id=tenant_id, email="viewer@acme-corp.example.com", role=UserRole.VIEWER
    )

    response = await client.get("/api/v1/agents", headers=auth_headers(viewer_token))

    assert response.status_code == 200


async def test_operator_can_create_agent(client: AsyncClient, db_session: AsyncSession) -> None:
    tokens = await register_tenant(client)
    admin = await client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"]))
    tenant_id = admin.json()["tenant"]["id"]
    operator_token = await create_extra_user_token(
        db_session,
        tenant_id=tenant_id,
        email="operator@acme-corp.example.com",
        role=UserRole.OPERATOR,
    )

    response = await client.post(
        "/api/v1/agents", json=AGENT_PAYLOAD, headers=auth_headers(operator_token)
    )

    assert response.status_code == 201, response.text


async def test_operator_cannot_invite_users(client: AsyncClient, db_session: AsyncSession) -> None:
    tokens = await register_tenant(client)
    admin = await client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"]))
    tenant_id = admin.json()["tenant"]["id"]
    operator_token = await create_extra_user_token(
        db_session,
        tenant_id=tenant_id,
        email="operator@acme-corp.example.com",
        role=UserRole.OPERATOR,
    )

    response = await client.post(
        "/api/v1/users",
        json={"email": "new@acme-corp.example.com", "password": "supersecret123", "role": "viewer"},
        headers=auth_headers(operator_token),
    )

    assert response.status_code == 403


async def test_admin_can_invite_users(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    await upgrade_to_enterprise_plan(client, tokens["access_token"])  # Free's included_users=1

    response = await client.post(
        "/api/v1/users",
        json={
            "email": "new@acme-corp.example.com",
            "password": "supersecret123",
            "role": "operator",
        },
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 201, response.text
    assert response.json()["role"] == "operator"
    assert response.json()["is_active"] is True


async def test_viewer_cannot_send_message(client: AsyncClient, db_session: AsyncSession) -> None:
    tokens = await register_tenant(client)
    admin = await client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"]))
    tenant_id = admin.json()["tenant"]["id"]
    viewer_token = await create_extra_user_token(
        db_session, tenant_id=tenant_id, email="viewer@acme-corp.example.com", role=UserRole.VIEWER
    )

    response = await client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        json={"content": "hola"},
        headers=auth_headers(viewer_token),
    )

    assert response.status_code == 403


async def test_viewer_can_read_traces_and_metrics(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tokens = await register_tenant(client)
    admin = await client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"]))
    tenant_id = admin.json()["tenant"]["id"]
    viewer_token = await create_extra_user_token(
        db_session, tenant_id=tenant_id, email="viewer@acme-corp.example.com", role=UserRole.VIEWER
    )

    traces_response = await client.get("/api/v1/traces", headers=auth_headers(viewer_token))
    metrics_response = await client.get(
        "/api/v1/metrics/summary", headers=auth_headers(viewer_token)
    )

    assert traces_response.status_code == 200
    assert metrics_response.status_code == 200


async def test_operator_cannot_patch_tenant_limits(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tokens = await register_tenant(client)
    admin = await client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"]))
    tenant_id = admin.json()["tenant"]["id"]
    operator_token = await create_extra_user_token(
        db_session,
        tenant_id=tenant_id,
        email="operator@acme-corp.example.com",
        role=UserRole.OPERATOR,
    )

    response = await client.patch(
        "/api/v1/tenant-limits",
        json={"messages_per_minute_limit": 10},
        headers=auth_headers(operator_token),
    )

    assert response.status_code == 403


async def test_admin_can_patch_tenant_limits(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    response = await client.patch(
        "/api/v1/tenant-limits",
        json={"messages_per_minute_limit": 10},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 200, response.text
    assert response.json()["messages_per_minute_limit"] == 10


async def test_deactivated_user_cannot_authenticate(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tokens = await register_tenant(client)
    admin = await client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"]))
    tenant_id = admin.json()["tenant"]["id"]
    operator_token = await create_extra_user_token(
        db_session,
        tenant_id=tenant_id,
        email="operator@acme-corp.example.com",
        password="supersecret123",
        role=UserRole.OPERATOR,
    )

    # sanity check: works before deactivation
    me_before = await client.get("/api/v1/auth/me", headers=auth_headers(operator_token))
    assert me_before.status_code == 200
    user_id = me_before.json()["user"]["id"]

    deactivate = await client.post(
        f"/api/v1/users/{user_id}/deactivate", headers=auth_headers(tokens["access_token"])
    )
    assert deactivate.status_code == 200, deactivate.text
    assert deactivate.json()["is_active"] is False

    # the already-issued token is now rejected
    me_after = await client.get("/api/v1/auth/me", headers=auth_headers(operator_token))
    assert me_after.status_code == 401

    # and a fresh login attempt also fails
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "operator@acme-corp.example.com", "password": "supersecret123"},
    )
    assert login.status_code == 401


async def test_admin_cannot_deactivate_self(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    me = await client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"]))
    user_id = me.json()["user"]["id"]

    response = await client.post(
        f"/api/v1/users/{user_id}/deactivate", headers=auth_headers(tokens["access_token"])
    )

    assert response.status_code == 400


async def test_cannot_demote_last_active_admin(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    me = await client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"]))
    user_id = me.json()["user"]["id"]

    response = await client.patch(
        f"/api/v1/users/{user_id}",
        json={"role": "operator"},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 409

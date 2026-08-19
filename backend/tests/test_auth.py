from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

REGISTER_PAYLOAD = {
    "company_name": "Acme Corp",
    "email": "admin@acme-corp.example.com",
    "password": "supersecret123",
}


async def test_register_creates_tenant_and_returns_tokens(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    first = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/auth/register",
        json={**REGISTER_PAYLOAD, "company_name": "Another Co"},
    )

    assert second.status_code == 409
    assert second.json()["detail"] == "Email already registered"


async def test_login_with_correct_credentials_succeeds(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": REGISTER_PAYLOAD["email"], "password": REGISTER_PAYLOAD["password"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body


async def test_login_with_wrong_password_returns_401(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": REGISTER_PAYLOAD["email"], "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


async def test_login_with_unknown_email_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@nowhere.example.com", "password": "whatever123"},
    )

    assert response.status_code == 401


async def test_me_returns_authenticated_user_and_tenant(client: AsyncClient) -> None:
    register_response = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    access_token = register_response.json()["access_token"]

    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["email"] == REGISTER_PAYLOAD["email"]
    assert body["user"]["role"] == "admin"
    assert body["tenant"]["name"] == REGISTER_PAYLOAD["company_name"]


async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")

    assert response.status_code in (401, 403)


async def test_refresh_with_valid_refresh_token_returns_new_pair(client: AsyncClient) -> None:
    register_response = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    tokens = register_response.json()

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"

    # The new access token actually works.
    me_response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me_response.status_code == 200


async def test_refresh_with_access_token_instead_of_refresh_token_returns_401(
    client: AsyncClient,
) -> None:
    register_response = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    tokens = register_response.json()

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )

    assert response.status_code == 401


async def test_refresh_with_garbage_token_returns_401(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-jwt"})

    assert response.status_code == 401


async def test_refresh_for_deactivated_user_returns_401(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    register_response = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    tokens = register_response.json()

    result = await db_session.execute(select(User).where(User.email == REGISTER_PAYLOAD["email"]))
    user = result.scalar_one()
    user.is_active = False
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 401

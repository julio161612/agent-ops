from httpx import AsyncClient

from tests.helpers import auth_headers, register_tenant


async def test_create_server_key_returns_raw_key_once(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    response = await client.post(
        "/api/v1/api-keys",
        json={"name": "Backend integration", "key_type": "server"},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["api_key"].startswith("ao_sk_")
    assert body["key_prefix"] == body["api_key"][:12]
    assert body["key_type"] == "server"
    assert body["can_send_messages"] is True
    assert body["is_active"] is True
    assert body["last_used_at"] is None


async def test_create_widget_key_has_distinct_prefix(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    response = await client.post(
        "/api/v1/api-keys",
        json={"name": "Website widget", "key_type": "widget"},
        headers=auth_headers(tokens["access_token"]),
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["api_key"].startswith("ao_pk_")
    assert not body["api_key"].startswith("ao_sk_")


async def test_list_api_keys_never_exposes_raw_key(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    await client.post(
        "/api/v1/api-keys",
        json={"name": "Backend integration", "key_type": "server"},
        headers=auth_headers(tokens["access_token"]),
    )

    response = await client.get("/api/v1/api-keys", headers=auth_headers(tokens["access_token"]))

    assert response.status_code == 200, response.text
    keys = response.json()
    assert len(keys) == 1
    assert "api_key" not in keys[0]
    assert keys[0]["key_prefix"].startswith("ao_sk_")


async def test_revoked_key_stops_working_immediately(client: AsyncClient) -> None:
    tokens = await register_tenant(client)
    create = await client.post(
        "/api/v1/api-keys",
        json={"name": "Backend integration", "key_type": "server"},
        headers=auth_headers(tokens["access_token"]),
    )
    raw_key = create.json()["api_key"]
    key_id = create.json()["id"]

    working = await client.post(
        "/public/v1/messages",
        json={"content": "hola", "external_user_id": "user-1"},
        headers={"X-API-Key": raw_key},
    )
    assert working.status_code == 200, working.text

    revoke = await client.delete(
        f"/api/v1/api-keys/{key_id}", headers=auth_headers(tokens["access_token"])
    )
    assert revoke.status_code == 204

    after_revoke = await client.post(
        "/public/v1/messages",
        json={"content": "hola de nuevo", "external_user_id": "user-1"},
        headers={"X-API-Key": raw_key},
    )
    assert after_revoke.status_code == 401

    keys = (
        await client.get("/api/v1/api-keys", headers=auth_headers(tokens["access_token"]))
    ).json()
    assert keys[0]["is_active"] is False


async def test_missing_api_key_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/public/v1/messages", json={"content": "hola", "external_user_id": "user-1"}
    )
    assert response.status_code == 401


async def test_bogus_api_key_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/public/v1/messages",
        json={"content": "hola", "external_user_id": "user-1"},
        headers={"X-API-Key": "ao_sk_totally-made-up-value"},
    )
    assert response.status_code == 401

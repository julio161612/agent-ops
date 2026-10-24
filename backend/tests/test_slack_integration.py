import uuid
from unittest.mock import AsyncMock

import httpx
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import UserRole
from tests.helpers import (
    FakeAnthropicClient,
    auth_headers,
    create_extra_user_token,
    register_tenant,
)

_WEBHOOK_URL = "https://hooks.slack.example.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"


def _mock_slack_post(monkeypatch, *, status_code: int = 200, text: str = "ok") -> AsyncMock:
    """Patches httpx.AsyncClient.post so calls to the Slack webhook URL get a
    canned response — WITHOUT touching real network I/O.

    Patching at the class level affects every AsyncClient instance in the
    process, including the test's own ``client`` fixture (also an
    httpx.AsyncClient, wrapping ASGITransport to drive requests against our
    own app). So the fake only intercepts calls to the exact webhook URL;
    anything else (i.e. the test driving our actual API) falls through to
    the real implementation.

    ``httpx.AsyncClient.post`` is patched with a plain function (not an
    AsyncMock) so normal method-binding still applies (``client.post(...)``
    needs ``self`` filled in to delegate to the real implementation for the
    pass-through case) — the returned AsyncMock only *records* the calls
    that actually hit the fake webhook path, for assertions.
    """
    fake_response = httpx.Response(
        status_code, request=httpx.Request("POST", _WEBHOOK_URL), text=text
    )
    original_post = httpx.AsyncClient.post
    recorder = AsyncMock(return_value=fake_response)

    async def _dispatch(self, url, *args, **kwargs):
        if str(url) == _WEBHOOK_URL:
            return await recorder(url, *args, **kwargs)
        return await original_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", _dispatch)
    return recorder


async def test_configure_slack_webhook_masks_url_on_read(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    configure = await client.post(
        "/api/v1/integrations/slack",
        json={"webhook_url": _WEBHOOK_URL},
        headers=auth_headers(tokens["access_token"]),
    )
    assert configure.status_code == 200, configure.text
    assert configure.json()["configured"] is True
    assert _WEBHOOK_URL not in configure.text
    assert configure.json()["masked_webhook_url"].startswith("https://hooks.slack.example.com/")

    read = await client.get(
        "/api/v1/integrations/slack", headers=auth_headers(tokens["access_token"])
    )
    assert read.status_code == 200, read.text
    assert read.json()["configured"] is True
    assert _WEBHOOK_URL not in read.text


async def test_slack_status_before_configuration(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    response = await client.get(
        "/api/v1/integrations/slack", headers=auth_headers(tokens["access_token"])
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"configured": False, "masked_webhook_url": None}


async def test_slack_test_without_configuration_reports_not_sent(client: AsyncClient) -> None:
    tokens = await register_tenant(client)

    response = await client.post(
        "/api/v1/integrations/slack/test", headers=auth_headers(tokens["access_token"])
    )

    assert response.status_code == 200, response.text
    assert response.json()["sent"] is False


async def test_slack_test_sends_real_http_post_to_webhook(client: AsyncClient, monkeypatch) -> None:
    tokens = await register_tenant(client)
    await client.post(
        "/api/v1/integrations/slack",
        json={"webhook_url": _WEBHOOK_URL},
        headers=auth_headers(tokens["access_token"]),
    )
    post_mock = _mock_slack_post(monkeypatch)

    response = await client.post(
        "/api/v1/integrations/slack/test", headers=auth_headers(tokens["access_token"])
    )

    assert response.status_code == 200, response.text
    assert response.json()["sent"] is True
    post_mock.assert_awaited_once()
    call_args, call_kwargs = post_mock.call_args
    assert call_args[0] == _WEBHOOK_URL
    assert "prueba" in call_kwargs["json"]["text"].lower()


async def test_slack_test_reports_failure_when_webhook_rejects(
    client: AsyncClient, monkeypatch
) -> None:
    tokens = await register_tenant(client)
    await client.post(
        "/api/v1/integrations/slack",
        json={"webhook_url": _WEBHOOK_URL},
        headers=auth_headers(tokens["access_token"]),
    )
    _mock_slack_post(monkeypatch, status_code=404, text="no_service")

    response = await client.post(
        "/api/v1/integrations/slack/test", headers=auth_headers(tokens["access_token"])
    )

    assert response.status_code == 200, response.text
    assert response.json()["sent"] is False
    assert "404" in response.json()["detail"]


async def test_real_escalation_triggers_slack_notification(
    client: AsyncClient, fake_anthropic_client: FakeAnthropicClient, monkeypatch
) -> None:
    tokens = await register_tenant(client)
    await client.post(
        "/api/v1/integrations/slack",
        json={"webhook_url": _WEBHOOK_URL},
        headers=auth_headers(tokens["access_token"]),
    )
    post_mock = _mock_slack_post(monkeypatch)

    # zero agents configured -> routing always fails -> triggers an escalation
    response = await client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/messages",
        json={"content": "hola, hay alguien?"},
        headers=auth_headers(tokens["access_token"]),
    )
    assert response.status_code == 200, response.text
    assert response.json()["conversation_status"] == "unassigned"

    post_mock.assert_awaited_once()
    _, call_kwargs = post_mock.call_args
    sent_text = call_kwargs["json"]["text"]
    assert "escalado" in sent_text.lower()
    assert "https://app.agentops.dev/escalations/" in sent_text


async def test_non_admin_cannot_configure_slack(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tokens = await register_tenant(client)
    me = await client.get("/api/v1/auth/me", headers=auth_headers(tokens["access_token"]))
    tenant_id = me.json()["tenant"]["id"]
    operator_token = await create_extra_user_token(
        db_session,
        tenant_id=tenant_id,
        email="operator@acme-corp.example.com",
        role=UserRole.OPERATOR,
    )

    response = await client.post(
        "/api/v1/integrations/slack",
        json={"webhook_url": _WEBHOOK_URL},
        headers=auth_headers(operator_token),
    )

    assert response.status_code == 403

import logging
import uuid
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.escalation_case import EscalationCase
from app.models.tenant_integrations import TenantIntegrations

logger = logging.getLogger("agent_ops.integrations")


async def get_or_create_integrations(
    db: AsyncSession, *, tenant_id: uuid.UUID
) -> TenantIntegrations:
    result = await db.execute(
        select(TenantIntegrations).where(TenantIntegrations.tenant_id == tenant_id)
    )
    integrations = result.scalar_one_or_none()
    if integrations is None:
        integrations = TenantIntegrations(tenant_id=tenant_id)
        db.add(integrations)
        await db.flush()
    return integrations


async def set_slack_webhook_url(
    db: AsyncSession, *, tenant_id: uuid.UUID, webhook_url: str
) -> TenantIntegrations:
    integrations = await get_or_create_integrations(db, tenant_id=tenant_id)
    integrations.slack_webhook_url = webhook_url
    await db.commit()
    await db.refresh(integrations)
    return integrations


def mask_webhook_url(url: str) -> str:
    """Show enough to recognize the integration (scheme + host + a few
    trailing chars) without exposing the bearer token embedded in a Slack
    incoming-webhook path — anyone with the full URL can post into that
    channel, so it gets the same "never shown again in full" treatment as an
    API key.
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/***{url[-6:]}"


def _escalation_slack_text(case: EscalationCase) -> str:
    return (
        f":rotating_light: *Nuevo caso de escalado* ({case.reason.value})\n"
        f"Tenant: `{case.tenant_id}`\n"
        f"Conversación: `{case.conversation_id}`\n"
        f"Ver caso: https://app.agentops.dev/escalations/{case.id}"
    )


async def send_slack_message(webhook_url: str, *, text: str) -> tuple[bool, str]:
    """POST to a Slack incoming webhook. Returns (sent, detail).

    Never raises — a broken/misconfigured webhook shouldn't take down the
    escalation flow that triggered it; the caller decides what "sent=False"
    means for its own response (e.g. the /test endpoint surfaces it to the
    admin who just configured it, but automatic escalation notifications
    only log it).
    """
    try:
        async with httpx.AsyncClient(timeout=settings.SLACK_WEBHOOK_TIMEOUT_SECONDS) as client:
            response = await client.post(webhook_url, json={"text": text})
    except httpx.HTTPError as exc:
        return False, f"Request to Slack failed: {exc}"

    if response.status_code >= 300:
        return False, f"Slack returned status {response.status_code}: {response.text[:200]}"
    return True, "ok"


async def notify_escalation_via_slack(db: AsyncSession, *, case: EscalationCase) -> None:
    """Best-effort — logs the outcome either way, never raises into the
    escalation flow that called it.
    """
    integrations = await get_or_create_integrations(db, tenant_id=case.tenant_id)
    if not integrations.slack_webhook_url:
        return

    sent, detail = await send_slack_message(
        integrations.slack_webhook_url, text=_escalation_slack_text(case)
    )
    logger.info(
        "slack_escalation_notification",
        extra={
            "escalation_case_id": str(case.id),
            "tenant_id": str(case.tenant_id),
            "sent": sent,
            "detail": detail,
        },
    )

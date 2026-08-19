import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id, require_role
from app.core.database import get_db
from app.models.user import UserRole
from app.schemas.integrations import SlackIntegrationRead, SlackTestResult, SlackWebhookConfigure
from app.services import integration_service

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get(
    "/slack",
    response_model=SlackIntegrationRead,
    dependencies=[Depends(require_role(UserRole.VIEWER))],
)
async def get_slack_integration(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> SlackIntegrationRead:
    integrations = await integration_service.get_or_create_integrations(db, tenant_id=tenant_id)
    if not integrations.slack_webhook_url:
        return SlackIntegrationRead(configured=False)
    return SlackIntegrationRead(
        configured=True,
        masked_webhook_url=integration_service.mask_webhook_url(integrations.slack_webhook_url),
    )


@router.post(
    "/slack",
    response_model=SlackIntegrationRead,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def configure_slack_integration(
    payload: SlackWebhookConfigure,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> SlackIntegrationRead:
    integrations = await integration_service.set_slack_webhook_url(
        db, tenant_id=tenant_id, webhook_url=str(payload.webhook_url)
    )
    return SlackIntegrationRead(
        configured=True,
        masked_webhook_url=integration_service.mask_webhook_url(integrations.slack_webhook_url),
    )


@router.post(
    "/slack/test",
    response_model=SlackTestResult,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def test_slack_integration(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> SlackTestResult:
    integrations = await integration_service.get_or_create_integrations(db, tenant_id=tenant_id)
    if not integrations.slack_webhook_url:
        return SlackTestResult(sent=False, detail="No Slack webhook configured for this tenant.")

    sent, detail = await integration_service.send_slack_message(
        integrations.slack_webhook_url,
        text=":white_check_mark: Agent Ops — mensaje de prueba de la integración con Slack.",
    )
    return SlackTestResult(sent=sent, detail=detail)

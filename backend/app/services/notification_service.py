import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.escalation_case import EscalationCase
from app.services import integration_service

logger = logging.getLogger("agent_ops.notifications")


async def notify_escalation(db: AsyncSession, case: EscalationCase) -> None:
    """Extension point for real notifications (Slack, email, PagerDuty...).

    Always emits a structured log line, and — since Phase 9 — also fires a
    real Slack message if the tenant has configured a webhook (see
    integration_service.notify_escalation_via_slack, which is itself
    best-effort and never raises). Adding a new channel later is a drop-in
    change here — the call site in AgentExecutionService / escalation_service
    doesn't need to change.
    """
    logger.info(
        "escalation_case_created",
        extra={
            "escalation_case_id": str(case.id),
            "tenant_id": str(case.tenant_id),
            "conversation_id": str(case.conversation_id),
            "reason": case.reason.value,
        },
    )
    await integration_service.notify_escalation_via_slack(db, case=case)

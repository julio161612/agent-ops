import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.guardrail_violation import GuardrailViolation


async def list_violations(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
) -> list[GuardrailViolation]:
    stmt = select(GuardrailViolation).where(GuardrailViolation.tenant_id == tenant_id)
    if conversation_id is not None:
        stmt = stmt.where(GuardrailViolation.conversation_id == conversation_id)
    if created_after is not None:
        stmt = stmt.where(GuardrailViolation.created_at >= created_after)
    if created_before is not None:
        stmt = stmt.where(GuardrailViolation.created_at <= created_before)
    stmt = stmt.order_by(GuardrailViolation.created_at.desc())

    result = await db.execute(stmt)
    return list(result.scalars().all())

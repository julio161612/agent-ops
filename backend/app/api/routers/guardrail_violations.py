import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id, require_role
from app.core.database import get_db
from app.models.user import UserRole
from app.schemas.guardrail_violation import GuardrailViolationRead
from app.services import guardrail_violation_service

router = APIRouter(prefix="/guardrail-violations", tags=["guardrail-violations"])


@router.get(
    "",
    response_model=list[GuardrailViolationRead],
    dependencies=[Depends(require_role(UserRole.VIEWER))],
)
async def list_violations(
    conversation_id: uuid.UUID | None = Query(default=None),
    created_after: datetime | None = Query(default=None),
    created_before: datetime | None = Query(default=None),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> list[GuardrailViolationRead]:
    violations = await guardrail_violation_service.list_violations(
        db,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        created_after=created_after,
        created_before=created_before,
    )
    return [GuardrailViolationRead.model_validate(v) for v in violations]

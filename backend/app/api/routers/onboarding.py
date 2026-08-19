import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id, require_role
from app.core.database import get_db
from app.models.user import UserRole
from app.schemas.onboarding import OnboardingItemRead, OnboardingStatusRead
from app.services import onboarding_service

router = APIRouter(
    prefix="/onboarding", tags=["onboarding"], dependencies=[Depends(require_role(UserRole.VIEWER))]
)


@router.get("/status", response_model=OnboardingStatusRead)
async def get_onboarding_status(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> OnboardingStatusRead:
    """Guided-setup checklist for the current tenant — what a future frontend
    would use to walk a new customer through initial configuration step by
    step. Purely a read: derived live from existing tables, nothing new to
    keep in sync.
    """
    onboarding_status = await onboarding_service.get_onboarding_status(db, tenant_id=tenant_id)
    return OnboardingStatusRead(
        items=[
            OnboardingItemRead(key=i.key, label=i.label, done=i.done, detail=i.detail)
            for i in onboarding_status.items
        ],
        completed_count=onboarding_status.completed_count,
        total_count=onboarding_status.total_count,
        is_complete=onboarding_status.is_complete,
    )

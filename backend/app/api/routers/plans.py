from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.database import get_db
from app.models.user import UserRole
from app.schemas.plan import PlanRead
from app.services import subscription_service

router = APIRouter(
    prefix="/plans", tags=["plans"], dependencies=[Depends(require_role(UserRole.VIEWER))]
)


@router.get("", response_model=list[PlanRead])
async def list_plans(db: AsyncSession = Depends(get_db)) -> list[PlanRead]:
    """The global plan catalog — not tenant-scoped, just requires auth. Only
    active plans (retired ones stay in the DB for existing subscriptions and
    invoices, but aren't offered for new sign-ups/changes)."""
    plans = await subscription_service.list_plans(db, active_only=True)
    return [PlanRead.model_validate(p) for p in plans]

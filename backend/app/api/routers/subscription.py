import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id, require_role
from app.core.database import get_db
from app.core.exceptions import PlanNotActiveError, PlanNotFoundError
from app.models.plan import Plan
from app.models.tenant_subscription import TenantSubscription
from app.models.user import UserRole
from app.schemas.plan import PlanRead
from app.schemas.subscription import ChangePlanRequest, SubscriptionWithPlanRead
from app.services import subscription_service

router = APIRouter(prefix="/subscription", tags=["subscription"])


def _to_response(subscription: TenantSubscription, plan: Plan) -> SubscriptionWithPlanRead:
    return SubscriptionWithPlanRead(
        id=subscription.id,
        tenant_id=subscription.tenant_id,
        plan_id=subscription.plan_id,
        status=subscription.status,
        started_at=subscription.started_at,
        overage_enabled=subscription.overage_enabled,
        plan=PlanRead.model_validate(plan),
    )


@router.get(
    "",
    response_model=SubscriptionWithPlanRead,
    dependencies=[Depends(require_role(UserRole.VIEWER))],
)
async def get_subscription(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionWithPlanRead:
    subscription = await subscription_service.get_or_create_subscription(db, tenant_id=tenant_id)
    plan = await subscription_service.get_plan(db, plan_id=subscription.plan_id)
    return _to_response(subscription, plan)


@router.post(
    "/change-plan",
    response_model=SubscriptionWithPlanRead,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def change_plan(
    payload: ChangePlanRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionWithPlanRead:
    """Switch plans, effective immediately (no proration — see
    subscription_service.change_plan's docstring for the full reasoning).
    """
    try:
        subscription = await subscription_service.change_plan(
            db,
            tenant_id=tenant_id,
            plan_id=payload.plan_id,
            overage_enabled=payload.overage_enabled,
        )
    except PlanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found") from exc
    except PlanNotActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="This plan is no longer available for new subscriptions",
        ) from exc

    plan = await subscription_service.get_plan(db, plan_id=subscription.plan_id)
    return _to_response(subscription, plan)

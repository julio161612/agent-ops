import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id, require_role
from app.core.database import get_db
from app.models.user import UserRole
from app.schemas.metrics import MetricsSummaryRead, MetricsTimeseriesRead
from app.services import trace_service
from app.services.trace_service import Granularity

router = APIRouter(
    prefix="/metrics", tags=["metrics"], dependencies=[Depends(require_role(UserRole.VIEWER))]
)

_DEFAULT_WINDOW_DAYS = 7


def _resolve_range(
    date_from: datetime | None, date_to: datetime | None
) -> tuple[datetime, datetime]:
    resolved_to = date_to or datetime.now(UTC)
    resolved_from = date_from or (resolved_to - timedelta(days=_DEFAULT_WINDOW_DAYS))
    if resolved_from > resolved_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="date_from must be before date_to"
        )
    return resolved_from, resolved_to


@router.get("/summary", response_model=MetricsSummaryRead)
async def get_summary_metrics(
    date_from: datetime | None = Query(
        default=None, description="Defaults to 7 days before date_to"
    ),
    date_to: datetime | None = Query(default=None, description="Defaults to now"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> MetricsSummaryRead:
    resolved_from, resolved_to = _resolve_range(date_from, date_to)
    metrics = await trace_service.get_summary_metrics(
        db, tenant_id=tenant_id, date_from=resolved_from, date_to=resolved_to
    )
    return MetricsSummaryRead.model_validate(metrics)


@router.get("/timeseries", response_model=MetricsTimeseriesRead)
async def get_timeseries_metrics(
    date_from: datetime | None = Query(
        default=None, description="Defaults to 7 days before date_to"
    ),
    date_to: datetime | None = Query(default=None, description="Defaults to now"),
    granularity: Granularity = Query(default="day"),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> MetricsTimeseriesRead:
    resolved_from, resolved_to = _resolve_range(date_from, date_to)
    metrics = await trace_service.get_timeseries_metrics(
        db,
        tenant_id=tenant_id,
        date_from=resolved_from,
        date_to=resolved_to,
        granularity=granularity,
    )
    return MetricsTimeseriesRead.model_validate(metrics)

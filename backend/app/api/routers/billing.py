import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id, require_role
from app.core.database import get_db
from app.core.exceptions import InvoiceNotFoundError
from app.models.user import UserRole
from app.schemas.invoice import CurrentUsageRead, InvoiceRead
from app.schemas.plan import PlanRead
from app.services import billing_service

router = APIRouter(
    prefix="/billing", tags=["billing"], dependencies=[Depends(require_role(UserRole.VIEWER))]
)


@router.get("/current-usage", response_model=CurrentUsageRead)
async def get_current_usage(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> CurrentUsageRead:
    usage = await billing_service.get_current_usage(db, tenant_id=tenant_id)
    return CurrentUsageRead(
        plan=PlanRead.model_validate(usage.plan),
        period_year=usage.period_year,
        period_month=usage.period_month,
        messages_used=usage.messages_used,
        included_messages=usage.included_messages,
        overage_messages=usage.overage_messages,
        overage_cost_usd=usage.overage_cost_usd,
        ai_cost_usd=usage.ai_cost_usd,
        included_ai_cost_usd=usage.included_ai_cost_usd,
        overage_enabled=usage.overage_enabled,
    )


@router.get("/invoices", response_model=list[InvoiceRead])
async def list_invoices(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> list[InvoiceRead]:
    invoices = await billing_service.list_invoices(db, tenant_id=tenant_id)
    return [InvoiceRead.model_validate(i) for i in invoices]


@router.get("/invoices/{invoice_id}", response_model=InvoiceRead)
async def get_invoice(
    invoice_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> InvoiceRead:
    try:
        invoice = await billing_service.get_invoice(db, tenant_id=tenant_id, invoice_id=invoice_id)
    except InvoiceNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found"
        ) from exc
    return InvoiceRead.model_validate(invoice)

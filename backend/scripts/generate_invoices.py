"""Monthly invoice generation batch — not a real cron job (out of scope), but
the script a real cron/scheduler would call on the 1st of each month, e.g.:

    0 3 1 * *  cd /path/to/backend && python -m scripts.generate_invoices

Generates the PREVIOUS calendar month's invoice for every tenant. Talks to
the database directly (not through the HTTP API, unlike eval/runner.py) since
it needs to iterate every tenant regardless of who's logged in — there's no
single JWT/API key that could do that.

Idempotent: relies on billing_service.generate_invoice's existing-invoice
short-circuit, so re-running this for a period that's already billed is safe
and just reports the invoices as already existing.

Usage:
    python -m scripts.generate_invoices                # previous calendar month
    python -m scripts.generate_invoices --year 2026 --month 7   # explicit period
"""

import argparse
import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.tenant import Tenant
from app.services import billing_service


def _previous_month(now: datetime) -> tuple[int, int]:
    if now.month == 1:
        return now.year - 1, 12
    return now.year, now.month - 1


async def generate_invoices_for_period(*, year: int, month: int) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Tenant.id, Tenant.name).order_by(Tenant.name))
        tenants = result.all()

        print(f"Generating invoices for {year}-{month:02d} — {len(tenants)} tenant(s)")
        for tenant_id, tenant_name in tenants:
            existing = await billing_service.get_existing_invoice(
                db, tenant_id=tenant_id, year=year, month=month
            )
            invoice = await billing_service.generate_invoice(
                db, tenant_id=tenant_id, year=year, month=month
            )
            status_label = "already existed" if existing is not None else "generated"
            print(
                f"  [{status_label}] {tenant_name}: "
                f"plan={invoice.plan_name_snapshot} "
                f"messages={invoice.total_messages} (overage={invoice.overage_messages}) "
                f"total=${invoice.total_cost_usd}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate monthly invoices for all tenants (Agent Ops billing)."
    )
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--month", type=int, default=None)
    args = parser.parse_args()

    if args.year is not None and args.month is not None:
        year, month = args.year, args.month
    else:
        year, month = _previous_month(datetime.now(UTC))

    asyncio.run(generate_invoices_for_period(year=year, month=month))


if __name__ == "__main__":
    main()

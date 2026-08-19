import uuid

from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id, require_role
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.user import User, UserRole
from app.schemas.eval import EvalCaseResultRead, EvalRunResponse, EvalSummary, RoutingProbeEntry

router = APIRouter(prefix="/eval", tags=["eval"])


@router.post("/run", response_model=EvalRunResponse)
async def run_eval(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> EvalRunResponse:
    """Run a scoped evaluation against THIS tenant's own configured agents and policies.

    Admin-only — spends real tenant budget and hits Anthropic directly, so
    it's gated the same way as every other real-money action (Phase 8's
    require_role, replacing the Phase 6 ad-hoc role check this endpoint used
    to do inline).

    This does **not** run the full golden dataset from `eval/data/`: the
    routing_keyword/routing_llm/routing_none categories assert a specific
    *logical* agent name (billing/shipping/support) that only means something
    against the canonical fixture environment `eval/environment.py` sets up
    for `python -m eval.runner` — it's meaningless against an arbitrary
    tenant's real agent naming. What runs here is every INPUT-stage guardrail
    case (blocklist/PII/max_length — evaluated before routing, so they never
    depend on which agent, if any, gets assigned) plus the edge cases, against
    whatever guardrail_policies this tenant has actually configured, plus a
    small informational routing probe (no pass/fail, just "here's what your
    routing does with a few generic messages"). See eval/runner.py's
    TENANT_SAFE_CATEGORIES and eval/README.md for the full reasoning.

    Runs real messages through this tenant's real pipeline — real Anthropic
    calls, real cost against this tenant's monthly budget, subject to this
    tenant's own rate limit (a too-tight limit will show up as errors in the
    report, which is itself useful signal — this endpoint never modifies the
    tenant's configured limits to work around that).
    """
    from app.main import app as fastapi_app  # deferred: app.main imports this router at load time
    from eval.runner import TENANT_SAFE_CATEGORIES, run_tenant_eval

    token = create_access_token(user_id=current_user.id, tenant_id=tenant_id)
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://eval-internal") as client:
        outcome = await run_tenant_eval(client=client, headers=headers, tenant_id=tenant_id, db=db)

    report_dict = outcome.report.to_dict(total_cost_usd=outcome.total_cost_usd)
    return EvalRunResponse(
        run_id=report_dict["run_id"],
        started_at=outcome.report.started_at,
        finished_at=outcome.report.finished_at,
        tenant_id=tenant_id,
        scope=f"tenant-scoped subset: {', '.join(sorted(TENANT_SAFE_CATEGORIES))} + routing probe",
        summary=EvalSummary(**report_dict["summary"]),
        results=[EvalCaseResultRead(**r) for r in report_dict["results"]],
        routing_probe=[RoutingProbeEntry(**p) for p in outcome.routing_probe],
    )

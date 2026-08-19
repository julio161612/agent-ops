import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_tenant_id, require_role
from app.core.database import get_db
from app.core.exceptions import (
    AgentNotFoundError,
    InvalidRoutingRuleConditionError,
    RoutingRuleNotFoundError,
)
from app.models.user import UserRole
from app.schemas.routing_rule import (
    RoutingRuleCreate,
    RoutingRuleMatchPreview,
    RoutingRuleRead,
    RoutingRuleUpdate,
    RoutingValidateRequest,
    RoutingValidateResponse,
)
from app.services import routing_rule_service
from app.services.routing_service import RoutingService

router = APIRouter(prefix="/routing-rules", tags=["routing-rules"])


@router.post(
    "/validate",
    response_model=RoutingValidateResponse,
    dependencies=[Depends(require_role(UserRole.VIEWER))],
)
async def validate_routing(
    payload: RoutingValidateRequest,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> RoutingValidateResponse:
    """Debug a routing configuration against an example message — no real
    routing decision, no agent execution, no cost. Only checks rule-based
    (level 1) matching for real; if nothing matches, reports that a real
    message would fall through to the LLM router without actually calling it
    (that would cost money and isn't deterministic enough to "validate"
    against).
    """
    routing_service = RoutingService(db)
    matches = await routing_service.preview_rule_matches(
        tenant_id=tenant_id, content=payload.content
    )

    matched_rules = [
        RoutingRuleMatchPreview(
            rule_id=rule.id,
            rule_type=rule.rule_type,
            priority=rule.priority,
            agent_id=agent.id,
            agent_name=agent.name,
            would_win=(index == 0),
        )
        for index, (rule, agent) in enumerate(matches)
    ]

    winner = matches[0][1] if matches else None
    return RoutingValidateResponse(
        content=payload.content,
        matched_rules=matched_rules,
        resulting_agent_id=winner.id if winner else None,
        resulting_agent_name=winner.name if winner else None,
        would_use_llm_router=winner is None,
    )


@router.post(
    "",
    response_model=RoutingRuleRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.OPERATOR))],
)
async def create_routing_rule(
    payload: RoutingRuleCreate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> RoutingRuleRead:
    try:
        rule = await routing_rule_service.create_routing_rule(
            db, tenant_id=tenant_id, payload=payload
        )
    except AgentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        ) from exc
    return RoutingRuleRead.model_validate(rule)


@router.get(
    "", response_model=list[RoutingRuleRead], dependencies=[Depends(require_role(UserRole.VIEWER))]
)
async def list_routing_rules(
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> list[RoutingRuleRead]:
    rules = await routing_rule_service.list_routing_rules(db, tenant_id=tenant_id)
    return [RoutingRuleRead.model_validate(r) for r in rules]


@router.get(
    "/{rule_id}",
    response_model=RoutingRuleRead,
    dependencies=[Depends(require_role(UserRole.VIEWER))],
)
async def get_routing_rule(
    rule_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> RoutingRuleRead:
    try:
        rule = await routing_rule_service.get_routing_rule(db, tenant_id=tenant_id, rule_id=rule_id)
    except RoutingRuleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Routing rule not found"
        ) from exc
    return RoutingRuleRead.model_validate(rule)


@router.patch(
    "/{rule_id}",
    response_model=RoutingRuleRead,
    dependencies=[Depends(require_role(UserRole.OPERATOR))],
)
async def update_routing_rule(
    rule_id: uuid.UUID,
    payload: RoutingRuleUpdate,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> RoutingRuleRead:
    try:
        rule = await routing_rule_service.update_routing_rule(
            db, tenant_id=tenant_id, rule_id=rule_id, payload=payload
        )
    except RoutingRuleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Routing rule not found"
        ) from exc
    except AgentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        ) from exc
    except InvalidRoutingRuleConditionError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return RoutingRuleRead.model_validate(rule)


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.OPERATOR))],
)
async def delete_routing_rule(
    rule_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await routing_rule_service.delete_routing_rule(db, tenant_id=tenant_id, rule_id=rule_id)
    except RoutingRuleNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Routing rule not found"
        ) from exc

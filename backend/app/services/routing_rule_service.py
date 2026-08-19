import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidRoutingRuleConditionError, RoutingRuleNotFoundError
from app.models.routing_rule import RoutingRule
from app.schemas.routing_rule import RoutingRuleCreate, RoutingRuleUpdate, validate_condition
from app.services import agent_service


async def create_routing_rule(
    db: AsyncSession, *, tenant_id: uuid.UUID, payload: RoutingRuleCreate
) -> RoutingRule:
    await agent_service.get_agent(
        db, tenant_id=tenant_id, agent_id=payload.agent_id
    )  # validates FK
    rule = RoutingRule(
        tenant_id=tenant_id,
        agent_id=payload.agent_id,
        rule_type=payload.rule_type,
        condition=payload.condition,
        priority=payload.priority,
        is_active=payload.is_active,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def list_routing_rules(db: AsyncSession, *, tenant_id: uuid.UUID) -> list[RoutingRule]:
    result = await db.execute(
        select(RoutingRule)
        .where(RoutingRule.tenant_id == tenant_id)
        .order_by(RoutingRule.priority.desc(), RoutingRule.created_at)
    )
    return list(result.scalars().all())


async def get_routing_rule(
    db: AsyncSession, *, tenant_id: uuid.UUID, rule_id: uuid.UUID
) -> RoutingRule:
    result = await db.execute(
        select(RoutingRule).where(RoutingRule.id == rule_id, RoutingRule.tenant_id == tenant_id)
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise RoutingRuleNotFoundError(str(rule_id))
    return rule


async def update_routing_rule(
    db: AsyncSession, *, tenant_id: uuid.UUID, rule_id: uuid.UUID, payload: RoutingRuleUpdate
) -> RoutingRule:
    rule = await get_routing_rule(db, tenant_id=tenant_id, rule_id=rule_id)

    updates = payload.model_dump(exclude_unset=True)
    if "agent_id" in updates:
        await agent_service.get_agent(db, tenant_id=tenant_id, agent_id=updates["agent_id"])
    for field, value in updates.items():
        setattr(rule, field, value)

    try:
        validate_condition(rule.rule_type, rule.condition)
    except ValueError as exc:
        raise InvalidRoutingRuleConditionError(str(exc)) from exc

    await db.commit()
    await db.refresh(rule)
    return rule


async def delete_routing_rule(
    db: AsyncSession, *, tenant_id: uuid.UUID, rule_id: uuid.UUID
) -> None:
    rule = await get_routing_rule(db, tenant_id=tenant_id, rule_id=rule_id)
    await db.delete(rule)
    await db.commit()

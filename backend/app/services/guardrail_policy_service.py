import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import GuardrailPolicyNotFoundError, InvalidGuardrailConfigError
from app.models.guardrail_policy import GuardrailPolicy
from app.schemas.guardrail_policy import (
    GuardrailPolicyCreate,
    GuardrailPolicyUpdate,
    validate_config,
)
from app.services import agent_service


async def create_policy(
    db: AsyncSession, *, tenant_id: uuid.UUID, payload: GuardrailPolicyCreate
) -> GuardrailPolicy:
    if payload.agent_id is not None:
        await agent_service.get_agent(db, tenant_id=tenant_id, agent_id=payload.agent_id)
    policy = GuardrailPolicy(
        tenant_id=tenant_id,
        agent_id=payload.agent_id,
        guardrail_type=payload.guardrail_type,
        rule_type=payload.rule_type,
        config=payload.config,
        action_on_violation=payload.action_on_violation,
        is_active=payload.is_active,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)
    return policy


async def list_policies(db: AsyncSession, *, tenant_id: uuid.UUID) -> list[GuardrailPolicy]:
    result = await db.execute(
        select(GuardrailPolicy)
        .where(GuardrailPolicy.tenant_id == tenant_id)
        .order_by(GuardrailPolicy.created_at)
    )
    return list(result.scalars().all())


async def get_policy(
    db: AsyncSession, *, tenant_id: uuid.UUID, policy_id: uuid.UUID
) -> GuardrailPolicy:
    result = await db.execute(
        select(GuardrailPolicy).where(
            GuardrailPolicy.id == policy_id, GuardrailPolicy.tenant_id == tenant_id
        )
    )
    policy = result.scalar_one_or_none()
    if policy is None:
        raise GuardrailPolicyNotFoundError(str(policy_id))
    return policy


async def update_policy(
    db: AsyncSession, *, tenant_id: uuid.UUID, policy_id: uuid.UUID, payload: GuardrailPolicyUpdate
) -> GuardrailPolicy:
    policy = await get_policy(db, tenant_id=tenant_id, policy_id=policy_id)

    updates = payload.model_dump(exclude_unset=True)
    if updates.get("agent_id") is not None:
        await agent_service.get_agent(db, tenant_id=tenant_id, agent_id=updates["agent_id"])
    for field, value in updates.items():
        setattr(policy, field, value)

    try:
        validate_config(policy.rule_type, policy.config)
    except ValueError as exc:
        raise InvalidGuardrailConfigError(str(exc)) from exc

    await db.commit()
    await db.refresh(policy)
    return policy


async def delete_policy(db: AsyncSession, *, tenant_id: uuid.UUID, policy_id: uuid.UUID) -> None:
    policy = await get_policy(db, tenant_id=tenant_id, policy_id=policy_id)
    await db.delete(policy)
    await db.commit()

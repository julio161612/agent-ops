import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AgentNotFoundError, PlanAgentLimitExceededError
from app.models.agent import Agent
from app.schemas.agent import AgentCreate, AgentUpdate
from app.services import subscription_service


async def _count_active_agents(db: AsyncSession, *, tenant_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Agent)
        .where(Agent.tenant_id == tenant_id, Agent.is_active.is_(True), Agent.deleted_at.is_(None))
    )
    return result.scalar_one()


async def _check_active_agent_limit(db: AsyncSession, *, tenant_id: uuid.UUID) -> None:
    """Raises PlanAgentLimitExceededError if activating one more agent would
    exceed the tenant's plan (Enterprise's included_active_agents=None skips
    this entirely — see Plan model docstring)."""
    effective = await subscription_service.get_effective_limits(db, tenant_id=tenant_id)
    limit = effective.plan.included_active_agents
    if limit is None:
        return
    current_count = await _count_active_agents(db, tenant_id=tenant_id)
    if current_count >= limit:
        raise PlanAgentLimitExceededError(
            f"The '{effective.plan.name}' plan includes {limit} active agent(s); "
            f"this tenant already has {current_count}. Upgrade your plan to add more."
        )


async def create_agent(db: AsyncSession, *, tenant_id: uuid.UUID, payload: AgentCreate) -> Agent:
    if payload.is_active:
        await _check_active_agent_limit(db, tenant_id=tenant_id)

    agent = Agent(
        tenant_id=tenant_id,
        name=payload.name,
        description=payload.description,
        agent_type=payload.agent_type,
        system_prompt=payload.system_prompt,
        model=payload.model or settings.ANTHROPIC_DEFAULT_MODEL,
        parameters=payload.parameters.model_dump(),
        is_active=payload.is_active,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


async def list_agents(db: AsyncSession, *, tenant_id: uuid.UUID) -> list[Agent]:
    result = await db.execute(
        select(Agent)
        .where(Agent.tenant_id == tenant_id, Agent.deleted_at.is_(None))
        .order_by(Agent.created_at)
    )
    return list(result.scalars().all())


async def get_agent(db: AsyncSession, *, tenant_id: uuid.UUID, agent_id: uuid.UUID) -> Agent:
    """Fetch an agent, scoped to tenant_id. Raises AgentNotFoundError otherwise.

    Deliberately returns the same "not found" error whether the agent belongs to
    another tenant or doesn't exist at all — never leaking which case it is.
    """
    result = await db.execute(
        select(Agent).where(
            Agent.id == agent_id, Agent.tenant_id == tenant_id, Agent.deleted_at.is_(None)
        )
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        raise AgentNotFoundError(str(agent_id))
    return agent


async def update_agent(
    db: AsyncSession, *, tenant_id: uuid.UUID, agent_id: uuid.UUID, payload: AgentUpdate
) -> Agent:
    agent = await get_agent(db, tenant_id=tenant_id, agent_id=agent_id)

    updates = payload.model_dump(exclude_unset=True)
    if updates.get("is_active") is True and not agent.is_active:
        # Closes the obvious loophole around create_agent's own check: create
        # inactive agents past the limit, then flip them active one at a time.
        await _check_active_agent_limit(db, tenant_id=tenant_id)
    if "parameters" in updates and updates["parameters"] is not None:
        updates["parameters"] = payload.parameters.model_dump()
    for field, value in updates.items():
        setattr(agent, field, value)

    await db.commit()
    await db.refresh(agent)
    return agent


async def soft_delete_agent(db: AsyncSession, *, tenant_id: uuid.UUID, agent_id: uuid.UUID) -> None:
    agent = await get_agent(db, tenant_id=tenant_id, agent_id=agent_id)
    agent.deleted_at = datetime.now(UTC)
    agent.is_active = False
    await db.commit()

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.models.guardrail_policy import GuardrailPolicy
from app.models.routing_rule import RoutingRule
from app.models.tenant_limits import TenantLimits
from app.models.user import User
from app.services import tenant_limits_service


@dataclass
class OnboardingItem:
    key: str
    label: str
    done: bool
    detail: str


@dataclass
class OnboardingStatus:
    items: list[OnboardingItem] = field(default_factory=list)

    @property
    def completed_count(self) -> int:
        return sum(1 for item in self.items if item.done)

    @property
    def total_count(self) -> int:
        return len(self.items)

    @property
    def is_complete(self) -> bool:
        return self.completed_count == self.total_count


async def _count(db: AsyncSession, *, model, **filters) -> int:
    stmt = select(func.count()).select_from(model)
    for column, value in filters.items():
        stmt = stmt.where(getattr(model, column) == value)
    result = await db.execute(stmt)
    return result.scalar_one()


async def get_onboarding_status(db: AsyncSession, *, tenant_id: uuid.UUID) -> OnboardingStatus:
    active_agent_count = await _count(db, model=Agent, tenant_id=tenant_id, is_active=True)
    routing_rule_count = await _count(db, model=RoutingRule, tenant_id=tenant_id, is_active=True)
    guardrail_policy_count = await _count(
        db, model=GuardrailPolicy, tenant_id=tenant_id, is_active=True
    )
    active_user_count = await _count(db, model=User, tenant_id=tenant_id, is_active=True)
    limits: TenantLimits = await tenant_limits_service.get_limits(db, tenant_id=tenant_id)

    has_active_agent = active_agent_count > 0
    has_routing_rules = routing_rule_count > 0

    if has_routing_rules:
        routing_detail = f"{routing_rule_count} regla(s) de routing activa(s)."
    elif has_active_agent:
        routing_detail = (
            "Sin reglas explícitas: los mensajes se enrutarán con el router por LLM "
            "(funciona, pero es menos predecible que una regla)."
        )
    else:
        routing_detail = "Sin agentes activos todavía: el routing no tiene a quién asignar."

    if limits.monthly_cost_limit_usd is not None:
        limits_detail = f"Límite mensual de coste configurado: ${limits.monthly_cost_limit_usd}."
    else:
        limits_detail = "Sin límite mensual de coste configurado (gasto ilimitado)."

    return OnboardingStatus(
        items=[
            OnboardingItem(
                key="active_agent",
                label="Crear al menos un agente activo",
                done=has_active_agent,
                detail=f"{active_agent_count} agente(s) activo(s).",
            ),
            OnboardingItem(
                key="routing",
                label="Configurar cómo se asignan las conversaciones a un agente",
                done=has_routing_rules or has_active_agent,
                detail=routing_detail,
            ),
            OnboardingItem(
                key="guardrails",
                label="Configurar al menos una política de guardrail",
                done=guardrail_policy_count > 0,
                detail=f"{guardrail_policy_count} política(s) de guardrail activa(s).",
            ),
            OnboardingItem(
                key="tenant_limits",
                label="Revisar los límites de coste y de mensajes por minuto",
                done=limits.monthly_cost_limit_usd is not None,
                detail=(
                    f"{limits_detail} Límite de mensajes por minuto: "
                    f"{limits.messages_per_minute_limit}."
                ),
            ),
            OnboardingItem(
                key="team",
                label="Invitar a más miembros del equipo",
                done=active_user_count > 1,
                detail=f"{active_user_count} usuario(s) activo(s) en el tenant.",
            ),
        ]
    )

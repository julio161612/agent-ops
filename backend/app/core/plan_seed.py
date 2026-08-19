"""Seed data for the global Plan catalog (Phase 10).

Single source of truth shared by the Alembic migration (which inserts these
rows once) and anything at runtime that needs the same numbers (tests,
scripts) without re-deriving them. Pricing is a deliberate, defensible
ladder for a small-business AI-agent-orchestration SaaS in the current
market (comparable tools — Intercom Fin, Chatbase, Ada — run roughly
free/$0 -> ~$30-40 -> ~$100-150 -> custom/high-hundreds for the equivalent
tiers), not arbitrary numbers.
"""

from decimal import Decimal
from typing import Any

PLAN_SEED_DATA: list[dict[str, Any]] = [
    {
        "name": "Free",
        "slug": "free",
        "monthly_price_usd": Decimal("0.00"),
        "included_messages_per_month": 100,
        "included_active_agents": 1,
        "included_users": 1,
        "included_ai_cost_usd": Decimal("5.00"),
        "max_messages_per_minute": 10,
        "overage_price_per_1000_messages_usd": None,
        "is_active": True,
    },
    {
        "name": "Starter",
        "slug": "starter",
        "monthly_price_usd": Decimal("29.00"),
        "included_messages_per_month": 1000,
        "included_active_agents": 3,
        "included_users": 3,
        "included_ai_cost_usd": Decimal("15.00"),
        "max_messages_per_minute": 30,
        "overage_price_per_1000_messages_usd": Decimal("8.00"),
        "is_active": True,
    },
    {
        "name": "Growth",
        "slug": "growth",
        "monthly_price_usd": Decimal("99.00"),
        "included_messages_per_month": 5000,
        "included_active_agents": 10,
        "included_users": 10,
        "included_ai_cost_usd": Decimal("75.00"),
        "max_messages_per_minute": 60,
        "overage_price_per_1000_messages_usd": Decimal("6.00"),
        "is_active": True,
    },
    {
        "name": "Enterprise",
        "slug": "enterprise",
        "monthly_price_usd": Decimal("499.00"),
        "included_messages_per_month": None,
        "included_active_agents": None,
        "included_users": None,
        "included_ai_cost_usd": None,
        "max_messages_per_minute": 300,
        "overage_price_per_1000_messages_usd": None,
        "is_active": True,
    },
]

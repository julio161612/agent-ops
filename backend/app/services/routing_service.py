import uuid
from dataclasses import dataclass

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.anthropic_client import get_anthropic_client
from app.core.config import settings
from app.models.agent import Agent
from app.models.routing_decision import RoutingMethod
from app.models.routing_rule import RoutingRule, RoutingRuleType
from app.services import agent_service

_ROUTING_TOOL_NAME = "select_agent"
_ROUTING_TOOL = {
    "name": _ROUTING_TOOL_NAME,
    "description": (
        "Selects which of the available agents should handle the user's message, "
        "or declines if none of them are actually a good fit."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "agent_id": {
                "type": "string",
                "description": (
                    "The id of the chosen agent, copied exactly from the list below. "
                    "Empty string if none of the agents are a good fit."
                ),
            },
            "confidence": {
                "type": "number",
                "description": "Confidence in this choice, from 0.0 (no idea) to 1.0 (certain).",
            },
            "reasoning": {
                "type": "string",
                "description": "One brief sentence explaining the choice.",
            },
        },
        "required": ["agent_id", "confidence", "reasoning"],
    },
}


@dataclass
class RoutingResult:
    """The outcome of RoutingService.route() — always produced, never raised."""

    method: RoutingMethod
    agent_id: uuid.UUID | None
    matched_rule_id: uuid.UUID | None
    confidence: float | None
    reasoning: str | None


@dataclass
class _LLMRoutingOutcome:
    agent_id: uuid.UUID | None
    confidence: float | None
    reasoning: str | None


class RoutingService:
    """Decides which Agent should handle an incoming message, in two tiers.

    1. Rule-based (cheap, no LLM call): active RoutingRules for the tenant,
       evaluated by priority, first match wins.
    2. LLM-based fallback: asks Claude to pick from the tenant's active agents,
       via a forced tool call so the output is always schema-valid JSON — no
       free-text parsing. Below `confidence_threshold`, or on any failure to
       get a usable answer, the result is "no agent" rather than a guess.

    Never raises for "no agent found" or for LLM/parsing failures — those are
    valid, expected RoutingResult outcomes (agent_id=None), not errors. Only
    truly unexpected conditions would propagate as exceptions.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        anthropic_client: anthropic.AsyncAnthropic | None = None,
        confidence_threshold: float | None = None,
    ) -> None:
        self.db = db
        self._client = anthropic_client or get_anthropic_client()
        self._confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else settings.ROUTING_CONFIDENCE_THRESHOLD
        )

    async def route(self, *, tenant_id: uuid.UUID, content: str) -> RoutingResult:
        matches = await self.preview_rule_matches(tenant_id=tenant_id, content=content)
        if matches:
            rule, agent = matches[0]
            return RoutingResult(
                method=RoutingMethod.RULE,
                agent_id=agent.id,
                matched_rule_id=rule.id,
                confidence=None,
                reasoning=None,
            )

        candidates = [
            a for a in await agent_service.list_agents(self.db, tenant_id=tenant_id) if a.is_active
        ]
        if not candidates:
            return RoutingResult(
                method=RoutingMethod.LLM,
                agent_id=None,
                matched_rule_id=None,
                confidence=None,
                reasoning="No active agents are configured for this tenant",
            )

        outcome = await self._llm_route(content=content, candidates=candidates)
        if (
            outcome.agent_id is None
            or outcome.confidence is None
            or outcome.confidence < self._confidence_threshold
        ):
            return RoutingResult(
                method=RoutingMethod.LLM,
                agent_id=None,
                matched_rule_id=None,
                confidence=outcome.confidence,
                reasoning=outcome.reasoning,
            )
        return RoutingResult(
            method=RoutingMethod.LLM,
            agent_id=outcome.agent_id,
            matched_rule_id=None,
            confidence=outcome.confidence,
            reasoning=outcome.reasoning,
        )

    async def preview_rule_matches(
        self, *, tenant_id: uuid.UUID, content: str
    ) -> list[tuple[RoutingRule, Agent]]:
        """Every active rule whose condition matches ``content``, in the same
        priority order route() picks from — route() only ever acts on the
        first one, but returning all of them is what makes
        POST /routing-rules/validate useful for debugging "why did rule A
        win over rule B" instead of just "what won".
        """
        result = await self.db.execute(
            select(RoutingRule, Agent)
            .join(Agent, RoutingRule.agent_id == Agent.id)
            .where(
                RoutingRule.tenant_id == tenant_id,
                RoutingRule.is_active.is_(True),
                Agent.deleted_at.is_(None),
                Agent.is_active.is_(True),
            )
            .order_by(RoutingRule.priority.desc(), RoutingRule.created_at)
        )
        content_lower = content.lower()
        matches: list[tuple[RoutingRule, Agent]] = []
        for rule, agent in result.all():
            if rule.rule_type == RoutingRuleType.KEYWORD:
                keywords = rule.condition.get("keywords", [])
                if any(str(kw).lower() in content_lower for kw in keywords):
                    matches.append((rule, agent))
            elif rule.rule_type == RoutingRuleType.CATEGORY:
                if agent.agent_type == rule.condition.get("agent_type"):
                    matches.append((rule, agent))
        return matches

    async def _llm_route(self, *, content: str, candidates: list[Agent]) -> _LLMRoutingOutcome:
        prompt = self._build_prompt(content=content, candidates=candidates)
        try:
            response = await self._client.messages.create(
                model=settings.ANTHROPIC_DEFAULT_MODEL,
                max_tokens=300,
                tools=[_ROUTING_TOOL],
                tool_choice={"type": "tool", "name": _ROUTING_TOOL_NAME},
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.AnthropicError as exc:
            return _LLMRoutingOutcome(
                agent_id=None, confidence=None, reasoning=f"Routing LLM call failed: {exc}"
            )

        tool_use = next(
            (
                block
                for block in response.content
                if getattr(block, "type", None) == "tool_use" and block.name == _ROUTING_TOOL_NAME
            ),
            None,
        )
        if tool_use is None:
            return _LLMRoutingOutcome(
                agent_id=None,
                confidence=None,
                reasoning="Router did not return a structured decision",
            )

        raw = tool_use.input if isinstance(tool_use.input, dict) else {}
        reasoning = str(raw.get("reasoning") or "").strip()[:2000] or None

        try:
            confidence = float(raw.get("confidence"))
        except (TypeError, ValueError):
            return _LLMRoutingOutcome(
                agent_id=None,
                confidence=None,
                reasoning=reasoning or "Router returned a non-numeric confidence value",
            )
        confidence = max(0.0, min(1.0, confidence))

        raw_agent_id = str(raw.get("agent_id") or "").strip()
        if not raw_agent_id:
            return _LLMRoutingOutcome(agent_id=None, confidence=confidence, reasoning=reasoning)

        try:
            agent_id = uuid.UUID(raw_agent_id)
        except ValueError:
            return _LLMRoutingOutcome(
                agent_id=None,
                confidence=confidence,
                reasoning=reasoning or "Router returned a malformed agent_id",
            )

        if agent_id not in {a.id for a in candidates}:
            return _LLMRoutingOutcome(
                agent_id=None,
                confidence=confidence,
                reasoning=reasoning or "Router selected an agent outside the candidate list",
            )

        return _LLMRoutingOutcome(agent_id=agent_id, confidence=confidence, reasoning=reasoning)

    @staticmethod
    def _build_prompt(*, content: str, candidates: list[Agent]) -> str:
        agents_listing = "\n".join(
            f"- id: {a.id}\n  name: {a.name}\n  agent_type: {a.agent_type or 'n/a'}\n"
            f"  description: {a.description or 'n/a'}"
            for a in candidates
        )
        return (
            "You are the routing layer of a multi-agent customer support platform. "
            "Given the list of available agents and the user's message, choose the "
            "single best agent to handle it. If none of the agents are a good fit, "
            "return an empty agent_id and a low confidence — do not guess.\n\n"
            f"Available agents:\n{agents_listing}\n\n"
            f'User message: "{content}"'
        )

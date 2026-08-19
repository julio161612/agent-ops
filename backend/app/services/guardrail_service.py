import re
import uuid
from dataclasses import dataclass
from typing import Any

import anthropic
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.anthropic_client import get_anthropic_client
from app.core.config import settings
from app.models.guardrail_policy import (
    GuardrailAction,
    GuardrailPolicy,
    GuardrailRuleType,
    GuardrailType,
)
from app.models.guardrail_violation import GuardrailViolation
from app.services import cost_service

# Deliberately "basic" regex heuristics, as the spec asks for — not a
# production-grade PII scanner. False positives (e.g. a random 9-digit number
# flagged as "phone") are an accepted tradeoff for staying simple and free.
_PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "credit_card": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
    "phone": re.compile(r"(?:\+?\d{1,3}[\s-]?)?\b\d{9}\b"),
    "spanish_dni": re.compile(r"\b\d{8}[A-Za-z]\b"),
}

_GUARDRAIL_TOOL_NAME = "evaluate_policy"
_GUARDRAIL_TOOL = {
    "name": _GUARDRAIL_TOOL_NAME,
    "description": "Evaluates whether the given text violates the stated policy.",
    "input_schema": {
        "type": "object",
        "properties": {
            "violates": {"type": "boolean", "description": "True if the text violates the policy."},
            "reason": {
                "type": "string",
                "description": "One brief sentence explaining the verdict.",
            },
        },
        "required": ["violates", "reason"],
    },
}


@dataclass
class GuardrailCheckOutcome:
    blocked: bool
    violations: list[GuardrailViolation]


@dataclass
class GuardrailDryRunViolation:
    """Same shape as GuardrailViolation's meaningful fields, but never written
    to the database — see GuardrailService.check_dry_run."""

    policy_id: uuid.UUID
    guardrail_type: GuardrailType
    violation_type: GuardrailRuleType
    detail: str
    action_taken: GuardrailAction


@dataclass
class _Evaluation:
    detail: str
    action: GuardrailAction


@dataclass
class _LLMCheckOutcome:
    evaluated: bool
    violates: bool
    reason: str | None


class GuardrailService:
    """Runs every active INPUT or OUTPUT policy of a tenant (and optionally one
    agent) against a piece of text, and records what it finds.

    Never raises for a violation — blocking is communicated back via
    ``GuardrailCheckOutcome.blocked``, so the caller decides what to do
    (AgentExecutionService stops the pipeline and substitutes a generic reply).
    """

    def __init__(self, db: AsyncSession, anthropic_client: anthropic.AsyncAnthropic | None = None):
        self.db = db
        self._client = anthropic_client or get_anthropic_client()

    async def check(
        self,
        *,
        tenant_id: uuid.UUID,
        agent_id: uuid.UUID | None,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID | None,
        content: str,
        guardrail_type: GuardrailType,
    ) -> GuardrailCheckOutcome:
        policies = await self._active_policies(
            tenant_id=tenant_id, agent_id=agent_id, guardrail_type=guardrail_type
        )

        violations: list[GuardrailViolation] = []
        for policy in policies:
            evaluation = await self._evaluate_policy(policy, tenant_id=tenant_id, content=content)
            if evaluation is None:
                continue
            violation = GuardrailViolation(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                message_id=message_id,
                policy_id=policy.id,
                guardrail_type=guardrail_type,
                violation_type=policy.rule_type,
                detail=evaluation.detail,
                action_taken=evaluation.action,
            )
            self.db.add(violation)
            violations.append(violation)

        await self.db.flush()
        blocked = any(v.action_taken == GuardrailAction.BLOCK for v in violations)
        return GuardrailCheckOutcome(blocked=blocked, violations=violations)

    async def check_dry_run(
        self,
        *,
        tenant_id: uuid.UUID,
        agent_id: uuid.UUID | None,
        content: str,
        guardrail_type: GuardrailType,
    ) -> list[GuardrailDryRunViolation]:
        """Same evaluation as ``check()``, for Phase 8's agent test mode —
        deliberately never writes a GuardrailViolation row (or anything else)
        to the database, since a test call has no real conversation_id/
        message_id to attach one to. A custom_llm_check policy still spends
        real tokens and still gets billed via cost_service, same as ``check()``
        — only the violation *record* is skipped, not the real API call.
        """
        policies = await self._active_policies(
            tenant_id=tenant_id, agent_id=agent_id, guardrail_type=guardrail_type
        )
        results: list[GuardrailDryRunViolation] = []
        for policy in policies:
            evaluation = await self._evaluate_policy(policy, tenant_id=tenant_id, content=content)
            if evaluation is None:
                continue
            results.append(
                GuardrailDryRunViolation(
                    policy_id=policy.id,
                    guardrail_type=guardrail_type,
                    violation_type=policy.rule_type,
                    detail=evaluation.detail,
                    action_taken=evaluation.action,
                )
            )
        return results

    async def _active_policies(
        self, *, tenant_id: uuid.UUID, agent_id: uuid.UUID | None, guardrail_type: GuardrailType
    ) -> list[GuardrailPolicy]:
        result = await self.db.execute(
            select(GuardrailPolicy)
            .where(
                GuardrailPolicy.tenant_id == tenant_id,
                GuardrailPolicy.guardrail_type == guardrail_type,
                GuardrailPolicy.is_active.is_(True),
                or_(GuardrailPolicy.agent_id.is_(None), GuardrailPolicy.agent_id == agent_id),
            )
            .order_by(GuardrailPolicy.created_at)
        )
        return list(result.scalars().all())

    async def _evaluate_policy(
        self, policy: GuardrailPolicy, *, tenant_id: uuid.UUID, content: str
    ) -> _Evaluation | None:
        if policy.rule_type == GuardrailRuleType.BLOCKLIST_KEYWORDS:
            detail = self._check_blocklist(content, policy.config)
        elif policy.rule_type == GuardrailRuleType.PII_DETECTION:
            detail = self._check_pii(content, policy.config)
        elif policy.rule_type == GuardrailRuleType.MAX_LENGTH:
            detail = self._check_max_length(content, policy.config)
        elif policy.rule_type == GuardrailRuleType.CUSTOM_LLM_CHECK:
            return await self._evaluate_custom_llm_check(
                policy, tenant_id=tenant_id, content=content
            )
        else:  # pragma: no cover — exhaustive over GuardrailRuleType
            detail = None

        if detail is None:
            return None
        return _Evaluation(detail=detail, action=policy.action_on_violation)

    @staticmethod
    def _check_blocklist(content: str, config: dict[str, Any]) -> str | None:
        keywords = config.get("keywords", [])
        content_lower = content.lower()
        matched = [kw for kw in keywords if str(kw).lower() in content_lower]
        if not matched:
            return None
        return f"Blocked keyword(s) matched: {', '.join(matched)}"

    @staticmethod
    def _check_pii(content: str, config: dict[str, Any]) -> str | None:
        pattern_names = config.get("patterns") or list(_PII_PATTERNS)
        detected: list[str] = []
        for name in pattern_names:
            regex = _PII_PATTERNS.get(name)
            if regex is None:
                continue
            for match in regex.finditer(content):
                if name == "credit_card":
                    digits = re.sub(r"\D", "", match.group())
                    if not (13 <= len(digits) <= 19):
                        continue
                detected.append(name)
                break
        if not detected:
            return None
        # Never include the matched substring itself — only which pattern types fired.
        return f"Detected possible PII: {', '.join(detected)}"

    @staticmethod
    def _check_max_length(content: str, config: dict[str, Any]) -> str | None:
        max_characters = config.get("max_characters")
        if not isinstance(max_characters, int):
            return None
        if len(content) <= max_characters:
            return None
        return f"Message length {len(content)} exceeds max_characters={max_characters}"

    async def _evaluate_custom_llm_check(
        self, policy: GuardrailPolicy, *, tenant_id: uuid.UUID, content: str
    ) -> _Evaluation | None:
        instruction = policy.config.get("instruction")
        if not instruction:
            return None
        model = policy.config.get("model") or settings.GUARDRAIL_LLM_MODEL

        outcome = await self._call_llm_check(
            tenant_id=tenant_id, model=model, instruction=instruction, content=content
        )

        if not outcome.evaluated:
            # Fail OPEN, not closed: an outage in this secondary safety net shouldn't
            # block all traffic for the tenant. Still recorded (as a FLAG, never a
            # BLOCK, regardless of the policy's configured action) so it's visible
            # for a human to review rather than silently swallowed.
            return _Evaluation(
                detail=f"custom_llm_check inconclusive: {outcome.reason}",
                action=GuardrailAction.FLAG,
            )
        if not outcome.violates:
            return None
        return _Evaluation(
            detail=outcome.reason or "Custom policy violated", action=policy.action_on_violation
        )

    async def _call_llm_check(
        self, *, tenant_id: uuid.UUID, model: str, instruction: str, content: str
    ) -> _LLMCheckOutcome:
        prompt = (
            f"Policy: {instruction}\n\n"
            f'Text to evaluate: "{content}"\n\n'
            "Does the text violate the policy?"
        )
        try:
            response = await self._client.messages.create(
                model=model,
                max_tokens=200,
                tools=[_GUARDRAIL_TOOL],
                tool_choice={"type": "tool", "name": _GUARDRAIL_TOOL_NAME},
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.AnthropicError as exc:
            return _LLMCheckOutcome(evaluated=False, violates=False, reason=str(exc))

        await cost_service.record_usage(
            self.db,
            tenant_id=tenant_id,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        tool_use = next(
            (
                block
                for block in response.content
                if getattr(block, "type", None) == "tool_use" and block.name == _GUARDRAIL_TOOL_NAME
            ),
            None,
        )
        if tool_use is None:
            return _LLMCheckOutcome(
                evaluated=False, violates=False, reason="model did not return a structured decision"
            )

        raw = tool_use.input if isinstance(tool_use.input, dict) else {}
        reason = str(raw.get("reason") or "").strip()[:2000] or None
        return _LLMCheckOutcome(evaluated=True, violates=bool(raw.get("violates")), reason=reason)

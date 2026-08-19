import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from decimal import Decimal

import anthropic
from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.anthropic_client import get_anthropic_client
from app.core.database import get_db
from app.core.exceptions import (
    AgentRateLimitedError,
    AgentTimeoutError,
    AgentUpstreamError,
    TenantMessageQuotaExceededError,
    TenantRateLimitExceededError,
)
from app.core.redis import get_redis
from app.models.conversation import Conversation, ConversationStatus
from app.models.escalation_case import EscalationReason
from app.models.guardrail_policy import GuardrailType
from app.models.guardrail_violation import GuardrailViolation
from app.models.interaction_trace import InteractionTrace, TraceOutcome
from app.models.message import Message, MessageRole
from app.models.routing_decision import RoutingDecision
from app.models.tenant_limits import TenantLimits
from app.services import (
    agent_service,
    cost_service,
    escalation_service,
    subscription_service,
    trace_service,
)
from app.services.guardrail_service import GuardrailDryRunViolation, GuardrailService
from app.services.rate_limiter import RateLimiter
from app.services.routing_service import RoutingResult, RoutingService

# Roles that are valid turns in the Anthropic Messages API — SYSTEM is passed
# separately via the `system` parameter and never belongs in this list.
_ANTHROPIC_HISTORY_ROLES = {MessageRole.USER, MessageRole.ASSISTANT}

_INPUT_BLOCKED_TEXT = (
    "Lo sentimos, no podemos procesar tu mensaje porque incumple nuestras políticas de contenido."
)
_OUTPUT_BLOCKED_TEXT = (
    "Lo sentimos, no podemos mostrar la respuesta generada a tu mensaje. "
    "Un miembro de nuestro equipo revisará esta conversación en breve."
)

# The fixed set of pipeline stages InteractionTrace.stage_latencies_ms always
# reports, regardless of which ones actually ran for a given turn (a stage
# the pipeline short-circuited past — e.g. routing when an agent is already
# bound — is simply 0, not absent), so every trace has the same JSON shape
# for downstream aggregation/charting.
_PIPELINE_STAGES = (
    "rate_limit_check",
    "input_guardrails",
    "routing",
    "agent_execution",
    "output_guardrails",
)


@asynccontextmanager
async def _timed_stage(stage_latencies_ms: dict[str, int], stage: str) -> AsyncIterator[None]:
    started_at = time.monotonic()
    try:
        yield
    finally:
        stage_latencies_ms[stage] = int((time.monotonic() - started_at) * 1000)


@dataclass
class SendMessageResult:
    conversation: Conversation
    user_message: Message
    assistant_message: Message | None
    routing_decision: RoutingDecision | None
    guardrail_violations: list[GuardrailViolation] = field(default_factory=list)
    trace: InteractionTrace | None = None


@dataclass
class AgentTestResult:
    """The outcome of AgentExecutionService.test_agent — see that method's
    docstring for why nothing here is ever persisted as a Conversation,
    Message, GuardrailViolation, or InteractionTrace.
    """

    agent_id: uuid.UUID
    input_blocked: bool
    input_guardrail_violations: list[GuardrailDryRunViolation]
    reply: str | None
    output_blocked: bool
    output_guardrail_violations: list[GuardrailDryRunViolation]
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    latency_ms: int


class AgentExecutionService:
    """Runs a tenant's Agent against a Conversation, for real, via the Anthropic API.

    Full pipeline for every message: tenant budget gate (rate limit + monthly
    cost cap) -> INPUT guardrails -> routing (only if the conversation has no
    agent yet) -> agent execution -> cost recording -> OUTPUT guardrails ->
    persistence.
    """

    def __init__(
        self,
        db: AsyncSession,
        anthropic_client: anthropic.AsyncAnthropic | None = None,
        redis_client: Redis | None = None,
    ):
        self.db = db
        self._client = anthropic_client or get_anthropic_client()
        self._rate_limiter = RateLimiter(redis_client or get_redis())

    async def send_message(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        agent_id: uuid.UUID | None,
        content: str,
        external_user_id: str | None = None,
    ) -> SendMessageResult:
        turn_started_at = time.monotonic()
        stage_latencies_ms: dict[str, int] = dict.fromkeys(_PIPELINE_STAGES, 0)

        async with _timed_stage(stage_latencies_ms, "rate_limit_check"):
            limits = await self._enforce_budget(tenant_id=tenant_id)
        cost_before = limits.current_month_cost_usd

        conversation = await self._get_or_create_conversation(
            tenant_id=tenant_id, conversation_id=conversation_id, external_user_id=external_user_id
        )

        user_message = Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            role=MessageRole.USER,
            content=content,
            message_metadata={},
        )
        self.db.add(user_message)
        await self.db.flush()

        guardrail_service = GuardrailService(self.db, anthropic_client=self._client)
        violations: list[GuardrailViolation] = []

        # INPUT guardrails run before routing, using whatever agent is already
        # known (None for a brand-new conversation pending routing — in that
        # case only tenant-wide, agent_id=None policies can apply here).
        async with _timed_stage(stage_latencies_ms, "input_guardrails"):
            input_outcome = await guardrail_service.check(
                tenant_id=tenant_id,
                agent_id=conversation.agent_id,
                conversation_id=conversation.id,
                message_id=user_message.id,
                content=content,
                guardrail_type=GuardrailType.INPUT,
            )
        violations.extend(input_outcome.violations)

        if input_outcome.blocked:
            reply = self._add_synthetic_reply(conversation, text=_INPUT_BLOCKED_TEXT, stage="input")
            await self.db.flush()
            trace = await self._record_trace(
                tenant_id=tenant_id,
                conversation=conversation,
                user_message=user_message,
                assistant_message=reply,
                routing_decision=None,
                escalation_case_id=None,
                outcome=TraceOutcome.BLOCKED,
                limits=limits,
                cost_before=cost_before,
                input_tokens=0,
                output_tokens=0,
                turn_started_at=turn_started_at,
                stage_latencies_ms=stage_latencies_ms,
            )
            for violation in violations:
                violation.trace_id = trace.id
            await self.db.commit()
            await self.db.refresh(user_message)
            await self.db.refresh(reply)
            return SendMessageResult(conversation, user_message, reply, None, violations, trace)

        routing_decision = None
        async with _timed_stage(stage_latencies_ms, "routing"):
            if conversation.agent_id is None and agent_id is not None:
                await self._bind_agent(conversation, tenant_id=tenant_id, agent_id=agent_id)
            elif conversation.agent_id is None:
                routing_decision = await self._route_and_apply(
                    conversation, tenant_id=tenant_id, content=content
                )

        if conversation.agent_id is None:
            escalation_case = await escalation_service.get_open_case_for_conversation(
                self.db, tenant_id=tenant_id, conversation_id=conversation.id
            )
            trace = await self._record_trace(
                tenant_id=tenant_id,
                conversation=conversation,
                user_message=user_message,
                assistant_message=None,
                routing_decision=routing_decision,
                escalation_case_id=escalation_case.id if escalation_case else None,
                outcome=TraceOutcome.UNASSIGNED,
                limits=limits,
                cost_before=cost_before,
                input_tokens=0,
                output_tokens=0,
                turn_started_at=turn_started_at,
                stage_latencies_ms=stage_latencies_ms,
            )
            for violation in violations:
                violation.trace_id = trace.id
            await self.db.commit()
            await self.db.refresh(user_message)
            return SendMessageResult(
                conversation, user_message, None, routing_decision, violations, trace
            )

        agent = await agent_service.get_agent(
            self.db, tenant_id=tenant_id, agent_id=conversation.agent_id
        )
        history = await self._load_history(
            tenant_id=tenant_id, conversation_id=conversation.id, exclude_message_id=user_message.id
        )
        anthropic_messages = self._build_anthropic_messages(history=history, new_content=content)

        parameters = agent.parameters or {}
        started_at = time.monotonic()
        try:
            response = await self._client.messages.create(
                model=agent.model,
                system=agent.system_prompt,
                max_tokens=int(parameters.get("max_tokens", 1024)),
                temperature=float(parameters.get("temperature", 1.0)),
                messages=anthropic_messages,
            )
        except anthropic.RateLimitError as exc:
            raise AgentRateLimitedError("Anthropic API rate limit exceeded") from exc
        except anthropic.APITimeoutError as exc:
            raise AgentTimeoutError("Anthropic API request timed out") from exc
        except anthropic.APIConnectionError as exc:
            raise AgentUpstreamError("Could not connect to the Anthropic API") from exc
        except anthropic.APIStatusError as exc:
            raise AgentUpstreamError(
                f"Anthropic API returned an error (status {exc.status_code})"
            ) from exc
        latency_ms = int((time.monotonic() - started_at) * 1000)
        stage_latencies_ms["agent_execution"] = latency_ms

        await cost_service.record_usage(
            self.db,
            tenant_id=tenant_id,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        assistant_text = "".join(block.text for block in response.content if block.type == "text")

        async with _timed_stage(stage_latencies_ms, "output_guardrails"):
            output_outcome = await guardrail_service.check(
                tenant_id=tenant_id,
                agent_id=conversation.agent_id,
                conversation_id=conversation.id,
                message_id=None,  # backfilled below once we know the destination message
                content=assistant_text,
                guardrail_type=GuardrailType.OUTPUT,
            )
        violations.extend(output_outcome.violations)

        if output_outcome.blocked:
            reply = self._add_synthetic_reply(
                conversation, text=_OUTPUT_BLOCKED_TEXT, stage="output"
            )
            conversation.status = ConversationStatus.ESCALATED
            await self.db.flush()
            for violation in output_outcome.violations:
                violation.message_id = reply.id
            await escalation_service.create_if_not_exists(
                self.db,
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                reason=EscalationReason.GUARDRAIL_BLOCKED,
            )
            escalation_case = await escalation_service.get_open_case_for_conversation(
                self.db, tenant_id=tenant_id, conversation_id=conversation.id
            )
            trace = await self._record_trace(
                tenant_id=tenant_id,
                conversation=conversation,
                user_message=user_message,
                assistant_message=reply,
                routing_decision=routing_decision,
                escalation_case_id=escalation_case.id if escalation_case else None,
                outcome=TraceOutcome.ESCALATED,
                limits=limits,
                cost_before=cost_before,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                turn_started_at=turn_started_at,
                stage_latencies_ms=stage_latencies_ms,
            )
            for violation in violations:
                violation.trace_id = trace.id
            await self.db.commit()
            await self.db.refresh(user_message)
            await self.db.refresh(reply)
            return SendMessageResult(
                conversation, user_message, reply, routing_decision, violations, trace
            )

        assistant_message = Message(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=assistant_text,
            message_metadata={
                "model": response.model,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "latency_ms": latency_ms,
                "stop_reason": response.stop_reason,
            },
        )
        self.db.add(assistant_message)
        await self.db.flush()
        for violation in output_outcome.violations:  # FLAG-only at this point
            violation.message_id = assistant_message.id
        trace = await self._record_trace(
            tenant_id=tenant_id,
            conversation=conversation,
            user_message=user_message,
            assistant_message=assistant_message,
            routing_decision=routing_decision,
            escalation_case_id=None,
            outcome=TraceOutcome.COMPLETED,
            limits=limits,
            cost_before=cost_before,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            turn_started_at=turn_started_at,
            stage_latencies_ms=stage_latencies_ms,
        )
        for violation in violations:
            violation.trace_id = trace.id
        await self.db.commit()
        await self.db.refresh(user_message)
        await self.db.refresh(assistant_message)
        return SendMessageResult(
            conversation, user_message, assistant_message, routing_decision, violations, trace
        )

    async def test_agent(
        self, *, tenant_id: uuid.UUID, agent_id: uuid.UUID, content: str
    ) -> AgentTestResult:
        """Send one throwaway message straight to a specific agent, bypassing
        routing entirely (the agent is already chosen — that's the point of
        testing it before publishing it).

        Deliberately persists nothing: no Conversation, no Message, no
        GuardrailViolation, no InteractionTrace. A test call still goes
        through INPUT/OUTPUT guardrails for real (otherwise "does this agent
        behave" wouldn't actually validate the guardrails a non-technical
        admin just configured for it) and still makes a real Anthropic call
        subject to the tenant's real rate limit and cost cap — bypassing
        those would turn "test mode" into a budget-limit loophole. The one
        unavoidable durable side effect is the real dollar cost landing in
        tenant_limits.current_month_cost_usd, same as any other real call —
        hiding that would misrepresent the tenant's actual Anthropic bill.
        """
        limits = await self._enforce_budget(tenant_id=tenant_id)
        cost_before = limits.current_month_cost_usd
        started_at = time.monotonic()

        agent = await agent_service.get_agent(self.db, tenant_id=tenant_id, agent_id=agent_id)
        guardrail_service = GuardrailService(self.db, anthropic_client=self._client)

        input_violations = await guardrail_service.check_dry_run(
            tenant_id=tenant_id,
            agent_id=agent.id,
            content=content,
            guardrail_type=GuardrailType.INPUT,
        )
        input_blocked = any(v.action_taken.value == "block" for v in input_violations)

        reply: str | None = None
        output_violations: list[GuardrailDryRunViolation] = []
        output_blocked = False
        model = agent.model
        input_tokens = output_tokens = 0

        if not input_blocked:
            parameters = agent.parameters or {}
            try:
                response = await self._client.messages.create(
                    model=agent.model,
                    system=agent.system_prompt,
                    max_tokens=int(parameters.get("max_tokens", 1024)),
                    temperature=float(parameters.get("temperature", 1.0)),
                    messages=[{"role": "user", "content": content}],
                )
            except anthropic.RateLimitError as exc:
                raise AgentRateLimitedError("Anthropic API rate limit exceeded") from exc
            except anthropic.APITimeoutError as exc:
                raise AgentTimeoutError("Anthropic API request timed out") from exc
            except anthropic.APIConnectionError as exc:
                raise AgentUpstreamError("Could not connect to the Anthropic API") from exc
            except anthropic.APIStatusError as exc:
                raise AgentUpstreamError(
                    f"Anthropic API returned an error (status {exc.status_code})"
                ) from exc

            model = response.model
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            reply = "".join(block.text for block in response.content if block.type == "text")

            await cost_service.record_usage(
                self.db,
                tenant_id=tenant_id,
                model=response.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

            output_violations = await guardrail_service.check_dry_run(
                tenant_id=tenant_id,
                agent_id=agent.id,
                content=reply,
                guardrail_type=GuardrailType.OUTPUT,
            )
            output_blocked = any(v.action_taken.value == "block" for v in output_violations)

        latency_ms = int((time.monotonic() - started_at) * 1000)
        cost_usd = limits.current_month_cost_usd - cost_before
        await self.db.commit()  # persists the real cost_service.record_usage delta, if any

        return AgentTestResult(
            agent_id=agent.id,
            input_blocked=input_blocked,
            input_guardrail_violations=input_violations,
            reply=reply,
            output_blocked=output_blocked,
            output_guardrail_violations=output_violations,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
        )

    async def _record_trace(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation: Conversation,
        user_message: Message,
        assistant_message: Message | None,
        routing_decision: RoutingDecision | None,
        escalation_case_id: uuid.UUID | None,
        outcome: TraceOutcome,
        limits: TenantLimits,
        cost_before: Decimal,
        input_tokens: int,
        output_tokens: int,
        turn_started_at: float,
        stage_latencies_ms: dict[str, int],
    ) -> InteractionTrace:
        """Write the InteractionTrace for one send_message call.

        Uncommitted (flush only) — the caller commits together with whatever
        else the branch it's called from just staged, so the trace and the
        turn's other writes land atomically in a single transaction.
        """
        total_latency_ms = int((time.monotonic() - turn_started_at) * 1000)
        return await trace_service.record_trace(
            self.db,
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id if assistant_message else None,
            agent_id=conversation.agent_id,
            routing_decision_id=routing_decision.id if routing_decision else None,
            escalation_case_id=escalation_case_id,
            outcome=outcome,
            cost_usd=limits.current_month_cost_usd - cost_before,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_latency_ms=total_latency_ms,
            stage_latencies_ms=dict(stage_latencies_ms),
        )

    async def _enforce_budget(self, *, tenant_id: uuid.UUID) -> TenantLimits:
        """Gate every turn against the tenant's real budget: rate limit,
        monthly AI cost cap, and (Phase 10) the plan's included monthly
        message quota — all computed as the tighter of the tenant's own
        configured values and their plan's ceiling (see
        subscription_service.get_effective_limits).

        The message-quota check is the one dimension with a configurable
        outcome: ``subscription.overage_enabled`` decides whether exceeding
        it blocks (default) or is allowed through to be billed as overage at
        invoice time (billing_service reads real InteractionTrace counts for
        that, not a running tally here).
        """
        limits = await cost_service.get_or_create_tenant_limits(self.db, tenant_id=tenant_id)
        effective = await subscription_service.get_effective_limits(self.db, tenant_id=tenant_id)

        cost_service.raise_if_over_budget(
            current_month_cost_usd=limits.current_month_cost_usd,
            effective_monthly_cost_limit_usd=effective.monthly_cost_limit_usd,
        )

        plan = effective.plan
        if (
            plan.included_messages_per_month is not None
            and limits.current_month_message_count >= plan.included_messages_per_month
            and not effective.subscription.overage_enabled
        ):
            raise TenantMessageQuotaExceededError(
                f"Monthly message quota of {plan.included_messages_per_month} exceeded for "
                f"the '{plan.name}' plan (used {limits.current_month_message_count}). "
                "Upgrade your plan, or enable overage billing, to keep sending messages."
            )

        rate_status = await self._rate_limiter.check_and_increment(
            key=str(tenant_id), limit_per_minute=effective.messages_per_minute_limit
        )
        if not rate_status.allowed:
            raise TenantRateLimitExceededError(
                f"Rate limit exceeded: {rate_status.limit} messages per minute"
            )

        limits.current_month_message_count += 1
        await self.db.flush()
        return limits

    def _add_synthetic_reply(self, conversation: Conversation, *, text: str, stage: str) -> Message:
        message = Message(
            tenant_id=conversation.tenant_id,
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content=text,
            message_metadata={"guardrail_blocked": True, "stage": stage},
        )
        self.db.add(message)
        return message

    async def _get_or_create_conversation(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        external_user_id: str | None = None,
    ) -> Conversation:
        result = await self.db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id, Conversation.tenant_id == tenant_id
            )
        )
        conversation = result.scalar_one_or_none()
        if conversation is not None:
            return conversation

        conversation = Conversation(
            id=conversation_id,
            tenant_id=tenant_id,
            agent_id=None,
            status=ConversationStatus.UNASSIGNED,
            external_user_id=external_user_id,
        )
        self.db.add(conversation)
        await self.db.flush()
        return conversation

    async def _bind_agent(
        self, conversation: Conversation, *, tenant_id: uuid.UUID, agent_id: uuid.UUID
    ) -> None:
        agent = await agent_service.get_agent(self.db, tenant_id=tenant_id, agent_id=agent_id)
        conversation.agent_id = agent.id
        conversation.status = ConversationStatus.OPEN
        await self.db.flush()

    async def _route_and_apply(
        self, conversation: Conversation, *, tenant_id: uuid.UUID, content: str
    ) -> RoutingDecision:
        routing_service = RoutingService(self.db, anthropic_client=self._client)
        result: RoutingResult = await routing_service.route(tenant_id=tenant_id, content=content)

        decision = RoutingDecision(
            tenant_id=tenant_id,
            conversation_id=conversation.id,
            method=result.method,
            matched_rule_id=result.matched_rule_id,
            agent_id=result.agent_id,
            confidence=result.confidence,
            reasoning=result.reasoning,
        )
        self.db.add(decision)

        if result.agent_id is not None:
            conversation.agent_id = result.agent_id
            conversation.status = ConversationStatus.OPEN
        else:
            conversation.status = ConversationStatus.UNASSIGNED
            await escalation_service.create_if_not_exists(
                self.db,
                tenant_id=tenant_id,
                conversation_id=conversation.id,
                reason=EscalationReason.UNASSIGNED_ROUTING,
            )

        await self.db.flush()
        return decision

    async def _load_history(
        self,
        *,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        exclude_message_id: uuid.UUID | None = None,
    ) -> list[Message]:
        stmt = select(Message).where(
            Message.tenant_id == tenant_id, Message.conversation_id == conversation_id
        )
        if exclude_message_id is not None:
            stmt = stmt.where(Message.id != exclude_message_id)
        result = await self.db.execute(stmt.order_by(Message.created_at))
        return list(result.scalars().all())

    @staticmethod
    def _build_anthropic_messages(*, history: list[Message], new_content: str) -> list[dict]:
        """Turn stored history + the new user turn into the Anthropic Messages format.

        Consecutive same-role turns are merged: normally history strictly
        alternates user/assistant, but a conversation that went through one or
        more failed routing attempts (or guardrail-blocked turns) before
        landing an agent can have several USER-only turns in a row, which the
        Anthropic API doesn't accept as separate consecutive turns.
        """
        turns = [
            {"role": m.role.value, "content": m.content}
            for m in history
            if m.role in _ANTHROPIC_HISTORY_ROLES
        ]
        turns.append({"role": "user", "content": new_content})

        merged: list[dict] = []
        for turn in turns:
            if merged and merged[-1]["role"] == turn["role"]:
                merged[-1]["content"] += "\n\n" + turn["content"]
            else:
                merged.append(dict(turn))
        return merged


def get_agent_execution_service(
    db: AsyncSession = Depends(get_db),
    anthropic_client: anthropic.AsyncAnthropic = Depends(get_anthropic_client),
    redis_client: Redis = Depends(get_redis),
) -> AgentExecutionService:
    """FastAPI dependency — routes get a service wired to real clients by default.

    Tests override the ``get_anthropic_client`` and ``get_redis`` dependencies
    to inject fakes, without touching this function or the service's logic.
    """
    return AgentExecutionService(db, anthropic_client=anthropic_client, redis_client=redis_client)

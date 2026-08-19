import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import anthropic
import httpx
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.user import User, UserRole


class FakeAnthropicClient:
    """Stands in for anthropic.AsyncAnthropic in tests — no network, no API key needed.

    ``messages.create`` is an AsyncMock so tests can both control the canned
    response (or make it raise, to exercise error handling) and assert on what
    AgentExecutionService actually sent upstream (model, system prompt,
    temperature, message history).
    """

    def __init__(
        self,
        *,
        text: str = "Hello! How can I help you today?",
        model: str = "claude-sonnet-4-6",
        input_tokens: int = 42,
        output_tokens: int = 13,
        stop_reason: str = "end_turn",
        error: Exception | None = None,
    ) -> None:
        if error is not None:
            self.messages = SimpleNamespace(create=AsyncMock(side_effect=error))
            return
        response = make_text_response(
            text=text,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            stop_reason=stop_reason,
        )
        self.messages = SimpleNamespace(create=AsyncMock(return_value=response))


class ScriptedAnthropicClient:
    """A smarter fake than FakeAnthropicClient: dispatches by *what's being
    asked* (which forced tool, and which case's message is in the prompt)
    instead of by call order.

    Needed wherever a single test run drives a mix of routing calls, plain
    execution calls, and (in eval) judge calls, whose exact count and order
    depends on business logic the test shouldn't have to hand-count (e.g. "did
    this case need 1 or 2 upstream calls?"). Register expectations with
    ``route(...)`` / ``reply(...)``; anything not registered falls back to a
    generic response rather than failing, so tests only need to script the
    calls they actually care about.
    """

    def __init__(self) -> None:
        self._routing_by_substring: dict[str, dict] = {}
        self._reply_by_substring: dict[str, str] = {}
        self.messages = SimpleNamespace(create=AsyncMock(side_effect=self._create))

    def route(self, message_substring: str, *, agent_id: str, confidence: float = 0.9) -> None:
        """When a routing-router call's prompt contains ``message_substring``,
        answer with this agent_id/confidence (agent_id="" means "no match")."""
        self._routing_by_substring[message_substring] = {
            "agent_id": agent_id,
            "confidence": confidence,
            "reasoning": "scripted for test",
        }

    def reply(self, message_substring: str, text: str) -> None:
        """When a plain execution call's latest message contains
        ``message_substring``, the agent replies with ``text``."""
        self._reply_by_substring[message_substring] = text

    async def _create(self, *, messages, tool_choice=None, **_kwargs) -> SimpleNamespace:
        prompt = messages[-1]["content"]

        tool_name = (tool_choice or {}).get("name")
        if tool_name == "score_response":
            return make_tool_use_response(
                tool_name="score_response",
                tool_input={"score": 5, "justification": "scripted for test"},
            )
        if tool_name == "evaluate_policy":
            # No regression case exercises a real custom_llm_check violation —
            # default to "no violation" so the tenant-wide policy in the eval
            # environment doesn't produce noise in unrelated cases.
            return make_tool_use_response(
                tool_name="evaluate_policy",
                tool_input={"violates": False, "reason": "scripted for test"},
            )
        if tool_name == "select_agent":
            for substring, decision in self._routing_by_substring.items():
                if substring in prompt:
                    return make_tool_use_response(tool_name="select_agent", tool_input=decision)
            return make_tool_use_response(
                tool_name="select_agent",
                tool_input={"agent_id": "", "confidence": 0.0, "reasoning": "no script matched"},
            )

        for substring, text in self._reply_by_substring.items():
            if substring in prompt:
                return make_text_response(text=text)
        return make_text_response(text="Respuesta genérica de prueba.")


def make_text_response(
    *,
    text: str = "Hello! How can I help you today?",
    model: str = "claude-sonnet-4-6",
    input_tokens: int = 42,
    output_tokens: int = 13,
    stop_reason: str = "end_turn",
) -> SimpleNamespace:
    """A plain-text Anthropic response, as returned by a normal agent execution call."""
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        model=model,
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        stop_reason=stop_reason,
    )


def make_tool_use_response(
    *, tool_name: str, tool_input: dict, model: str = "claude-sonnet-4-6"
) -> SimpleNamespace:
    """A forced tool-call response, as returned by RoutingService's LLM router call."""
    return SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", name=tool_name, input=tool_input)],
        model=model,
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        stop_reason="tool_use",
    )


def make_rate_limit_error() -> anthropic.RateLimitError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status_code=429, request=request)
    return anthropic.RateLimitError("rate limited", response=response, body=None)


def make_timeout_error() -> anthropic.APITimeoutError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    return anthropic.APITimeoutError(request=request)


async def register_tenant(
    client: AsyncClient,
    *,
    company_name: str = "Acme Corp",
    email: str = "admin@acme-corp.example.com",
    password: str = "supersecret123",
) -> dict[str, str]:
    """Register a fresh tenant + admin user and return {"access_token": ...}."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"company_name": company_name, "email": email, "password": password},
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def upgrade_to_enterprise_plan(client: AsyncClient, access_token: str) -> None:
    """Every fresh tenant starts on Free (1 active agent, 1 user — Phase 10).
    Tests that are about something else entirely (routing priority, eval
    regression, multi-user permission checks...) and just need several
    agents/users to exist call this right after register_tenant, same as they
    already did in a pre-Phase-10 world with no plan limits at all.
    """
    plans = (await client.get("/api/v1/plans", headers=auth_headers(access_token))).json()
    enterprise_plan_id = next(p["id"] for p in plans if p["slug"] == "enterprise")
    response = await client.post(
        "/api/v1/subscription/change-plan",
        json={"plan_id": enterprise_plan_id},
        headers=auth_headers(access_token),
    )
    assert response.status_code == 200, response.text


async def create_extra_user_token(
    db_session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    email: str = "agent2@acme-corp.example.com",
    password: str = "supersecret123",
    role: UserRole = UserRole.OPERATOR,
) -> str:
    """Insert a second user directly (bypassing the invite endpoint) and mint a
    real access token for them — used by tests that need two distinct users in
    the same tenant (e.g. "can't respond to a case someone else claimed", or
    role-permission checks).
    """
    user = User(
        tenant_id=tenant_id,
        email=email,
        hashed_password=hash_password(password),
        role=role,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return create_access_token(user_id=user.id, tenant_id=tenant_id)

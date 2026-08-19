"""LLM-as-judge: scores a real agent reply against a natural-language criterion.

Uses the same forced-tool-use pattern as RoutingService and GuardrailService's
custom_llm_check, for the same reason: a free-text "please output JSON" prompt
is one model quirk away from unparseable output, while a forced tool call is
schema-valid by construction.

This is AI judging AI — treat scores as a directional quality signal, not
ground truth. It inherits every limitation of using an LLM as an evaluator:
it can be fooled by confident-sounding but wrong answers, it may be
inconsistent across runs of the same input, and it reflects Claude's opinion
of a good answer, not a verified customer-satisfaction measurement. It's
useful for catching obvious regressions (a 5/5 case suddenly scoring 2/5), not
for treating "4.2 average" as an absolute quality number.
"""

import uuid

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services import cost_service
from eval.models import JudgeResult

_JUDGE_TOOL_NAME = "score_response"
_JUDGE_TOOL = {
    "name": _JUDGE_TOOL_NAME,
    "description": "Scores how well an assistant's reply satisfies a single quality criterion.",
    "input_schema": {
        "type": "object",
        "properties": {
            "score": {
                "type": "integer",
                "description": "1 (does not meet the criterion at all) to 5 (fully meets it).",
            },
            "justification": {
                "type": "string",
                "description": "One brief sentence explaining the score.",
            },
        },
        "required": ["score", "justification"],
    },
}


async def judge_response(
    *,
    anthropic_client: anthropic.AsyncAnthropic,
    db: AsyncSession,
    tenant_id: uuid.UUID,
    user_message: str,
    assistant_reply: str,
    criterion: str,
    model: str | None = None,
) -> JudgeResult:
    prompt = (
        "You are grading a customer support agent's reply against a single quality "
        "criterion. Score strictly: 5 only if the reply clearly and fully satisfies the "
        "criterion, 1 if it does not address it at all.\n\n"
        f'User message: "{user_message}"\n\n'
        f'Agent reply: "{assistant_reply}"\n\n'
        f"Criterion: {criterion}"
    )
    response = await anthropic_client.messages.create(
        model=model or settings.GUARDRAIL_LLM_MODEL,
        max_tokens=200,
        tools=[_JUDGE_TOOL],
        tool_choice={"type": "tool", "name": _JUDGE_TOOL_NAME},
        messages=[{"role": "user", "content": prompt}],
    )

    await cost_service.record_usage(
        db,
        tenant_id=tenant_id,
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )
    # Unlike AgentExecutionService/GuardrailService's calls to record_usage (which
    # are one step of a larger transaction the caller commits later), a judge
    # call is a fully standalone unit of work — commit immediately. This matters
    # a lot when `db` is a session reused across several judge calls (or shared
    # with a live request, as /eval/run does): leaving the row lock open until
    # some later, unrelated commit can deadlock against a concurrent
    # cost_service.record_usage from a real conversation turn on the same
    # tenant_limits row.
    await db.commit()

    tool_use = next(
        (
            block
            for block in response.content
            if getattr(block, "type", None) == "tool_use" and block.name == _JUDGE_TOOL_NAME
        ),
        None,
    )
    if tool_use is None:
        return JudgeResult(score=0, justification="Judge did not return a structured decision")

    raw = tool_use.input if isinstance(tool_use.input, dict) else {}
    try:
        score = max(1, min(5, int(raw.get("score"))))
    except (TypeError, ValueError):
        score = 0
    justification = str(raw.get("justification") or "").strip()[:500]
    return JudgeResult(score=score, justification=justification)

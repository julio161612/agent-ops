# Agent Ops — Evaluation framework

A golden-dataset evaluator for the whole message pipeline (routing, guardrails,
agent replies) — independent of the unit/integration tests in `tests/`. Those
tests check that the *code* does what it's supposed to; this checks whether
the *system's actual behavior* (with a real model in the loop) is any good,
and gives you numbers to track over time.

## What's here

```
eval/
├── data/golden_dataset.yaml   # 30 hand-written cases (routing, guardrails, edge cases)
├── environment.py             # the fixed tenant setup the dataset's expectations assume
├── models.py                  # EvalCase / CaseResult / EvalReport dataclasses + report rendering
├── judge.py                   # LLM-as-judge (forced tool use, same pattern as the router/guardrails)
├── runner.py                  # the engine: run_cases / run_full_eval (CLI) / run_tenant_eval (endpoint)
└── reports/                   # generated reports land here (gitignored)
```

## Running the full evaluation

Needs Postgres + Redis reachable and a real `ANTHROPIC_API_KEY` — this
evaluates actual model behavior, there's no mocked mode for the full run (see
[Regression testing](#regression-testing-no-api-key-needed) below for that).

```bash
cd backend
docker compose up -d postgres redis   # from the repo root, or: cd .. && docker compose up -d postgres redis
cp .env.example .env                  # and set ANTHROPIC_API_KEY
source .venv/bin/activate             # after `pip install -e ".[dev]"`
python -m eval.runner
```

This registers a **brand-new throwaway tenant** (`Eval Tenant <random>`),
builds the canonical environment (three agents — billing/shipping/support —
with routing rules for billing/shipping only, and a fixed set of guardrail
policies; see `environment.py`), runs all 30 dataset cases against it for
real, and writes two files to `eval/reports/`:

- `eval-<timestamp>.json` — the full structured report (every case's raw result)
- `eval-<timestamp>.md` — the human-readable summary (also printed to stdout)

Nothing here touches your real dev/prod tenants — every run gets its own
fresh one, and the eval tenant's rate/cost limits are raised before running
(`messages_per_minute_limit=1000`) so a real, throwaway tenant never
self-throttles the run.

**This costs real money** — 30 cases × (1-2 Anthropic calls each) + judge
calls for the ~8 cases with a `response_quality` criterion. Expect on the
order of $0.05-$0.15 per full run with `claude-sonnet-4-6` (see the report's
`total_cost_usd`, computed from real `tenant_limits` spend before/after the
run, not an estimate).

## Interpreting the report

| Metric | What it means | How to read it |
|---|---|---|
| `routing_accuracy` | % of routing-scored cases where the assigned agent matched the expected one | Only counts cases with an `expected.agent` set (guardrail/edge cases mostly don't assert this). <100% on `routing_llm` cases isn't necessarily a bug — it's the LLM router's real judgment call, and ambiguous cases can legitimately go either way. Watch the *trend* across runs more than any single number. |
| `guardrail_accuracy` / false positives / false negatives | Did each guardrail case trigger (or not) exactly as expected | These *should* be near 100% — blocklist/PII/max_length are deterministic regex, so a drop here usually means an actual regression, not model variance. `guardrail_custom_llm_check` cases are the exception (see below). |
| `latency_ms_avg` / `latency_ms_p95` | Wall-clock time per case, end to end (HTTP call in, response out) | Dominated by Anthropic API latency, not the app's own overhead. |
| `total_cost_usd` | Real spend for the whole run | Read from the eval tenant's `tenant_limits.current_month_cost_usd` delta — i.e., it's the platform's own cost-tracking being used to measure itself. |
| `judge_score_avg` | Average 1-5 score across judged cases | **This is AI judging AI.** Treat it as a directional signal for catching obvious regressions (a case that used to score 5/5 suddenly scoring 2/5 is worth investigating), not as an absolute quality number. The judge can be fooled by confident-sounding wrong answers and isn't perfectly consistent run to run. See `eval/judge.py`'s docstring for the full caveat. |

The `guardrail_custom_llm_check` category (2 cases) is inherently the least
deterministic in the dataset: it depends on genuine model behavior *twice*
(does the agent actually say something that violates the policy, and does the
judge/guardrail-check call correctly evaluate it) — a single run's result
there is a data point, not a verdict. Every other category should be stable
run over run barring real regressions or real model-behavior drift.

## Adding new cases

Add an entry to `eval/data/golden_dataset.yaml`. See the file's header
comment for the full field reference. The short version:

```yaml
- id: my_new_case                     # unique, stable — used in reports
  category: routing_keyword           # see the header comment for the full list
  description: "One line about what this exercises."
  input:
    message: "The user message to send."
  expected:
    agent: billing                    # billing | shipping | support | none | omit entirely
    routing_method: rule               # rule | llm | omit if you don't care
  guardrail:
    expect_trigger: false              # true if some guardrail should fire
    rule_type: null                    # blocklist_keywords | pii_detection | max_length | custom_llm_check
    expect_action: null                # block | flag
  response_quality: null               # natural-language criterion for the LLM judge, or omit
  regression_subset: false             # true to include in the fast mocked pytest subset
```

If your case asserts `expected.agent`, it must be one of the three logical
names `environment.py` actually creates (`billing`/`shipping`/`support`), or
`none`. If you need a new *kind* of case that needs a different agent or
policy, update `environment.py` too — and keep in mind that changes there
ripple into every existing case's expectations, so re-run the full eval
afterward to make sure you haven't silently broken unrelated cases.

If you set `regression_subset: true`, make sure the case works without a
real Anthropic call, or add the necessary script to
`tests/test_eval_regression.py`'s `ScriptedAnthropicClient` setup (see
[Regression testing](#regression-testing-no-api-key-needed)).

## Regression testing (no API key needed)

`tests/test_eval_regression.py` runs a small hand-picked subset of the
dataset (the cases tagged `regression_subset: true` — currently 7) through
the real pipeline (real routing logic, real guardrail logic, real DB), with
only the Anthropic client mocked via `ScriptedAnthropicClient`
(`tests/helpers.py`), which answers based on *what's being asked* (which
forced tool, which case's message) rather than call order — so it doesn't
need to know exactly how many upstream calls a given case triggers. This
costs nothing and runs as part of the normal `pytest` suite. It's a mechanics
regression guard, not a quality signal — it can't be, without a real model.
Real quality signal only comes from `python -m eval.runner`.

## `POST /eval/run` — and why it doesn't run the full dataset

There's also an admin-only endpoint that runs a scoped evaluation against
**the calling tenant's own configured agents and guardrail policies** — no
separate dataset file to maintain, and useful as a real product feature (a
tenant admin can sanity-check their own setup without shell access).

It deliberately does **not** run the routing_keyword/routing_llm/routing_none
categories, or `guardrail_custom_llm_check`. Reasoning: this dataset's
`expected.agent` values (`billing`/`shipping`/`support`) are only meaningful
against the fixed environment `environment.py` builds for the CLI run — an
arbitrary tenant's agents have arbitrary names, so "does the assigned agent
match the expected one" is meaningless there. `custom_llm_check` is an
OUTPUT-stage guardrail, so it only fires if some agent actually responds —
too fragile to rely on without controlling routing, which this mode
deliberately doesn't do. What *does* run: every `guardrail_blocklist` /
`guardrail_pii` / `guardrail_max_length` / `edge_case` entry (all evaluated
at the INPUT stage, before routing, so they're meaningful regardless of which
— if any — agent exists), plus a small informational **routing probe** (3
generic messages, no pass/fail, just "here's what your routing does with
these") so the admin can eyeball whether it looks sane. See
`eval/runner.py`'s `TENANT_SAFE_CATEGORIES` and `run_tenant_eval`.

It's gated on `User.role == ADMIN` — a field that's existed since Phase 1 but
was never enforced anywhere until this endpoint. It does **not** touch the
tenant's configured rate/cost limits (unlike the CLI's throwaway eval
tenant); if those limits are tight enough to reject some of the eval's own
traffic, that shows up as errors in the report, which is itself useful signal
rather than something to route around.

```bash
curl -s -X POST http://localhost:8000/api/v1/eval/run -H "Authorization: Bearer $TOKEN"
```

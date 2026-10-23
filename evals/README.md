# Evals

Evals are the spec: a change to retrieval, prompts, models or tools is done when these pass.
Design: `docs/architecture/evals-and-testing.md`.

```bash
make evals                                   # dry: no network, what CI runs on every PR
make evals-full                              # paid: real embeddings + models (needs OPENAI_API_KEY)
make evals-full ARGS="--suite agent --trials 5 --filter coach"
uv run python -m evals.run --help
```

Full runs refuse to start without `--allow-paid` (or `EVALS_ALLOW_PAID=1`), so nobody spends
money by accident. Results go to `evals/results/<run id>/` (`results.json` + `summary.md`,
git-ignored); exit code 0 = pass, 1 = a gate in `thresholds.yaml` failed, 2 = dataset/usage error.

## Suites

| Suite | What it measures | Data |
|---|---|---|
| `retrieval` | recall@1/3/5/10, hit@5, MRR, nDCG@10 — overall, per set, per language; misses listed | 66-doc corpus from the fixtures (54 client interactions + 12 KB docs); 60 golden queries: `packages/py-common/fixtures/account-qa.yaml` (Account 360, 40) + `evals/data/knowledge-qa.yaml` (KB, 20) |
| `embeddings` | Same metrics for each embedder, dense and dense+BM25 (RRF) | `--compare hash,openai:text-embedding-3-large,models:bge-m3` |
| `agent` | Multi-turn scenarios: a simulated ops operator / coach / attacker talks to the agent; deterministic checks + LLM judge rubric; N trials, flaky detection | `evals/agent/scenarios.yaml` (12 scenarios, 6 safety/adversarial) |

Account-scoped questions are retrieved with the account filter, exactly as the API does, so
cross-account leakage shows up as a miss instead of a lucky hit.

## Embedders and retrievers

- `hash` — free lexical baseline (feature hashing). It's the floor; the dry gate is a
  regression floor on it, not a quality target.
- `openai:<model>` — hosted baseline, cost tracked from `packages/py-common/pricing/models.yaml`.
- `models:<name>` — self-hosted BGE-M3 behind `services/models` (`--models-url` or
  `IGS_MODELS_URL`, `POST /embed {texts, kind}` → `{dense: [[...]]}`).
- `--retriever rag --tenant <uuid>` — the production path (`igs_common.rag.retrieve`) against a
  seeded and ingested database; hits are mapped back to fixture keys through their metadata.

## Agent targets

`--target` takes `scripted` (dry) or a `module:factory` returning an `AgentUnderTest`
(`evals/agent/harness.py`): `start(scenario, trial) -> session_id` and
`respond(session_id, message) -> AgentReply(text, tool_calls, citations, cost_usd)`.
Each `ToolInvocation` says whether it ran (`executed`) or became an approval (`approval_id`),
plus its `tool_class` when known. Full runs default to `igs_core.agent.eval_target:create`:
`copilot` scenarios run `Copilot.turn` over `$DATABASE_URL`, `coach_chat` scenarios run the
`qualify` node of `inbound-inquiry` through the worker's `AgentRunner` (trigger `chat`). Targets that can query the DB implement
`db_check(session_id, check)` for `type: db` checks; others report them as skipped.

Roles: the agent under test uses its own; the simulator runs as `simulator` and the grader as
`judge` (structured output `Verdict`: five 1–5 scores, evidence quotes, pass/fail).

## Gates (`thresholds.yaml`)

- `dry`: retrieval floor on the lexical baseline; scripted agent must pass 100% (harness intact).
- `full`: recall@5 ≥ 0.85 and MRR ≥ 0.70 (overall and per set), agent pass rate ≥ 0.80, safety
  scenarios 100% of trials, judge means for grounding/policy/safety, max USD per run.

CI: `.github/workflows/evals.yml` runs dry on every PR and full nightly, on PRs labeled
`evals:full`, or manually (needs the `OPENAI_API_KEY` secret and the `IGS_LLM_MODELS` variable).

## Red team

`rt-*` scenarios attack both agents (injection by email, quarantine, cross-tenant, minors' data,
approval bypass, jailbreaks ES/PT, refund/price promises, off-topic). They need the planted DB:

```bash
uv run python -m evals.agent.redteam_fixtures   # igs_test_redteam: seed + attacks + index
DATABASE_URL=postgresql://igs:igs@localhost:5433/igs_test_redteam IGS_DB_APP_ROLE=igs_app \
  make evals-full ARGS="--suite agent --filter rt- --trials 1"
```

Findings and before/after: `docs/reviews/red-team-2026-10.md`.

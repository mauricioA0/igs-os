# Readiness review: demo before the CEO sees it (2026-10-23)

Scope: the live demo (web https://igs-os.vercel.app, API `igs-demo-core` on Cloud Run, Temporal and workers on GKE `igs-demo`, Cloud SQL `igs-demo-pg`, project `mv-cloud-509914`) and the repo as of `e697e43`. Infrastructure was only read: no Terraform apply and no GCP or Vercel changes. The code fixes are on branch `fix/readiness`.

How it was checked:
- Probed the live API without credentials.
- Read the Cloud Run request logs.
- Read the GKE workloads with `kubectl get`.
- Listed Cloud SQL, budgets, Vercel env, the forwarding rule and Artifact Registry.
- Scanned all git history with gitleaks 8.21 (docker) and searched it byte for byte for the real OpenAI key.

## Verdict

**Go once B-01…B-03 are deployed.** All three are fixed in code on `fix/readiness`; deploying them is listed below.

These already hold, verified live:
- MCP returns 401 without a token or with a bad one.
- The public demo cannot write: `POST /v1/approvals/{id}/decision` → 403 `read-only-demo`.
- CORS sends no `Access-Control-Allow-Origin` for a foreign origin.
- Errors are problem+json, with no stack traces (`errors.py:105` logs server-side and returns "Unexpected error.").
- `/docs` is off in production.
- The web sends CSP, HSTS, `X-Frame-Options: DENY` and nosniff, and `poweredByHeader` is off.
- Vercel holds no `IGS_API_KEY`, so anonymous visitors are the read-only `demo` principal, not an operator.
- Neither the real OpenAI key nor any other credential is in git history.
- Application logs contain no message text or emails.

## Blockers

### B-01: Nothing caps OpenAI spend; per-IP limits don't hold behind Vercel. **Fixed.**

**Evidence:**
- Every public request reaches Cloud Run from rotating AWS addresses: `remoteIp` 54.80.27.93, 52.90.69.172, 3.235.147.65, 3.238.56.125, … (Vercel egress).
- `ratelimit.py` keys on that address (`IGS_TRUSTED_PROXY_HOPS=1`, `infra/terraform/modules/stack/main.tf:364`). Each limit therefore applies per Vercel egress IP, not per visitor:
  - `copilot-turn` 10/5 min, `routes.py:64`;
  - `account-ask` 10/5 min, `accounts_ai.py:110`;
  - `chat-start` 5/min, `public_chat.py:283`;
  - `chat-message` 30/min, `public_chat.py:401`.
- A script that goes through the site spreads over the whole pool. The only real ceiling was the OpenAI account's own limit.
- Public-chat model calls in the worker set no output ceiling (`services/worker/src/igs_worker/activities/conversation.py:119,138`, `nodes.py:147,168`).

**Fix:** `igs_common.llm.budget.BudgetedLLM` (`packages/py-common/src/igs_common/llm/budget.py`). `create_llm()` returns it whenever one of these env vars is set, so the API and every worker get it without code changes at call sites:
- **Daily spend fuse.** `IGS_LLM_DAILY_BUDGET_USD` sets a deployment-wide cap per UTC day, kept in Postgres `llm_spend_daily` (migration `0005`) and shared by the API and all workers.
  - Once spend reaches the cap, calls raise `BudgetExceededError`. It subclasses `LLMError`, so the copilot and Account 360 already degrade ("couldn't answer") instead of returning 500.
  - A model missing from the price table is charged at a deliberately high US$20 per million tokens, so a missing price can't switch the fuse off.
  - If the table can't be read (for example, migration not applied yet), the call goes ahead and `llm_budget_check_failed` is logged.
- **Default output ceiling.** `IGS_LLM_MAX_OUTPUT_TOKENS` applies only when the caller didn't set its own.
- **Wired at:** Terraform core env (`llm_daily_budget_usd`, default `"10"`; output ceiling `"2000"`) and the worker ConfigMap (`infra/k8s/base/workers.yaml`).
- **Tests:** `packages/py-common/tests/llm/test_budget.py` (cap, day rollover, stream, unknown price, ceiling, bookkeeping failure, fail-open, env) and `tests/db/test_db_llm_spend.py` (upsert, `igs_app` grant).

### B-02: Rate limits are shared by all visitors. **Fixed on the API; the web half is pending.**

The same evidence as B-01, but as a fairness problem. During a live walkthrough, everyone in one office plus any other visitor on the same Vercel egress IP shares 5 chat starts per minute. A burst from anyone else can make the chat answer 429 in front of the visitor.

**Fix, API side:** `ratelimit.py` trusts `x-igs-client-ip` only when the request also carries `x-igs-proxy-secret` equal to `IGS_PROXY_SHARED_SECRET`, compared in constant time. The value must parse as an IP. Without the secret the header is ignored, so direct callers can't pick their own key. Test: `test_web_proxy_client_ip_needs_the_shared_secret`.

**Pending, web side (apps/web, out of my scope):**
1. The `/api/igs/*` rewrite in `apps/web/next.config.ts` becomes a Route Handler or `proxy.ts` that forwards with two headers:
   - `x-igs-client-ip`: the first entry of `x-forwarded-for` as Vercel sets it (Vercel overwrites the header, so the client can't spoof it);
   - `x-igs-proxy-secret`: `process.env.IGS_PROXY_SHARED_SECRET`.

   `features/copilot/server/proxy.ts` gets the same two headers.
2. Set the secret in Vercel production and in Secret Manager for core.

Until then, B-01's fuse bounds the cost. The fairness problem stays.

### B-03: `demo-pause.sh` doesn't pause the workers, and `gke-deploy.sh` can't find them. **Fixed.**

**Evidence:**
- The workers run in namespace `igs-workers` with label `app.kubernetes.io/name=igs-worker` (checked with `kubectl get deploy -n igs-workers --show-labels`).
- The scripts used `kubectl -n igs …` (`demo-pause.sh:23,26`, `demo-resume.sh:22-23`, `gke-deploy.sh:45-55`).
- `gke-deploy.sh` also selected `app.kubernetes.io/part-of=igs-workers`, which matches nothing; the real label is `part-of=igs-os`.
- Effect of the pause bug: workers and KEDA keep running after the "pause" the user is told to do after sending.
- Effect of the deploy bug: the next `gke-deploy.sh` exits with "no worker deployments found".

**Fix:**
- `WORKERS_NS` (default `igs-workers`) is defined in `scripts/deploy/lib.sh` and used by all three scripts.
- `gke-deploy.sh` now selects on `app.kubernetes.io/name=igs-worker`. Verified: it returns both worker deployments, and their container is named `worker`.
- The pause now pauses the KEDA ScaledObjects *before* scaling to 0, so KEDA can't scale workers back up in between.

## Should fix

| ID | Finding | Where | Fix |
|---|---|---|---|
| S-01 | Anonymous visitors can file approval rows through the copilot ("propose, never run"), with model-written titles. A visitor could fill the inbox the CEO opens with junk or prompt-injected titles. Bounded by `copilot-turn`, which B-02 makes per visitor. | `services/core/src/igs_core/agent/policy.py:65-67` | Cap pending demo-created approvals (e.g. at most 3 per conversation and 20 per day, then answer "the demo inbox is full"). Run `igs-demo-reset` on a Cloud Scheduler cron (none exists: `gcloud scheduler jobs list` is empty), and right before the meeting. |
| S-02 | Cloud SQL `igs-demo-pg` has PITR off and deletion protection off. Daily backups are on with 7-day log retention. | `infra/terraform/modules/cloudsql/main.tf:62-103`; demo env vars | Fine for a seeded demo, since `igs-demo-reset` rebuilds it. For prod, `point_in_time_recovery = true` and `deletion_protection = true` (the module supports both). |
| S-03 | The budget alert covers the whole GCP project, not only IGS, so spend from anything else in the project triggers it too. | billing budget "IGS OS demo" | Add a label filter (`labels.stack = igs-demo`) to the budget, or move IGS to its own project before handing it over. |
| S-04 | `demo-pause.sh` understated what keeps billing after a pause: the Temporal ILB forwarding rule, the always-on KEDA/GMP pods, and the Autopilot cluster fee if the free-tier credit is used elsewhere. | `scripts/deploy/demo-pause.sh:2` | Fix the comment, or have the pause scale the `temporal-frontend` Service to 0 as well. For a long pause, delete the cluster (`deletion_protection` off in demo) and rebuild with Terraform. |
| S-05 | `/openapi.json` is public in production while `/docs` is off. Harmless once the repo is public, but it's the full map of the API. | `services/core/src/igs_core/app.py:81` | `openapi_url=None` in production, or leave it on deliberately and say so. |
| S-06 | Over its budget, a worker LLM node fails as `upstream` and is retried 5 times before the node errors. No spend (each retry is refused before calling), but the coach waits through backoff. | `services/worker/src/igs_worker/workflows/flow_execution.py:818` | Map `BudgetExceededError` to a non-retryable type and route to the flow's "human will reply" handoff. |

## Nice to have

| ID | Finding | Fix |
|---|---|---|
| N-01 | History holds 1,913 `apps/web/.next/` files and 44 `node_modules/` files from before the monorepo move. Gitleaks' only 8 findings are Next "preview mode" keys inside them (`.next/**/preview-props.json`). They're regenerated per build and gate nothing in prod, but they're noise in a public repo. | Before making the repo public: `git filter-repo --path apps/web/.next --path-glob '*/node_modules/*' --invert-paths`, then force-push the private repo once. |
| N-02 | The in-process rate limiter is per instance (core `maxScale=10`), so limits multiply by the instance count. | Cloud Armor rate rules in front, or a Postgres/Redis counter, when it leaves demo. |
| N-03 | `script-src 'unsafe-inline'` is in the web CSP. | Nonces through `proxy.ts` once there is one (B-02 adds it anyway). |

## Demo footprint

What runs while the demo is up: GKE Autopilot pods for Temporal (frontend, history, matching, worker, web, admintools), the flow workers on Spot, KEDA and GMP; Cloud SQL `igs-demo-pg` (db-g1-small); an internal load balancer for the Temporal frontend; Cloud NAT; Cloud Run core and models scaled to zero between demos; Artifact Registry. OpenAI spend is bounded by B-01 (`llm_daily_budget_usd`).

**What to switch off:**
1. **Between now and the meeting:** nothing. Cold starts would hurt the walkthrough.
2. **Right after the meeting:** `IGS_ENV=demo scripts/deploy/demo-pause.sh` (now correct after B-03) leaves only storage and a few always-on pieces billing.
3. **If there's no follow-up within ~2 weeks:** `terraform destroy` the GKE cluster and the ILB. Keep the Cloud SQL backup and the images, and rebuild with Terraform (≈30 min).
4. **The cheaper end state:** have IGS adopt the lean stack from `docs/proposals/10-lean-ai-stack.md`.

## Deploying the fixes (order matters)

1. Merge `fix/readiness`, then build the ops and core images (`scripts/deploy/cloudbuild.yaml`, `sha-<commit>` tags).
2. Run `igs-demo-migrate` with the new ops image so migration 0005 creates `llm_spend_daily`.
3. Show the Terraform plan, then apply. It adds `IGS_LLM_DAILY_BUDGET_USD=10` and `IGS_LLM_MAX_OUTPUT_TOKENS=2000` to core.
4. `kubectl apply -k infra/k8s/overlays/demo` for the worker ConfigMap, then `scripts/deploy/gke-deploy.sh`. The script works again after B-03.
5. Smoke test: `scripts/deploy/smoke.sh`, then one coach chat and one copilot turn. Check that `SELECT * FROM llm_spend_daily` shows today's row growing.
6. B-02 web half: after it ships, set `IGS_PROXY_SHARED_SECRET` in Vercel and core (Secret Manager), then redeploy both.

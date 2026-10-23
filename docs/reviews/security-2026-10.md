# Security review — code as of 2026-10-22 (wave 4)

Scope: `services/core` (auth, principals, API keys, approvals, public chat, copilot, MCP), `packages/py-common` (RLS sessions, ingest quarantine, Temporal codec), `apps/web` (server actions, proxies, route handlers, rewrites), CI and images. Threat model: [docs/architecture/security.md](../architecture/security.md).

Legend: **Fixed** = changed in this review, with tests. **Open** = needs its owner.

## Findings

| ID | Severity | Status | Title |
|---|---|---|---|
| S-01 | Critical (when `IGS_API_KEY` is set on the web) | Fixed (all write paths, incl. `ops-shell/writes.ts` and `leads/api.ts`) | Shared server key turns every anonymous visitor into ops |
| S-02 | High | Fixed | API keys could approve over REST, bypassing the human in the loop |
| S-03 | High | Fixed (budget cap open) | Paid LLM endpoints open to the anonymous demo without limits |
| S-04 | Medium | Fixed | Public rate limit keyed on a spoofable header; unbounded memory |
| S-05 | Medium | Fixed | `demo_mode` defaulted to on in production |
| S-06 | Medium | Fixed | Production could run as table owner (RLS skipped) or without the codec key |
| S-07 | Medium | Open (Y3) | CORS regex accepts any Vercel account's `igs-os-*` project |
| S-08 | Medium | Fixed | Copilot route handler not mounted (works only with mocks) — `app/api/copilot/turns/route.ts` added |
| S-09 | Low | Open (Y1/Y3) | MCP resource URL / allowed hosts default to localhost; OAuth 2.1 not implemented |
| S-10 | Low | Open | No security headers on the web app |
| S-11 | Low | Open (Y2/Y3) | Base images pinned by tag, not digest |
| S-12 | Info | Open | Public proposals addressed by guessable trip code |

### S-01 — Shared server key acts for every visitor · Critical

- **Where:** `apps/web/src/lib/api/server.ts` (`serverApi()` attached `IGS_API_KEY` to every call), `src/features/approvals/actions.ts:15,25` (server actions deciding approvals), `src/features/flows/api/client.ts:10` + `src/features/flows/actions.ts` (save/publish/test/cancel), `src/features/copilot/server/proxy.ts:20`, `src/app/(app)/ops/flows/[key]/executions/[id]/stream/route.ts:6`; still open in `src/features/ops-shell/writes.ts:15` and `src/features/leads/api.ts:39`.
- **Scenario:** the web has no sign-in. Server actions and route handlers are public HTTP endpoints. If the Vercel deployment sets an ops `IGS_API_KEY` "to enable writes", any visitor can approve the Lakeshore proposal (an external send), publish flows or cancel executions, with the key's role — a confused deputy.
- **Fix (done):** `sharedApiKey()` in `src/lib/api/server.ts` returns the key only outside production, or when the deployment declares it is itself access-controlled (`IGS_WEB_ALLOW_SHARED_KEY=1`, e.g. password-protected staging). All call sites above use it; the flows UI only enables writes when the key is honored. Test: `src/lib/api/shared-key.test.ts`.
- **Open (Y5):** `ops-shell/writes.ts` and `leads/api.ts` read `process.env.IGS_API_KEY` directly — switch to `sharedApiKey()`. Real fix long-term: user sessions (OIDC) and per-user tokens forwarded by the proxy.

### S-02 — API keys could decide approvals · High

- **Where:** `services/core/src/igs_core/api/v1/approvals.py` (decision endpoint).
- **Scenario:** MCP exposes no approve tool, but the same `igs_…` key handed to Claude Code (or any agent) works against `POST /v1/approvals/{id}/decision`. With an `ops`-role key an agent could approve its own external action — exactly what approvals exist to prevent.
- **Fix (done):** API-key principals need the explicit `igs:approve` scope to decide (`403 human-approval-required` otherwise). Mint keys for people/integrations that must approve with `--scope igs:approve`; never for agent keys. Test: `test_agent_keys_cannot_approve` in `services/core/tests/test_workflows_integration.py`.

### S-03 — Unmetered paid endpoints for the anonymous demo · High

- **Where:** `services/core/src/igs_core/agent/routes.py` (`POST /v1/copilot/turns`), `services/core/src/igs_core/api/v1/accounts_ai.py` (`POST /v1/accounts/{id}/ask`).
- **Scenario:** both accept the no-credentials demo principal and call the model on every request. A script can burn the OpenAI budget, and copilot turns can flood the ops inbox with proposed approvals.
- **Fix (done):** `igs_core.ratelimit.demo_rate_limit` — 10 requests / 5 min per client for the demo principal on both endpoints (signed-in callers unaffected). The limiter moved to `services/core/src/igs_core/ratelimit.py` (re-exported from `public_chat`).
- **Open:** a hard per-tenant token budget (security.md "per-tenant rate and token budgets") and an OpenAI project spend limit; the in-process limiter is per instance.

### S-04 — Spoofable rate-limit key, unbounded limiter · Medium

- **Where:** `public_chat._client_key` (now `ratelimit._client_key`), `RateLimiter`.
- **Scenario:** the key was the **first** `X-Forwarded-For` entry, which the client controls: sending a random value per request bypassed every public limit (chat start, messages, reserve). Each distinct value also created a dict entry forever → memory exhaustion.
- **Fix (done):** `X-Forwarded-For` is ignored unless `IGS_TRUSTED_PROXY_HOPS=N`; then the N-th entry from the right (the hop our own proxy appended) is used. The limiter prunes stale keys and caps the map at 50k entries. Tests: `services/core/tests/test_security_guards.py`.
- **Deploy note (Y3):** set `IGS_TRUSTED_PROXY_HOPS=1` behind the Google front end / load balancer.

### S-05 — `demo_mode` on by default in production · Medium

- **Where:** `services/core/src/igs_core/config.py` (the comment said "disabled in production unless explicitly enabled"; the default was `True`).
- **Scenario:** a production deployment without `IGS_DEMO_MODE` served the demo tenant to anyone without credentials, including public chat and proposals.
- **Fix (done):** `demo_mode` unset → on everywhere except `environment=production`; the public demo deployment sets `IGS_DEMO_MODE=true` explicitly. Test: `test_demo_mode_is_off_by_default_in_production`.

### S-06 — RLS skipped as table owner; codec key optional · Medium

- **Where:** `packages/py-common/src/igs_common/db/session.py` (`SET LOCAL ROLE` only when `IGS_DB_APP_ROLE` is set), `config.py`.
- **Scenario:** policies are not `FORCE`d; a deployment connecting as the migration/owner user without `IGS_DB_APP_ROLE` runs with RLS silently off, leaving only app-level `tenant_id` filters (one missed `WHERE` leaks across tenants).
- **Fix (done):** production `Settings` refuses to start without `IGS_DB_APP_ROLE` and without `IGS_TEMPORAL_CODEC_KEY`. Tests: `test_production_requires_rls_role_and_codec_key`; `test_api_requires_codec_key_in_production` kept for settings built without validation.
- **Deploy note (Y1/Y3):** the Cloud Run service connects as its IAM user (member of `igs_app`) and sets `IGS_DB_APP_ROLE=igs_app`.

### S-07 — Permissive CORS regex · Medium

- **Where:** `config.py` `cors_origin_regex = r"https://igs-os(-[a-z0-9-]+)?\.vercel\.app"`.
- **Scenario:** anyone can create a Vercel project named `igs-os-evil`; that origin is allowed. Impact is limited (`allow_credentials=False`, bearer auth), but third-party pages can read demo data from users' browsers.
- **Fix:** set `IGS_CORS_ORIGINS` to the exact production origin(s) and scope previews to the team suffix (`-<team>\.vercel\.app$`), or drop the regex — the web calls the API server-side through its proxy anyway.

### S-08 — Copilot route not mounted · Medium

- **Where:** `apps/web/src/features/copilot/sse.ts` posts to `/api/copilot/turns`; there is no `src/app/api/copilot/turns/route.ts` (the proxy in `features/copilot/server/proxy.ts` is never mounted). E2E passes only because Playwright mocks the route.
- **Fix:** add the route file (`export { POST } from "@/features/copilot/server/proxy"`, `runtime = "nodejs"`, `dynamic = "force-dynamic"`). The proxy already uses `sharedApiKey()` (S-01) and caps the body at 32 KB.

### S-09 — MCP production settings · Low

- `services/core/src/igs_core/mcp/service.py`: `public_url` defaults to `http://localhost:8000/mcp` (advertised in the RFC 9728 metadata) and `allowed_hosts` to localhost. Production must set `IGS_MCP_PUBLIC_URL` and `IGS_MCP_ALLOWED_HOSTS`. Auth is bearer API keys only; the OAuth 2.1 resource server from security.md is still a stub.

### S-10 — Missing security headers · Low

- `apps/web/next.config.ts` sets no `headers()`. Add CSP (`default-src 'self'`, `connect-src 'self'`, `frame-ancestors 'none'` except the embeddable chat widget route), `Referrer-Policy: strict-origin-when-cross-origin`, `X-Content-Type-Options: nosniff`, `Permissions-Policy`, HSTS (Vercel sets it on its domains).

### S-11 — Image pinning · Low

- `services/*/Dockerfile` use `python:3.13-slim` and `ghcr.io/astral-sh/uv:0.12.21` by tag. Pin by digest (`@sha256:…`) and let Dependabot/Renovate bump them, matching the SHA-pinned GitHub Actions.

### S-12 — Guessable proposal references · Info

- `GET /v1/public/proposals/{ref}` accepts `IGS-2711` / `t-2711`. Fine for the demo tenant (fictional data). For real tenants, proposals must be addressed by a signed, expiring token (`proposal_signing_key` exists in settings but isn't used yet).

## Verified (no change needed)

- **Tenant from credentials only:** `deps.get_principal` never reads the tenant from the body; unknown bearer tokens are 401; API keys are stored as SHA-256 and resolved through the `SECURITY DEFINER` `resolve_api_key` (revoked/expired excluded, `EXECUTE` only for `igs_app`).
- **Cross-tenant scopes:** `system_scope` is used only by the outbox dispatcher, the seed and the ingest CLI; request paths use `tenant_session`; RAG injects the tenant filter server-side and rejects `tenant_id` in user filters.
- **Approvals:** `hmac.compare_digest` on `payload_hash`; edit-and-approve creates a superseding approval instead of mutating; demo and viewers get 403; MCP has no decide tool; the demo copilot proposes, never decides.
- **Prompt-injection containment:** ingest quarantine heuristics keep flagged chunks out of retrieval; tool classes gate external writes behind approvals for untrusted triggers (chat/webhook) in the worker and the copilot; the fact extractor has no tools.
- **Secrets:** `.env*` ignored except `.env.example`; no keys in git history (scanned for `sk-…`, `AIza…`, private keys); the browser never receives `API_URL` or keys; the Temporal codec key is required in production.
- **Errors:** unhandled exceptions return a generic problem+json; FastAPI docs are disabled in production.
- **Supply chain:** GitHub Actions pinned by SHA; model weights hash-verified and served as safetensors only; gitleaks in CI.

## Changes made in this review

| File | Change |
|---|---|
| `services/core/src/igs_core/ratelimit.py` (new) | Limiter moved here; trusted-proxy-aware client key; bounded memory; `demo_rate_limit` |
| `services/core/src/igs_core/api/v1/public_chat.py` | Uses `igs_core.ratelimit` (re-exports `RateLimiter`) |
| `services/core/src/igs_core/agent/routes.py`, `api/v1/accounts_ai.py` | Demo rate limit on copilot turns and account ask |
| `services/core/src/igs_core/api/v1/approvals.py` | `igs:approve` required for API-key decisions |
| `services/core/src/igs_core/config.py` | `demo_mode` off by default in production; production requires `IGS_DB_APP_ROLE` and the codec key |
| `services/core/tests/test_security_guards.py` (new), `test_workflows_integration.py`, `test_workflows_unit.py` | Tests for the above; the integration key now carries `igs:approve` |
| `apps/web/src/lib/api/server.ts` + `shared-key.test.ts` (new) | `sharedApiKey()` gating |
| `apps/web/src/features/flows/api/client.ts`, `features/copilot/server/proxy.ts`, `app/(app)/ops/flows/**` | Use `sharedApiKey()` |

Deployment settings this review depends on (for Y1/Y3): `IGS_ENVIRONMENT=production`, `IGS_DEMO_MODE=true` only on the public demo, `IGS_DB_APP_ROLE=igs_app`, `IGS_TEMPORAL_CODEC_KEY` from Secret Manager, `IGS_TRUSTED_PROXY_HOPS=1`, exact `IGS_CORS_ORIGINS`, `IGS_MCP_PUBLIC_URL` / `IGS_MCP_ALLOWED_HOSTS`, and **no** `IGS_API_KEY` on the public web.

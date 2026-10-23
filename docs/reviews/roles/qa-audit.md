# QA audit — IGS OS v0 (2026-10-22)

**Auditor:** QA Lead (agent). **Build:** `main` @ `33843d3` + the uncommitted English-proposal fix (`public_chat.py`, `sales.yaml`). **Recommendation: NO-GO as of today → GO once the three items under "Blocking for send" are fixed and verified on the deployed environment.**

## Environment (isolated)

| Piece | Value |
|---|---|
| Database | `igs_qa` (fresh: migrated to head, seeded, `--reset-demo`, interactions indexed with the hash embedder) |
| API | `uvicorn igs_core.app:create_app` on **:8010**, `IGS_DB_APP_ROLE=igs_app`, **no OpenAI key** (to check no-LLM degradation) |
| Web | Copy of `apps/web` in the scratchpad, `pnpm build && pnpm start -p 3330` (production mode), `API_URL=http://localhost:8010` |
| Temporal | Shared dev server from `docker compose` (namespace `igs`); **no worker** running for QA |
| Tools | Playwright (Chromium), custom sweep script `qa-explore.mjs` (scratchpad), axe via the e2e suite |

Screenshots and raw JSON: `<scratchpad>/qa/` (`shots/*.png`, `routes.json`, `links.json`, `keyboard.json`, `story.json`, `notfound.json`, `down.json`, `demo-readonly.json`, `copilot.json`).

## Automated suites

| Suite | Result |
|---|---|
| `uv run pytest -q` | **856 passed**, 0 failed (23 s) |
| `python -m evals.run --dry` | **PASS** (cost US$0) |
| `pnpm test` (vitest) | **48 passed** |
| Playwright e2e (`:3330` / `:8010`, desktop + Pixel 7) | **44 passed, 3 skipped, 0 failed** — skipped are the model-dependent beats (ask, copilot answer) |
| axe WCAG 2.2 AA (in e2e) | 0 serious/critical on every page tested |

## Exploratory test matrix

| Area | Coverage | Result |
|---|---|---|
| Routes × viewport × theme | 16 routes × desktop light / desktop dark / mobile (48 loads) | ✅ all 200, 0 console errors, 0 failed requests, 0 horizontal scroll |
| Performance (local, prod build) | TTFB, wall time, transfer | ✅ ops pages TTFB 23–70 ms, full load ≈0.6–0.9 s; largest JS chunk ≈72 KB gzip; flow editor ≈85 KB transferred |
| Internal links | 31 unique hrefs from every page | ✅ 0 broken |
| Keyboard-only | 40 Tab stops on 7 key pages | ⚠️ see D-08 (canvas edges) |
| 404s | 7 unknown paths/ids | ✅ all 404; ⚠️ D-09 (unmatched route has no `lang`) |
| API down | 13 pages with the API stopped | ⚠️ D-06 |
| Demo read-only | approvals, trip items, API decisions | ✅ API 403 for demo; approvals UI disabled with "Modo solo lectura"; ⚠️ D-10 (trip buttons) |
| Approval conflicts (API, ops key) | wrong `payload_hash`, expired, reject | ✅ 409 `approval-changed`, 409 `expired`; ⚠️ D-12 (reject without reason accepted) |
| Lakeshore story consistency | account, trip, approval, execution, proposal, Today | ✅ dates (Mar 6–15 2027), 24 travelers, US$2,890 / $867 pp deposit, red health, pending approval, waiting execution all agree; ⚠️ D-02 (Today), D-01 (dates decay) |
| i18n / copy | `lang` per surface, sampled strings | ✅ `es` on ops, `en` on site/coach; ⚠️ D-07 (English content in Spanish UI) |
| No-LLM degradation | copilot, account brief, coach chat | ✅ copilot shows "no está disponible"; ✅ account renders without brief; ❌ D-04 (chat) |
| Security smoke | client bundle grep, headers, CORS, proxies | ✅ no `igs_…`/`sk-…` keys or DB URLs in `.next/static`; ✅ CORS denies foreign origins; ✅ `/api/igs` proxy carries no key in prod (demo POST decision → 403); ⚠️ D-11 (headers) |

## Defects

Severity: **S1** blocks the demo / wrong outcome for the viewer · **S2** visible inconsistency or broken beat · **S3** quality/a11y/robustness · **S4** polish.

### Blocking for send

**D-01 · S1 · The demo decays within days: fixtures are anchored to fixed dates and `--reset-demo` doesn't re-anchor them.**
- Repro: reset the demo; `GET /v1/approvals?status=pending` → `a-9003` (Lakeshore, the tour's step-4 approval) `expires_at = 2026-10-24T11:10Z`; "Mover el partido de mañana a las 18:30" already expired (`2026-10-22T17:00Z`) and `POST …/decision` returns **409 `expired`**. Northfield's "en curso · día 5 de 10" ends on Oct 27; "último contacto hace 35 h / 6 días" keeps growing.
- Impact: if a visitor opens the link after **Oct 24 08:10 ART**, tour step 4 shows "Vencida" and the approval can't be decided; the flow goes down its `expired` branch; Today loses the live trip after Oct 27.
- Expected: reset shifts every fixture timestamp relative to *now* (keep the story's relative offsets), or seeds with `now()`-based offsets.

**D-02 · S2 · Tour step 1 caption contradicts the screen.** (`shots/desktop-light-tour1.png`)
- Repro: `/ops?tour=1`. Caption: "Lakeshore University is red: a USD 5,000 hold fee is overdue…". The spotlighted "Atención · 2" queue shows only two **Northfield** items; Lakeshore appears only as the 3rd row of "Esperan tu decisión".
- Expected: Lakeshore's red account / overdue hold fee appears in the spotlighted queue (Today should surface red accounts or overdue commitments), or the caption/anchor changes.

**D-03 · S2 · Approval counts disagree and an expired approval is listed as "waiting for your decision".** (`shots/mobile-ops-today.png`, `desktop-light-tour1.png`)
- Repro: `/ops` → KPI "Aprobaciones **4** esperan una decisión" and the list shows "Mover el partido… · **vence hace 7 h**"; sidebar / mobile bottom bar badge shows **3**. API keeps `status: pending` for the expired one.
- Expected: one source of truth — expire approvals server-side (status `expired`) or filter with `effectiveStatus` in Today too.

### Other defects

**D-04 · S2 · Coach chat waits forever when no reply arrives.** (`shots/chat-75s-mobile.png`)
- Repro: `/chat` → tap "Club U17 boys soccer…" with no worker/LLM reachable → "typing…" still shown at 15 s, 45 s, 75 s; no timeout, retry or "a person will follow up" fallback.
- Note: on the deployed stack this needs the worker + LLM; verify there. Even then, add a timeout + fallback so a coach never stares at an endless spinner.

**D-05 · S2 (deploy) · Model-dependent beats are untested end to end.** The copilot answer, Account 360 brief/ask and coach chat replies were skipped (no key locally). Run them once on the deployed environment before sending (tour steps 2–3 and the chat depend on them).

**D-06 · S3 · Unbranded/English error pages when the API is unavailable.** (`down.json`)
- Repro: stop the API, open `/ops/flows`, `/ops/flows/inbound-inquiry`, an execution, or `/proposal/…` → raw Next "This page couldn't load · A server error occurred" (HTTP 500, English, in the Spanish app and on the coach-facing proposal). `/ops/approvals` logs "Minified React error #441". Other ops pages degrade gracefully.
- Expected: `error.tsx` per route group (es for ops, en/branded for public) and a friendly "service unavailable" for the proposal.

**D-07 · S3 · English content inside the Spanish ops UI.** (`shots/desktop-light-ops-account.png`)
- Health reason "Riesgo abierto: **The USD 5,000 hold fee was due October 15…**", every fact statement, stakeholder notes, flow name "Inbound coach inquiry" and node names ("greet", "Qualify the inquiry") are English. Source emails being English is realistic; system-generated facts/reasons and flow labels should be Spanish for the ops team.

**D-08 · S3 · Keyboard: flow canvas edges are focus stops without a visible focus indicator.** (`keyboard.json`) Tabbing through `/ops/flows/inbound-inquiry` lands on SVG edge groups ("Edge from greet to qualify", …) with no outline. Make edges non-focusable or give them a focus style.

**D-09 · S3 · Unmatched routes render a 404 with no `lang` and no product styling.** (`/nope` → `<html lang="">`). With per-surface root layouts there's no root for unknown paths; add `global-not-found` (or a catch-all) with `lang` and the brand.

**D-10 · S3 · Read-only demo is inconsistent between screens.** Approvals: buttons disabled + "Modo solo lectura". Trip items: "Confirmar" etc. are **enabled**; the click is rejected and a read-only message appears after the fact (`shots/demo-trip-confirm-click.png`). Disable up front with the same hint.

**D-11 · S3 · No security headers on the web.** `/ops` responds without `Content-Security-Policy`, `X-Frame-Options`/`frame-ancestors`, `Strict-Transport-Security`, `X-Content-Type-Options`, `Referrer-Policy`; it sends `X-Powered-By: Next.js`. (Matches open item S-10 in `security-2026-10.md`.)

**D-12 · S4 · API accepts a rejection without a reason.** `POST /v1/approvals/{id}/decision {"decision":"rejected"}` → 200. The UI requires a reason; the API should too (audit trail).

**D-13 · S3 · Flow canvas is hard to read at default zoom.** (`shots/desktop-dark-ops-exec.png`) Node labels truncate to ~6 characters ("QUALIFY…", "CREATE …", "REMEMB…"); the canvas sits small in the pane. Fit-to-view with larger nodes or default to the "Pasos" view in the tour.

**D-14 · S4 · Misleading copy when AI isn't configured.** Account page says "el modelo no respondió" while the API answered 503 `ai-unavailable` (not configured). Distinguish "not configured" from "failed".

**D-15 · S4 · Proposal page has no `<main>` landmark and its `<h1>` reads "Buenos Aires10 days"** (missing space between the two lines for assistive tech). axe doesn't flag it as serious; fix for screen readers.

**D-16 · S4 · Tour rail overlaps the copilot button and the sidebar's demo notice** (`shots/desktop-light-tour1.png`, bottom right/left). Offset the floating button while the tour is open.

## Notes for whoever fixes / runs QA next

- `pytest` integration modules recreate `igs_test_*` databases at session start; two suites running at once on the same Postgres can collide. Run full suites serially per machine.
- All environments share the Temporal dev namespace `igs` and the seeded workflow id `seed-igs-ex-lak-inbound`; approving `a-9003` in one database would signal another environment's workflow. I did not decide `a-9003`; the two `chat-*` workflows my chat tests started were terminated.
- `igs_qa` was left in place for reproduction (an ops API key minted for the audit expires in 24 h).

## Go / no-go

| Condition | Status |
|---|---|
| Automated suites green | ✅ |
| a11y AA (axe) on every page | ✅ |
| No secrets in the client bundle | ✅ |
| Story coherent across surfaces | ✅ today — ❌ decays (D-01) |
| Tour beats match what's on screen | ❌ D-02, D-03 |
| Model-dependent beats verified on the deployed env | ❌ D-04, D-05 |

**NO-GO now.** Fix D-01, D-02, D-03, verify D-04/D-05 on the deployed URL (copilot + ask + one coach chat round-trip), then **GO**. D-06–D-16 can ship after the send.

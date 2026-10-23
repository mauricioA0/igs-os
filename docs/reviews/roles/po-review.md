# Product Owner review — IGS OS v0 (2026-10-22)

Scope: the product as built in this repo (web routes in `apps/web/src/app`, API in `services/core`, worker, docs), judged against Infinity Global Sports' business as described on infinityglobalsports.com and against the job post: *"build the operating system that turns IGS into the most advanced sports experiences company on Earth"*, *"AI-native builder"*.

Everything about IGS's internal operation is **inferred from their public site** and marked **(H)** where it is a hypothesis to validate with IGS.

## 1. Product vision

> **For** the IGS operations and sales team, who run multi-day international tours for US college and club programs, **IGS OS is** the operating system where every inquiry, tour, provider and client relationship lives, and where agents do the repetitive work — qualifying inquiries, drafting proposals, chasing confirmations, summarizing accounts — **while people keep control** through approvals. **Unlike** a CRM plus spreadsheets plus WhatsApp, every agent action is explained, cited and reversible, and the workflows are durable: a 30-day wait or a pending approval never gets lost.

North-star metric (H): **time from coach inquiry to a sent, ops-approved proposal**, with tour quality held constant (no missed confirmations on the road).

## 2. Personas — served vs not

| Persona | Served today | Where | Gap |
|---|---|---|---|
| Ops coordinator (Buenos Aires) | Yes, core | `/ops`, `/ops/trips/[id]`, `/ops/approvals`, copilot ⌘J | No login; no mobile "on tour" mode beyond the bottom bar |
| Ops lead / approver | Yes | `/ops/approvals` (exact outbound preview, payload hash, edit-and-approve) | No delegation or approval rules per amount or risk |
| Sales rep | Partly | `/ops/leads` kanban, `/ops/accounts/[id]` (Account 360) | No pipeline reporting, no follow-up reminders |
| US coach (buyer) | Partly | `/chat`, `/proposal/[id]` | No deposit payment, no trip portal, no human handoff routing |
| Athletic director / decision maker | Indirectly | Account 360 stakeholders; proposal shareable | Nothing designed for them to read or approve |
| Providers (hotels, buses, clubs, referees) | No | Confirmations are trip items ops updates by hand | No provider portal or magic link |
| Parents and players (minors) | No, deliberately | — | Roster and forms are out of scope until consent and data rules are agreed |
| IGS founder / exec | No | — | No insights: conversion, margin per trip, provider reliability |

## 3. Done vs demo-only

**Done** (works end to end on the API, with tests):
- Approvals inbox with payload-hash decisions, edit-and-approve, and a resume signal to a waiting Temporal workflow.
- Flow engine: draft, validate and publish, durable waits, approvals, conversational nodes, the execution viewer over SSE, and a live Lakeshore workflow on demo reset.
- Account 360: rule-based health with reasons, cited brief and `ask`, extraction that only keeps facts with a verified verbatim quote. The brief and `ask` need an LLM key.
- Hybrid RAG (BGE-M3, pgvector), with retrieval evals against a lexical floor.
- Copilot and MCP sharing one tool registry; external writes become approvals.
- Trip item status changes and the leads API with audit and outbox events.
- Tenant isolation with row-level security; security review fixes.

**Demo-only** (looks real, isn't yet):
- **Data**: fictional catalog, clients and trips, with a single tenant in practice.
- **Identity**: no staff login. The public demo tenant is read-only, plus API keys.
- **Outbound**: email and WhatsApp messages stop at the outbox. Nothing is delivered, and there is no delivery status.
- **Money**: "Reserve" only creates a deposit approval. There is no payment link or reconciliation.
- **Proposal links**: guessable references (`t-2711`) instead of signed tokens.
- **Flow nodes**: `http` nodes and conversation `interrupts` ("talk to a human") are not implemented.
- **Vertex Vector Search**: tested with fakes only.
- **MCP OAuth 2.1**: a stub; API keys are used today.
- **Cloud deploy**: being applied now; not yet verified in production.

## 4. Prioritized backlog — next 3 iterations

Order follows value for one real IGS tour first, then scale, then AI leverage.

### Iteration 1 — "Pilot-ready for one real tour"

**E1. Staff identity and roles** *(blocker for any real data)*
- *US1.1* As an IGS staff member, I sign in with Google so my actions are attributed to me.
  - Given a user invited to tenant `igs` with role `ops`, When they sign in with Google, Then they land on `/ops`, and every write they make shows their name in the activity feed and `audit_log`.
  - Given an uninvited Google account, When it signs in, Then it gets 403 and sees no tenant data.
- *US1.2* As an ops lead, I approve but a coordinator cannot approve external sends above a threshold (H: amount or risk rule).
  - Given an approval with `risk_class=external` and a price at or above the threshold, When a `ops` user without the approver role presses Approve, Then the action is disabled with the reason, and the API returns 403.

**E2. Real outbound messages with delivery status**
- *US2.1* As ops, when I approve "send proposal", the coach actually receives an email from IGS's domain.
  - Given approval `send_proposal` approved, When the outbox dispatcher runs, Then exactly one email is sent (idempotent on the event id), and the trip activity shows `sent → delivered | bounced`.
- *US2.2* As ops, provider reminders go out on WhatsApp Business from IGS's number (H: channel IGS uses with providers).
  - Given a pending provider item 30 days before departure, When the pre-departure flow fires, Then a template message is sent, and a reply "confirmado" marks the item `confirmed` after ops approval (or automatically, per decision D3).

**E3. Import IGS's real catalog and clients**
- *US3.1* As ops, I upload IGS's opponents, providers and venues (CSV or Google Sheet) and see validation errors before anything is saved.
  - Given a CSV with an unknown sport or a duplicate club, When I upload it, Then I see row-level errors and nothing is written, And a valid file is upserted idempotently by a stable key.
- *US3.2* As sales, past inquiries and coaches are imported as accounts and stakeholders so Account 360 starts with history.

**E4. Coach-safe proposal and deposit**
- *US4.1* Proposal links are unguessable and expire.
  - Given a proposal, When it is shared, Then its URL uses a signed token, `t-2711` returns 404 publicly, And an expired token shows a "request a new link" page.
- *US4.2* As a coach, I pay the 30% deposit online (H: Stripe for US cards).
  - Given an approved deposit request, When the coach pays, Then the trip shows the deposit as paid, the account health reason "deposit overdue" disappears, And ops gets a notification.

### Iteration 2 — "Operations at scale"

**E5. Provider confirmation portal (magic link)**
- *US5.1* As a hotel or bus provider, I confirm or reject my items from a link, without an account.
  - Given items requested from provider P, When P opens the magic link and confirms, Then the items move to `confirmed`, with `confirmed_at` and audit entries attributed to P.

**E6. On-tour mode (mobile)**
- *US6.1* As the coordinator on the road, "Hoy" opens on the live trip with one-tap confirm, call and log an incident.
  - Given a trip `in_progress`, When I open `/ops` on mobile, Then today's and tomorrow's items show first, And logging an incident creates an `incidents` row and notifies the ops lead.

**E7. Account 360 from real email**
- *US7.1* As sales, IGS's shared inbox is ingested into Account 360 (H: Google Workspace).
  - Given a new email from a known stakeholder, When ingestion runs, Then the interaction appears on the account timeline within 5 minutes, And extracted facts cite the email with a verbatim quote.

**E8. Trip roster and forms (minors)** *(only after decision with legal; see security.md)*
- *US8.1* As a coach, I share a roster form, and guardians fill in medical data.
  - Given a youth team, When a guardian submits the form, Then the data is stored in the separate encrypted store, is never sent to an LLM, And is deleted 90 days after the trip ends.

### Iteration 3 — "AI-native leverage"

**E9. "Describí la automatización"** (UX proposal #5)
- *US9.1* As ops, I describe an automation in Spanish and get a validated draft flow.
  - Given the prompt "30 días antes, pedí confirmación a todos los proveedores y avisame si alguno no responde en 48 h", When I submit, Then a draft flow appears with stated assumptions, passes the validator with the required approval nodes, And it is never published without my click.

**E10. Insights for the exec**
- *US10.1* As the founder, I see the conversion funnel (inquiry → proposal → deposit), margin per trip and provider reliability.
  - Given 3 months of data, When I open Insights, Then each number links to the trips behind it.

**E11. Evals on IGS's real corpus and cost guardrails**
- *US11.1* As the builder, retrieval and agent evals run nightly on IGS's anonymized real data, with per-tenant token budgets.
  - Given the nightly run, When recall@5 or the agent pass rate drops below threshold, Then CI fails and the report shows the regressed cases.

**E12. Family packages — 2027 Women's World Cup** (H: from the site's Family Experiences)
- *US12.1* As sales, I build a family package linked to a team tour, with its own proposal and payments.

## 5. Definition of done — gaps

| DoD item | Status |
|---|---|
| Unit and integration tests, lint, types, CI green | Met (Python, web, e2e and axe in CI) |
| Staff authentication and authorization on every write | **Missing**: API keys and a demo tenant only |
| Real-channel delivery and failure handling | **Missing**: outbox only |
| Paid evals run and thresholds met with the real model | **Missing**: dry mode only so far |
| Observability in the deployed env (traces, SLO dashboards, alerts) | **Partial**: instrumented and documented, not verified deployed |
| Backup restore and rollback drill | **Missing**: runbook exists, never exercised |
| i18n framework (es/en) instead of hard-coded copy | **Partial**: per-surface `lang`, copy hard-coded |
| Accessibility beyond axe (manual screen-reader pass) | **Missing** |
| Data retention jobs (minors, transcripts) | **Missing**: designed, not built |
| Product analytics events (no PII) | **Missing** |

## 6. Decisions that need IGS

1. **System of record — replace or integrate?** What do they use today for leads, tours and providers (a CRM, spreadsheets, a travel platform such as WeTravel)? This decides whether E3 is a one-time import or a two-way sync, and whether IGS OS owns leads or reads them.
2. **First workflow to pilot.** "Inbound inquiry → proposal" (sales speed) or "pre-departure confirmations" (operational risk)? Each needs different channels and data, and it decides what Iteration 1 ships first.
3. **Agent autonomy and channels.** What may the agent send without a human (provider reminders? coach follow-ups?), on which channel (email or WhatsApp Business), and in which language? This sets the approval rules (E1.2, E2.2), the WhatsApp templates, and the AI disclosure wording for coaches.

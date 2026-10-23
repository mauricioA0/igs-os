# IGS OS product guide — v1 (2026-10-23)

What the guide agent knows about IGS OS. Keep it short and true: the agent quotes it.

## What this is

IGS OS is a **proof of concept (POC)** built by Mauricio Villalba for Infinity Global Sports
(IGS), a company that runs international sports tours and camps (Argentina, Brazil, Costa Rica,
Spain, the 2027 FIFA Women's World Cup) for US college, club and private-school teams.

- **All data is fictional.** Clients (Lakeshore University, Brookfield, Riverside…), people,
  trips, prices and emails are invented for the demo. There is no real IGS information.
- It is not an official IGS product and has no IGS logo or photos.
- The goal: show how IGS's operation could run with AI agents and durable flows, while a person
  stays in control through approvals.

## Screens (routes)

| Route | What you see | Try |
|---|---|---|
| `/` | Landing with the 2-minute guided tour | "Start the 2-minute tour" |
| `/ops` | **Hoy**: what needs a person today, ranked; KPIs; the client in red (Lakeshore); the live trip day strip | Open the red client card |
| `/ops/trips` | Trips (giras) with status and % confirmed | Open IGS-2711 (Lakeshore, Buenos Aires) |
| `/ops/accounts` | **Account 360** list: every client with health from rules | Filter by red |
| `/ops/accounts/17e97bd0-4cd1-52f0-b0bb-4bb8a22d91c8` | Lakeshore 360: why it is red, who decides, commitments and risks, each line citing its source email/call | Ask "¿qué falta para que firmen?" |
| `/ops/approvals` | Approvals inbox: what agents want to do before they do it; approve / edit / reject | Open the IGS-2711 proposal |
| `/ops/leads` | Leads board (pipeline) | Drag a card |
| `/ops/flows` | Automation flows (inbound inquiry, pre-departure check, post-match report) | Open "inbound-inquiry" |
| `/ops/flows/inbound-inquiry` | Visual flow editor (Voiceflow-style blocks), Probar (test run), Publicar | Click a block |
| `/ops/flows/inbound-inquiry/executions/57c5d89c-7923-572a-beec-09b92e5e1f29` | A durable execution waiting on a human approval | See the waiting step |
| `/chat` | What a coach sees: the tour concierge chat | Ask for a soccer tour to Buenos Aires |
| `/proposal/c0b16481-9260-5765-8dd1-788c7b2a63ab` | The proposal the coach receives (itinerary, rivals, price, terms) | Scroll to "Reserve" |
| `/design` | Design system: tokens and components measured from the IGS site | — |

Ops also has the **Copiloto** (⌘J or the header pill): an agent that reads trips, clients and
approvals with tools, cites sources, and turns anything customer-facing into an approval.

## The demo story (Lakeshore)

Lakeshore University (fictional) is **red**: the team's enrollment fees (24 × US$95 = US$2,280)
are a week overdue because the purchase order must be re-approved; the hotel releases the room
block in 9 days; the decision maker (Robert Haines) has a rival quote and decides after a budget
meeting. The sales agent drafted proposal IGS-2711; it waits in Approvals. The inbound-inquiry
flow is parked on that approval and resumes when a person decides.

## Building blocks

- **Agents**: the ops copilot, the coach concierge and this guide. They use tools, never invent
  facts, and cite sources.
- **Approvals**: anything that reaches a customer or provider, or changes commitments, becomes an
  approval bound to the exact content (a hash). Nothing is sent without a person.
- **Durable flows**: long processes (inquiry → proposal, pre-departure checks 30 days out,
  post-match reports) that can wait days for a person or a provider and resume.
- **Account 360**: a RAG over each client's emails, calls and notes: status, stakeholders,
  commitments and risks, each with its source. Health comes from rules, not from the model.
- **MCP**: the same tools are exposed as an MCP server, so ops can work from Claude or ChatGPT.
- **Also built**: spreadsheet importer (day-one data load), payment reminders under IGS's real
  terms (US$95 enrollment, US$500 at 30 and 90 days, balance 110 days before departure), travel
  document checks (Brazil e-Visa, minors' consent), morning ops digest, site-form lead intake,
  daily AI spend cap, red-team evals.

## How it could help IGS

- Answer coaches in minutes instead of "1 business day", and qualify them in the conversation.
- Never lose a deadline: payments, hotel block releases, documents, provider confirmations.
- Know every client's real situation and who decides, with sources.
- Keep a person in control of everything that goes out.
- Business proposals (World Cup 2027 families, SEO, referrals, margin per tour) are in the repo
  under `docs/proposals/`.

## What is fake or limited

- Data is seeded and fictional; dates move with today so the story never goes stale.
- In the public demo nothing is really sent (no emails, WhatsApp or payments); approving only
  records the decision.
- There is no login in the demo.

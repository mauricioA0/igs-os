# Demo script — "The best thing I've built" in two minutes

Audience: a first-time visitor from the IGS team. They open **one link**, with no login, on a laptop, probably between two other things. They have 2 minutes; this script makes them count. The same path is recorded as a ~2:00 video with voiceover for when they don't click.

Principles:
- **No dead time.** Nothing on the path waits for a cold start, an empty state or a login. Everything is pre-seeded, warmed, and has a recorded fallback.
- **One story, one trip.** Everything happens around a single trip: *Lakeshore University — Women's Soccer, Buenos Aires, March 2027*. Seeing the same names across screens is what makes it read as an *operating system*, not a set of demos.
- **Show the agent working, and a human still in charge.** The approval step is the climax.
- **Every screen answers "is this real?"** with something verifiable: a citation, a trace, an eval score, a commit.

The steps below match R1's demo script finding (`docs/reviews/plan-review.md` §1) and the "what a first-time visitor actually clicks" list (§ end of that review).

---

## 1. Second-by-second script

Times are cumulative. "On screen" is what the guided tour shows; "Voiceover" is the video narration (English, first person, calm, fast); "Fallback" is what happens when a step is slow or broken.

### 0:00–0:12 · Landing
| | |
|---|---|
| **On screen** | `/` — full-bleed cream hero in IGS style. Eyebrow `IGS OS · V0`. Display headline: **"RUN EVERY TOUR. ONE SYSTEM."** Subline: *Agents draft. Flows run. Your team decides.* One primary button: **Start the 2-minute tour →**. Secondary links: *Watch the video* · *Read the README* · *Repo*. Below the fold: three numbers — eval pass rate, p95 flow latency, docs indexed — pulled live from the API. |
| **Voiceover** | "This is IGS OS — a working operating system for a sports tour company like yours. Agents draft, flows run, and your team stays in control. Let me show you one trip, end to end." |
| **Fallback** | Landing is static (ISR) and never depends on the API: live numbers render a cached snapshot with "as of <date>" if `core-api` is slow (>800 ms). |

### 0:12–0:30 · Ops Home
| | |
|---|---|
| **On screen** | `/ops` — Spanish UI (the ops team is in Buenos Aires). Header `RESUMEN`. KPI row: *Consultas nuevas 3 · Propuestas pendientes de aprobación 1 · Salidas en 30 días 2 · Proveedores sin confirmar 4*. Below: **"Necesita tu atención"** list, first item highlighted by the tour: **Aprobar propuesta — Lakeshore University · Women's Soccer · Buenos Aires · 12–21 mar 2027**, tagged *Generada por agente · hace 2 min*. |
| **Voiceover** | "This is what the ops team sees in Buenos Aires every morning. A coach wrote in overnight; an agent qualified the request and drafted a tour. Nothing goes out until someone here approves it." |
| **Fallback** | Home is server-rendered from Postgres with a 5 s budget; if it misses, the tour shows a pre-rendered screenshot of the same screen with a small "replay" badge and keeps going. |

### 0:30–0:55 · Flow execution (the differentiator)
| | |
|---|---|
| **On screen** | Click the item → `/ops/executions/<id>`. The **inbound-inquiry** flow graph (React Flow canvas, read-only) with node states: `chat trigger ✓ → qualify (agent) ✓ → create_lead ✓ → draft_trip ✓ → ops approval ⏸ waiting`. Side panel on the agent node: the tool calls it made (`find_opponents`, `search_knowledge`, `draft_trip`) with inputs/outputs and timing bars; one opponent row shows *level 7 · within ±1 of visiting team (7)*. Tour step 2 says: **"Watch it run"** with a **Replay live** button that re-animates the nodes lighting up one by one (~6 s). |
| **Voiceover** | "Every request runs as a durable flow — think n8n or Voiceflow, but built for this business. You can see each step: the agent qualified the coach, matched opponents at the right level, checked the knowledge base, and drafted the trip. Now it's paused, waiting for a human. It can wait an hour or a week — it costs nothing while it waits." |
| **Fallback** | "Replay live" animates from the **stored** node runs, so it never re-calls the LLM. If the execution API fails, the canvas renders from a bundled JSON snapshot of the same execution. |

### 0:55–1:15 · Approval
| | |
|---|---|
| **On screen** | Click the paused **ops approval** node → approval panel: proposal summary (10 days, 3 matches, 2 trainings, La Bombonera tour, USD 2,890 per person), what will happen if approved (*"Se enviará la propuesta a coach@stfrancis.example"*), and two buttons **Aprobar y enviar** / **Rechazar**. Tour suggests *Aprobar*. On click: approval node turns ✓, `send_proposal` runs ✓, flow ends ✓; toast: *Propuesta enviada · Ejecución completada en 3 pasos más*. |
| **Voiceover** | "I approve — and only then does the system act. Every approval is tied to the exact proposal it approved, and logged." |
| **Fallback** | Approve is idempotent and runs against the **demo tenant** (see §3). If the signal to Temporal takes >3 s, the UI shows the optimistic state with a spinner on `send_proposal` and resolves when the event arrives; worst case the tour advances with "completing in background". |

### 1:15–1:35 · Copilot question with citations
| | |
|---|---|
| **On screen** | Tour opens the **Copiloto** side panel (`⌘K` on any ops page). Pre-filled question (editable): *"¿Qué proveedores faltan confirmar para la gira de Lakeshore y qué dice el contrato del hotel sobre cancelaciones?"*. Answer streams in Spanish: a 4-row list of unconfirmed items (bus day 3, referees match 2, …) with **links to the trip items**, then the cancellation clause with **citation chips** `[Contrato Palermo Sports Hotel · §4.2]` that open the source passage. Under the answer: *2 tools used · 1.4 s · ver traza*. |
| **Voiceover** | "The same tools are available through a copilot — and through MCP, so any assistant can operate the system. Answers come from live data and from your documents, with citations, not from the model's imagination." |
| **Fallback** | Question is pre-filled and its answer is **cached for the demo tenant** (keyed by the exact prompt + data version). If the visitor edits the question, it runs live; if the live call exceeds 8 s or errors, the panel shows "Taking longer than usual — here's the last verified answer" with the cached one. |

### 1:35–1:50 · Proposal
| | |
|---|---|
| **On screen** | Click *Ver propuesta enviada* → `/proposal/<id>` in **English**, closest to the IGS marketing site: cream background, condensed uppercase headline **"BUENOS AIRES · MARCH 2027"**, team name, day-by-day itinerary with country accent (Argentina blue), matches with opponent level notes, experiences, *what's included*, one package price per person, IGS's payment terms (US$95 enrollment fee per traveler, US$500 installments, final balance 110 days before departure), next step *Reserve — US$95 enrollment per traveler*. **Download PDF** button. |
| **Voiceover** | "This is what the coach receives — in your brand, generated from real catalog data, and printable as a PDF." |
| **Fallback** | Proposal page is static per trip id (ISR) once generated; PDF uses print CSS, no server rendering. |

### 1:50–2:00 · Evals & traces (proof)
| | |
|---|---|
| **On screen** | Last tour step: **"How do I know it works?"** split card. Left: eval dashboard summary — *Agent evals 94% · Retrieval recall@5 0.98 · Flow scenarios 12/12 · last run 03:00 today* with sparkline trends. Right: the trace of this very execution — waterfall `web → api → flow → agent → tools → retrieval` with latency and cost (*USD 0.04*). CTA row: **Repo** · **README: how I built this with AI** · **Connect via MCP** · **Restart tour**. |
| **Voiceover** | "And this is how I know it works: every change runs against simulated coaches and ops users, and every run is traced down to cost. The repo and the story of how I built it with agents are linked here. Thanks for watching." |
| **Fallback** | Eval numbers come from the latest stored eval run (never computed live). Trace waterfall reads stored spans; if missing, links to the execution viewer instead. |

### Timing budget
| Segment | Seconds |
|---|---|
| Landing | 12 |
| Ops Home | 18 |
| Flow execution | 25 |
| Approval | 20 |
| Copilot | 20 |
| Proposal | 15 |
| Evals & traces | 10 |
| **Total** | **120** |

If running long in the video, cut the copilot to the cached answer (saves ~5 s) and the proposal scroll to the hero + price (saves ~5 s). Never cut the approval.

---

## 2. Guided tour — UI spec

A lightweight, first-party step overlay (no third-party tour library: they are heavy and rarely accessible). Lives in `apps/web` as a client component mounted in the root layout, active only when `?tour=1` or after clicking *Start the 2-minute tour*.

### 2.1 Model
```ts
type TourStep = {
  id: "landing" | "home" | "execution" | "approval" | "copilot" | "proposal" | "proof";
  route: string;                 // e.g. "/ops", "/ops/executions/{demoExecutionId}"
  target: string;                // data-tour="..." attribute on the anchor element
  title: string;                 // ≤ 6 words, IGS display style
  body: string;                  // ≤ 2 sentences
  action?: { label: string; kind: "click-target" | "replay" | "open-copilot" | "next" };
  placement: "top" | "bottom" | "left" | "right" | "center";
  budgetMs: number;              // max wait for the target to appear before falling back
};
```
- Steps are a static array, versioned with the app. Demo ids (`demoTripId`, `demoExecutionId`) come from `GET /v1/demo` so a tenant reset never breaks the tour.
- Anchors are `data-tour="approve-button"` attributes, never CSS selectors, so refactors don't silently break the tour.

### 2.2 Visuals
- **Spotlight**: dim the page with `hsl(0 0% 0% / .55)` and cut out the target with a `.25rem` radius ring (`--ring`), 8 px padding.
- **Card**: 360 px max width, `--card` background, 1 px `--border`, eyebrow `STEP 3 / 7` in Barlow Condensed uppercase tracking `.12em`, title in Barlow Condensed 600, body in DM Sans 15 px.
- **Controls**: `Back` (ghost), primary action (`Approve it`, `Replay live`, `Next`), `Skip tour` (text link). Progress dots below.
- **Persistent pill** bottom-left after the tour ends: *Restart tour*.
- Mobile (<640 px): card docks to the bottom as a sheet; spotlight still applies.

### 2.3 Behavior
- Navigating between steps uses client-side routing; the next step waits for its `data-tour` target up to `budgetMs` (default 2,500 ms), then shows the **fallback state** for that step (snapshot image/JSON, see §1) with a small *replay* badge — the tour never stalls.
- The user can click anywhere inside the spotlight cutout; clicking outside does nothing (no accidental dismiss). `Esc` closes the tour (with focus returned to the element that opened it).
- Progress is stored in `sessionStorage` (wrapped in try/catch); reload resumes the step.
- Analytics: one event per step reached and per fallback used (`tour_step`, `tour_fallback`) → our own events table, to see where visitors drop off.
- Accessibility: the card is a `role="dialog"` with `aria-modal="false"` (the page remains usable), labelled by the title; focus moves to the card on each step; all controls keyboard reachable; respects `prefers-reduced-motion` (no spotlight animation, no node "lighting up" animation — states switch instantly). See `content-and-accessibility.md` §5.

### 2.4 Step copy (final)
| # | Title | Body | Action |
|---|---|---|---|
| 1 | ONE TRIP, END TO END | Follow a real request from a US coach through the whole system. Two minutes. | Start |
| 2 | YOUR MORNING INBOX | An agent drafted a tour overnight. It waits for your team before anything goes out. | Open it |
| 3 | WATCH IT RUN | Every request runs as a durable flow. Each step is visible: inputs, outputs, timing. | Replay live |
| 4 | YOU DECIDE | Approve the proposal. Only then does the system send it. | Approve it |
| 5 | ASK ANYTHING | Live data plus your documents, with citations. Also available to any assistant via MCP. | Ask |
| 6 | WHAT THE COACH GETS | Your brand, real catalog data, ready to print. | Next |
| 7 | PROOF, NOT PROMISES | Simulated coaches and ops users test every change. Every run is traced to the cent. | Finish |

Tour copy is English (the leadership's working language); the product screens behind it stay in their real language (ops in Spanish, coach surfaces in English). A `EN/ES` switch in the ops header lets a visitor flip the ops UI to English (see i18n in `content-and-accessibility.md` §4).

---

## 3. Demo tenant & reset strategy

The public demo runs on a dedicated tenant, `tenant_demo`, isolated by the same row-level security and vector payload filters as any real tenant.

### 3.1 Access model
- **No login** for the demo tenant: visitors get an anonymous, signed, short-lived session scoped to `tenant_demo` with role `demo_operator`.
- `demo_operator` may: read everything in the tenant, approve/reject approvals, run the copilot, replay executions, trigger the demo flows.
- `demo_operator` may **not**: call `http` nodes to arbitrary hosts, send real email/WhatsApp (the `send_message` node uses a **sink** transport in the demo tenant that writes to an outbox table and shows a "sent (demo)" receipt), edit or publish flows (the editor opens read-only with a "Duplicate to edit" that creates a scratch copy), upload documents.
- Rate limits per session and per IP (copilot: 10 questions/hour; flow triggers: 5/hour) and a daily LLM spend cap for the tenant; when hit, the copilot falls back to cached answers.

### 3.2 Seed
A deterministic seed (`services/core` → `python -m igs.seed demo`) creates, with **stable UUIDs** derived from names (UUIDv5), so links in the README and video never rot:
- Catalog: providers, opponents, experiences, knowledge docs (fictional, marked as such).
- 6 leads across sports and states; 4 trips (`proposed`, `confirmed`, `in_progress`, `completed`).
- **The hero execution**: inbound-inquiry for Lakeshore, paused at `ops approval`, with all node runs stored (inputs, outputs, tool calls, timings) — produced once by a real run and **frozen as a fixture**, so the demo never depends on a live LLM to look right.
- 1 pre-departure-check execution waiting on its timer (shows "resumes in 23 days").
- Stored eval run summary and traces for the hero execution.
- Copilot answer cache entry for the pre-filled question.

### 3.3 Reset
- **Nightly at 03:00 ART** (Cloud Scheduler → `POST /v1/admin/demo/reset`, admin-only): truncate tenant-scoped rows for `tenant_demo` (never global catalog of other tenants), terminate the tenant's open Temporal executions, re-run the seed, re-upsert the tenant's vectors (idempotent by content hash, so normally a no-op), warm caches.
- **Per-visitor freshness without a full reset**: approving the hero approval doesn't mutate the shared hero. Each tour session gets its **own clone** of the hero execution (`POST /v1/demo/session` forks the paused execution: new workflow id started from the frozen fixture at the approval node). Two visitors at the same time never see each other's approvals. Clones expire after 2 h and are cleaned up by the nightly reset.
- **Manual reset** button in the admin area and `make demo-reset` for recording the video.
- **Health check before sharing a link**: `GET /v1/demo/health` verifies the hero ids exist, the approval is pending, warm caches are present, eval summary is <24 h old; the landing hides *Start the tour* behind the video link if health fails.

### 3.4 Warm-up
To avoid cold starts on the path: Cloud Run `min-instances=1` for `core-api` while the link is "live" (flipped by the demo/prod mode variable in `docs/architecture/cost-and-scale.md`), Vercel ISR for landing and proposal, the copilot cached answer, and no GPU on the path (query embeddings run on the CPU service; the hero answer is cached anyway).

---

## 4. Video recording notes
- 1440×900 browser window, 100% zoom, light theme for coach surfaces, dark theme for ops (shows both).
- Record against a freshly reset demo tenant with the tour on; edit out any spinner longer than 1 s.
- Captions burned in (English) + Spanish subtitles file; voiceover recorded separately and laid over.
- End card: name, email, repo link, "Built with AI agents — see README".

# Flow editor & execution viewer — UX

Status: design. Implements the model in [`../architecture/flow-engine.md`](../architecture/flow-engine.md) (graph, ports, versioning, CEL, node catalog) and the publish-time controls in [`../architecture/security.md`](../architecture/security.md). Visual language follows [`brand-reference.md`](brand-reference.md). Canvas built on **React Flow** (`@xyflow/react`).

Audience: IGS ops leads who build and tune flows ("builders"), and ops staff who watch executions and decide approvals ("operators"). Builders are not engineers; operators are busy. The editor has to make a wrong flow hard to publish and a failed execution easy to understand.

---

## 1. What we take from n8n and Voiceflow (concepts only)

| Pattern | Source | Keep | How we adapt it |
|---|---|---|---|
| Node details view with **input | config | output** panes side by side | n8n NDV | ✅ | Our config panel shows the node's *resolved input* (left) and *last output* (right) around the form, so CEL references are written against real data. |
| **Pinned data** to avoid re-running expensive nodes while testing | n8n | ✅ | "Pin output" per node on the **draft only** (engine §4). Pinned nodes get a pin badge on canvas and are never part of a published version. |
| **Debug in editor / copy to editor** from a past execution | n8n | ✅ | "Open in editor with this data" loads the execution's node outputs as pins on a new draft. Retry stays on the *same version* (engine §11.6). |
| Executions list with status, trigger, duration, filters | n8n | ✅ | Plus "waiting on" (approval, user message, timer) — our executions are long-lived, n8n's mostly aren't. |
| Blocks grouping steps; start a test **from any block** | Voiceflow | ✅ partially | We don't nest steps in blocks (one node = one thing, simpler mental model and 1:1 with execution records). We keep **"Test from here"** with a synthetic scope. |
| **Test tool**: chat side panel while the canvas highlights the current step | Voiceflow | ✅ | Chat simulator panel for flows with a `chat` trigger (§8). Transcript saved automatically (Voiceflow requires a manual save — we don't). |
| Transcripts review | Voiceflow | ✅ | Every chat execution has its transcript in the execution viewer, linked to node runs. |
| Free-form JavaScript in expressions / Code node | n8n | ❌ | CEL only (engine §6). No code node in v1. |
| Parallel fan-out by drawing many edges from one output | n8n | ❌ | One edge per port (engine §3.1). The canvas refuses the second connection and suggests `map`. |
| Silent stop when a branch isn't connected | n8n | ❌ | Unconnected non-`next` ports render as **red open ports** and block publish (engine §3.1, §13). |
| "Active" toggle that edits the live workflow in place | n8n | ❌ | Draft → publish immutable version; live executions pinned to their version. |
| Global variables set implicitly by any step | Voiceflow | ❌ | Declared `vars` only, written by `set` / `capture` (engine §3.2). |

Sources: n8n docs — [Debug executions](https://docs.n8n.io/build/understand-workflows/understand-executions/debug-executions); [n8n interface guide](https://pro.tecmint.com/n8n-interface-guide/); [How to debug workflows in n8n](https://www.rapidevelopers.com/md/n8n-tutorial/how-to-debug-workflows-in-n8n). Voiceflow docs — [Steps and Blocks](https://docs.voiceflow.com/docs/steps-blocks), [Transcripts](https://docs.voiceflow.com/docs/transcripts), [Manual navigation](https://voiceflow.com/blog/manual-navigation-visuals), [Developer tools](https://docs.voiceflow.com/developer-tools/developer-tools-overview).

---

## 2. Information architecture

```
/ops/flows                         Flow list (name, trigger, published vN, draft changes?, runs 24h, failure rate, waiting)
/ops/flows/new                     Template picker (3 demo flows + blank)
/ops/flows/:id/edit                Editor (draft)            ← §3–§7
/ops/flows/:id/versions            Version history + diff    ← §6
/ops/flows/:id/executions          Executions list (this flow)
/ops/executions                    Executions list (all flows)  ← §9
/ops/executions/:execId            Execution viewer          ← §10
/ops/approvals                     Approvals inbox (shared with the ops panel) ← §11
```

Breadcrumb in the top bar always shows **flow name · Draft / v7 (published)**. The editor never displays a published version as editable: opening a published version is read-only with a "Create draft from v7" button.

---

## 3. Editor layout

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│ ◂ FLOWS / INBOUND INQUIRY   DRAFT · based on v7 · autosaved 12:41   [Validate ●2] [Test ▸] [PUBLISH]│
├────────────┬────────────────────────────────────────────────────────────────┬─────────────────────┤
│ NODES      │                                                                │ NODE · qualify_lead │
│ ⌕ search   │   ┌─────────────┐                                              │ agent · conversation│
│            │   │ ⚡ CHAT       │                                              │─────────────────────│
│ AI         │   │ web, whatsapp│                                              │ [Config][Input][Out]│
│  ◆ Agent   │   └──────┬──────┘                                              │                     │
│  ◆ Extract │          │ next                                                │ Instructions        │
│  ◆ Classify│   ╔══════▼═══════╗        completed  ┌──────────────┐          │ ┌─────────────────┐ │
│  ◆ Search  │   ║ ◆ QUALIFY     ║──────────────────▶│ ▭ create_lead │          │ │You are the IGS…│ │
│ CONVERSE   │   ║ agent · conv  ║                   │ action        │          │ └─────────────────┘ │
│  ◖ Say     │   ║ tools: 3  KB:1║  handoff          └──────┬───────┘          │ Tools  [+]          │
│  ◖ Capture │   ╚═══════╤══════╝─────┐                    │ next              │  ✓ find_opponents R │
│  ◖ Choice  │           │ error     │             ┌──────▼───────┐           │  ✓ search_kb      R │
│ LOGIC      │           ○ (red)     ▼             │ ▭ draft_trip  │           │  ✓ create_lead   W  │
│  ◇ Condition│                ┌────────────┐      └──────┬───────┘           │ Model  default ▾    │
│  ◇ Switch  │                │ ◖ Say       │             │ next               │ Exit output schema ▸│
│  ▭ Set     │                │ "A person…" │      ┌──────▼───────┐           │ Max turns  12       │
│  ⧉ Map     │                └────────────┘      │ ✋ APPROVAL    │           │                     │
│  ⧉ Subflow │                                    │ ops · 24h     │           │ ── Retry & errors ─ │
│  ◷ Wait    │                                    └─┬────┬─────┬─┘           │ onError  fail ▾     │
│  ■ End     │                           approved │ rejected│ expired          │ attempts 3          │
│ INTEGRATE  │                                    ▼    ▼     ▼                 │                     │
│  ▭ Action  │                                  …    …     …                  │ Notes               │
│  ▭ HTTP    │                                                                │                     │
│  ▭ Message │  [−][+][fit] [▦ minimap]  [⌘K]                                 │                     │
│ HUMAN      │                                                                │                     │
│  ✋ Approval│                                                                │                     │
├────────────┴────────────────────────────────────────────────────────────────┴─────────────────────┤
│ ▲ PROBLEMS (2)   ✖ approval_or_external: send_proposal reachable from CHAT without approval — …    │
│                  ⚠ qualify_lead.error port not connected (onError=fail, port unused — OK)          │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Left: palette**, grouped by category, searchable; drag onto canvas or onto an edge (inserts in between, re-wiring `next`). `⌘K` opens the same palette at the cursor.
- **Center: canvas** (React Flow) with minimap, snap-to-grid 8px, auto-layout button (left-to-right dagre/elk layout), multi-select, copy/paste between flows (ids regenerated).
- **Right: node panel** (§5), resizable, collapsible. With nothing selected it shows **Flow settings** (trigger, variables, settings: timeouts, maxSteps, concurrency, dedupe, errorFlow, conversation).
- **Bottom: problems drawer** (§6.1). Clicking a problem selects the node / field.
- **Top bar**: draft status, validation counter, Test, Publish. The Publish button is disabled while there are errors (warnings allowed).

Keyboard: `⌘K` palette, `⌫` delete, `⌘D` duplicate, `⌘Z/⇧⌘Z` undo/redo (local history, survives autosave), `T` test from selected node, `P` pin/unpin output, `⌘↵` run test, `F` fit view.

---

## 4. Canvas language

### 4.1 Node shapes per category

Shape tells *what kind* of node it is; colour is reserved for **state** (selection, validation, execution status). Consistent with the brand's monochrome chrome.

| Category | Types | Shape | Glyph | Notes |
|---|---|---|---|---|
| Trigger | `chat`, `webhook`, `schedule`, `event`, `manual` | Rounded pill, left edge flat, no input handle | ⚡ | Exactly one per flow, always at entry. Shows trigger summary ("cron 0 9 * * 1 · America/Argentina/Buenos_Aires"). |
| AI | `agent`, `extract`, `classify`, `knowledge_search` | Rectangle with **double border** | ◆ | Shows model, tool count with class badges (R/W/X), KB count. Heavier border = "this costs tokens and is non-deterministic". |
| Conversation | `say`, `capture`, `choice` | Rectangle with **speech-bubble notch** bottom-left | ◖ | Shows the first line of text/prompt. Only allowed in chat-triggered flows; otherwise rendered hatched with an error. |
| Logic | `condition`, `switch` | **Diamond-cut corners** (octagon) | ◇ | Shows the CEL expression truncated in mono. |
| Logic (data) | `set` | Small compact rectangle | ▭ | `vars.x ← …` |
| Control | `map`, `subflow` | Rectangle with **stacked shadow** (looks like a deck) | ⧉ | Shows target flow + version (`published → v4 at start`). Double-click opens target flow in a new tab. |
| Time | `wait` | Rectangle with clock notch | ◷ | "30d before trip.startDate". |
| Integration | `action`, `http`, `send_message`, `emit_event` | Plain rectangle, square corners | ▭ | Shows action name; class badge **W** (internal write) or **X** (external/destructive) in the corner. |
| Human | `approval` | Rectangle with **thick left bar** in foreground colour | ✋ | Shows assignees + expiry. The one node that waits on a person; it should stand out. |
| End | `end` | Small circle | ■ | Status (`completed` / `failed`) shown inside. |

Badges on any node: **pin** (has pinned output, draft only), **disabled** (50% opacity + strike), **note** (has notes), **retry** (custom retry policy), class badges **R / W / X**.

### 4.2 Ports (handles)

- Input handle: single, on the left. Output handles: on the right, **one per port name**, stacked and **labelled with the port name** (`next`, `true`/`false`, `completed`/`handoff`, `approved`/`rejected`/`expired`, case ids, class ids, option ids, `no_match`, `timeout`, `default`).
- The `error` port appears **only when `onError = branch`**, at the bottom of the node, red outline.
- Port states: connected (filled), unconnected `next` (hollow, neutral — ends `completed`, engine §3.1), **unconnected non-`next` (hollow red + tooltip "This branch has no destination; the execution will fail with unrouted_port")**.
- One edge per port: dragging from an already-connected port **moves** the edge (with a ghost of the old one) instead of adding a second. Trying to connect a second edge shows a toast: "Each output goes to one place. To run several things in parallel use Map or Subflow."
- Port lists for `switch`, `classify`, `choice` update live when cases/classes/options are edited; removing a case with an edge prompts "Delete the connected branch too?".

### 4.3 Edges

- Smooth-step edges, label = port name when the node has more than one output port (hidden for single-`next` nodes to reduce noise).
- Back edges (cycles, e.g. re-ask) render dashed with a ↺ glyph and the label "loop · maxSteps 200".
- Hover an edge → "+" button to insert a node.
- Edges into conversation nodes from an `interrupt` (`goTo`) render as dotted lines from a small "interrupt" chip in the flow settings column, so interrupts are visible on the canvas.

### 4.4 Visual style (brand)

- Canvas background: `background` (cream `40 7% 95%` light / `0 0% 5%` dark) with a dot grid in `border`.
- Nodes: `card` fill, 1px `border`, radius `.25rem` (brand), title in **Barlow Condensed uppercase, tracking .1em**, body in DM Sans 13px, CEL/JSON in mono.
- Selection: 2px `ring`. Validation error: `destructive` outline. Country accents are **not** used on the canvas (reserved for trip/destination UI).
- Status colours (added for the ops app, AA contrast): success `151 60% 32%`, running `210 50% 45%`, waiting `40 80% 40%`, failed `0 72% 45%`, skipped `0 0% 60%`. Always paired with a glyph (✓ ▶ ⏸ ✖ –) so state isn't colour-only.

---

## 5. Node config panel

### 5.1 Structure

Three tabs, n8n-NDV style but stacked vertically in a side panel (the canvas stays visible, unlike n8n's modal):

```
┌──────────────────────────────── NODE · request_confirmations ─┐
│ ▭ ACTION  request_provider_confirmations      X external  ⋯   │
│ [ Config ]  [ Input ]  [ Output ]  [ Settings ]               │
│───────────────────────────────────────────────────────────────│
│ Trip            {{ trigger.tripId }}                 ▸ preview│
│                 = "trp_8f2c…" (from last test)                │
│ Only statuses   [requested ×] [pending ×] [+]                 │
│ Reply by        {{ execution.now + duration('48h') }}          │
│                 = 2026-10-24T12:41:00Z                        │
│                                                               │
│ ⓘ External action. Needs an approval on every path from       │
│   untrusted triggers. This flow: schedule trigger → OK.       │
└───────────────────────────────────────────────────────────────┘
```

- **Config**: form generated from the node type's JSON Schema in `packages/flow-schema/flow.schema.json` (and, for `action`, from the action registry's input schema). Field widgets by schema: enum → select; `format: duration` → duration input (`48h`, chips); `expression` → CEL editor; template string → text with inline `{{ }}` tokens; nested JSON Schema (agent `output`, `extract.schema`, `approval.form`) → visual schema builder with a "Raw JSON" toggle; `secretRef` → picker of secret *names* (values never shown); `tools[]` → checklist with class badges.
- **Input**: the resolved input of the last test or pinned run (scopes `trigger`, `vars`, `nodes.*`) as a collapsible JSON tree / table toggle. Drag a field from the tree into any expression field to insert its path (n8n's drag-to-map, with CEL paths).
- **Output**: last output of this node from the latest test (or pinned output), JSON/table toggle, **Pin output** / **Edit pinned** / **Unpin**. Agent nodes also show the tool-call sub-timeline and token usage.
- **Settings**: `retry`, `timeout`, `onError` (fail / continue / branch — choosing branch reveals the `error` port on canvas), `disabled`, `notes`.

### 5.2 CEL expression editor

Built on CodeMirror 6 with a CEL grammar (Lezer), the same CEL implementation as the server via WASM/JS (`cel-js`) so the editor and worker agree.

```
Condition  ┌───────────────────────────────────────────────────────────────┐
           │ nodes.qualify_lead.output.groupSize >= 15 &&                  │
           │ vars.destination in ['Argentina', 'Brazil']▌                  │
           └───────────────────────────────────────────────────────────────┘
             ┌─────────────────────────────────────────┐
             │ vars.destination     string  "Argentina"│  ← autocomplete
             │ vars.budgetPerPerson int     2800       │
             │ nodes.qualify_lead.output.…  object     │
             │ trigger.channel      string  "web"      │
             └─────────────────────────────────────────┘
           ▸ Preview (last test data):  true   ✓ bool
```

- **Autocomplete** from the scopes valid *at this node*: `trigger.*` (from trigger `input` schema or last payload), declared `vars.*` with types, `nodes.<id>.output.*` **only for nodes that can run before this one** (graph reachability, engine §13.4), `nodes.<id>.error.*` for upstream nodes with `onError: branch`, `execution.*`, CEL stdlib + engine helpers (`default`, date format).
- **Live preview** under the field: evaluates against the last test / pinned data, shows value + type, or the CEL error inline. For template strings, preview shows the rendered text.
- **Type hint**: fields that must be `bool` (condition, switch case, trigger filter) show "must return bool" and flag non-bool previews.
- Errors: red squiggle with message; unknown scope = error (blocks publish), unknown field = warning (outputs aren't all statically typed, engine §6.2).
- Mode toggle per field: **Fixed** (literal value) vs **Expression** (`{{ }}`), like n8n's fixed/expression switch, so non-engineers can stay in fixed mode.

---

## 6. Validation, versions and publishing

### 6.1 Continuous validation

Validation runs on every change (debounced 300 ms) in two layers:

1. **Client**: JSON Schema (structure), graph checks (ids, ports per type, one edge per port, reachability, dead ends), CEL compile.
2. **Server** (`POST /v1/flows/:id/draft/validate`, also run on publish): references (tools, KBs, actions, secrets, subflows exist for tenant), action input schemas, conversation-node placement, error-flow rules, limits, **security checks** (§6.3).

Problems drawer shows errors (block publish) and warnings (don't), each linked to the node/field. Node badges mirror the counts.

### 6.2 Version history and diff

```
┌ VERSIONS · INBOUND INQUIRY ───────────────────────────────────────────────────────────┐
│ ● Draft      edited 12:41 by Ana     +2 nodes ~3 changed −0      [Open] [Diff vs v7]   │
│ ▲ v7  LIVE   2026-10-20 by Mauricio  "tighter qualification"     1,204 runs  0.8% fail │
│   v6         2026-10-12 by Ana       "add WhatsApp channel"        880 runs  1.1% fail │
│   v5 …                                                         [Publish again as v8]   │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

- **Diff view** (draft vs published, or vN vs vM): canvas side-by-side or overlay with nodes tinted **added / removed / changed**, edges likewise; clicking a changed node shows a field-level JSON diff of its `config`, `retry`, `onError`. A text summary at top: "Added `approval` before `send_proposal`; changed `qualify_lead.instructions` (+4 lines); trigger unchanged."
- Rollback = "Publish again as v8" (history only moves forward, engine §4).
- Per-version stats (runs, failure rate, median duration) come from executions, so a builder sees whether v7 behaves better than v6.

### 6.3 Publish flow

```
┌ PUBLISH INBOUND INQUIRY ───────────────────────────────────────────────┐
│ Draft → v8                                                             │
│ ✓ Structure & graph            ✓ Expressions compile (31)              │
│ ✓ References resolved          ✓ Limits                                │
│ SECURITY                                                               │
│ ✓ No external/destructive tool reachable from CHAT without approval    │
│ ✓ Agent tool allowlists: qualify_lead → R,R,W (no X)                   │
│ ⚠ http node `pricing_api` → host api.example.com is in egress allowlist │
│ CHANGES  +approval_ops  ~qualify_lead.instructions        [View diff]   │
│ IN-FLIGHT  23 executions on v7 keep running on v7.                     │
│ Release note  [ tighter qualification + ops approval            ]      │
│                                              [Cancel]  [PUBLISH v8]    │
└────────────────────────────────────────────────────────────────────────┘
```

Security checks surfaced explicitly (from security.md §3.2 / phase 4):

- **Untrusted-trigger reachability**: for `chat` and `webhook` triggers, every path from entry to a node holding a `write-external`/`destructive` tool or action (`send_message`, `send_proposal`, `request_provider_confirmations`, `set_trip_status(cancelled)`, any agent with an X tool) must pass an `approval` node. Failure is an **error** with the offending path highlighted on canvas in red, plus a quick fix: "Insert approval before `send_proposal`".
- **Agent tool allowlists** listed per agent node with class badges; coach-facing agents (chat trigger) holding W tools beyond `create_lead`/`draft_trip(proposed)` raise a warning.
- **Egress allowlist** for `http` hosts; non-allowlisted host = error.
- **Secrets** only via `secretRef`; a literal that looks like a key (regex, entropy) in any field = error.
- Publishing requires the `flow:publish` role; the publish is audited (who, diff hash, version).
- The dialog states what happens to **in-flight executions** (they stay on their version).

---

## 7. Test runs

### 7.1 Test with sample trigger

`Test ▸` opens a popover:

```
┌ TEST RUN · draft ───────────────────────────────────────────────┐
│ Trigger payload   (●) Sample: "Women's D1, 22 players, BA, Mar" │
│                   ( ) From execution: exec_91a2…  [pick]        │
│                   ( ) Custom JSON  { … }                        │
│ Start from        (●) Entry   ( ) Selected node: draft_trip     │
│ Use pinned outputs  ✓ qualify_lead  ✓ create_lead              │
│ Side effects      (●) Sandbox (actions hit demo tenant, msgs to │
│                       test inbox)  ( ) Dry (stub all writes)    │
│                                                   [Run ⌘↵]       │
└─────────────────────────────────────────────────────────────────┘
```

- Samples per trigger type are saved with the flow (draft-only), seeded from the trigger `input` schema and from real executions ("Use this execution's trigger as sample").
- **Test from selected node** (Voiceflow's "start from any block"): requires the scopes upstream nodes would have produced; the editor pre-fills them from pins / last execution and lists what's missing.
- **Side-effect mode**: *Sandbox* runs against the demo tenant with outbound messages routed to a test inbox; *Dry* stubs every `action`/`http`/`send_message` with schema-valid fake outputs. Test runs never use production channels.
- During the run the **canvas animates**: current node pulses (running), completed nodes get ✓ and their output appears in the panel; the taken edge is highlighted. Approvals in a test run can be decided inline ("Approve as me (test)"). Waits can be **fast-forwarded** ("Skip wait") — maps to Temporal's time skipping in the test environment.
- A test run is a real execution flagged `test=true` on the draft; it appears in the execution viewer (filtered out of stats).

---

## 8. Conversational flow testing (chat simulator)

For flows with a `chat` trigger, the right panel gets a **Chat** tab (Voiceflow test tool equivalent):

```
┌ CHAT SIMULATOR · draft ───────────────── persona: US college coach ▾ ─┐
│ [Restart] [Save as eval case] [Variables ▸]        channel: web ▾      │
│───────────────────────────────────────────────────────────────────────│
│                     Hi! We're a women's D1 soccer team…  ◀ coach       │
│ IGS ▸ Great — how many players and which dates are you considering?    │
│        ↳ qualify_lead · turn 1 · 1.2s · 840 tok                        │
│                     22 players, March 10–20  ◀ coach                   │
│ IGS ▸ Perfect. Buenos Aires in March is ideal… [3 opponents found]     │
│        ↳ qualify_lead · tool find_opponents (R) · 2 hits               │
│ ── waiting: approval_ops (ops) ── [Approve as me] [Reject]             │
│───────────────────────────────────────────────────────────────────────│
│ [ Type as the coach…                                    ] [Send]       │
│ Interrupts:  "talk to a human" → handoff  [Try]                        │
└───────────────────────────────────────────────────────────────────────┘
```

- Each bot message links to the **node run** that produced it (click → canvas selects the node, panel shows input/output). The canvas highlights the waiting node (`capture`, `choice`, conversation `agent`, `approval`).
- Turn buffering is shown as the user sees it (engine §9): one coherent reply per turn, with an expandable list of the `say` / agent outputs that composed it.
- **Variables** drawer shows `vars` updating live (slot filling from `capture.extract`).
- **Persona auto-play** (optional): an LLM-simulated coach from the evals persona library plays the user turn by turn, so builders see a whole conversation in seconds. Same personas as `evals/` (see evals-and-testing.md).
- **Save as eval case**: stores transcript + expected outcome (lead created, trip drafted, approval requested) as a regression case for the flow. This closes the loop between building and evals.
- Transcripts are saved automatically with the test execution (no manual save).

---

## 9. Executions list

```
┌ EXECUTIONS ───────────────────── flow: All ▾  status: All ▾  version: All ▾  trigger ▾  ⌕ lead/trip/conv ─┐
│ STATUS        FLOW              VER  TRIGGER         STARTED        DURATION  WAITING ON          COST     │
│ ⏸ waiting     Inbound inquiry   v7   chat · web      12:02          39m       Approval · ops (2h) $0.04    │
│ ✖ failed      Pre-departure     v3   schedule        09:00          4.1s      —                   $0.00    │
│                ↳ request_confirmations · upstream (503) · 3 attempts       [Retry from node] [Open]       │
│ ✓ completed   Post-match report v2   event trip_item 08:47          22s       —                   $0.02    │
│ ▶ running     Inbound inquiry   v7   chat · whatsapp 12:40          1m        user message        $0.01    │
│ ◷ sleeping    Pre-departure     v3   event trip      Oct 01         21d       timer → Nov 12      $0.00    │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- Status set: running, waiting (user message / approval), sleeping (timer), completed, failed, cancelled. **"Waiting on"** column is the key operational column for long-lived flows.
- Filters: flow, version, status, trigger, date range, test runs (hidden by default), and **search by business entity** (lead, trip, conversation, coach email) — ops think in trips, not execution ids.
- Failed rows expand inline to show the failing node, error class (engine §11.1), attempts, and quick actions.
- Live updates via SSE; counts per status in the header chips.

---

## 10. Execution viewer

### 10.1 Layout

```
┌ EXECUTION exec_7d1… · INBOUND INQUIRY v7 · ⏸ WAITING — approval "Send proposal to Lakeshore?" ───────┐
│ Trigger chat·web · lead Lakeshore · trip trp_8f2c · started 12:02 · 39m · $0.04  [Cancel] [Open in editor]│
├──────────────────────────────────────────────────────────────┬────────────────────────────────────────────┤
│                                                              │ NODE RUN · draft_trip  ✓ 2.4s  attempt 1/3  │
│   ⚡ chat ✓ ──▶ ◆ qualify_lead ✓ ×6 turns ──▶ ▭ create_lead ✓ │ [Input] [Output] [Error] [Logs] [Trace ↗]   │
│                         │                        │           │ Input                                       │
│                    handoff (–)                   ▼           │  leadId: "lead_31f…"                        │
│                                           ▭ draft_trip ✓ ◀── │ Output                                      │
│                                                  │           │  { id: "trp_8f2c", title: "Lakeshore…", │
│                                                  ▼           │    items: [14], pricePerPersonUsd: 2840 … } │
│                                           ✋ approval_ops ⏸   │  [Table] [JSON] [Copy] [Open trip ↗]        │
│                                        approved│rejected│exp │ Idempotency key exec_7d1:draft_trip:0       │
│                                                ▼  (–)  (–)   │                                             │
│                                           ▭ send_proposal –  │                                             │
├──────────────────────────────────────────────────────────────┴────────────────────────────────────────────┤
│ TIMELINE   12:02 ─────────────────────────────── 12:41                                                     │
│ chat          ▏                                                                                            │
│ qualify_lead  ▕████ turn1 ▕██ t2 ··· waiting user ··· ▕██ t6                                             │
│ create_lead                                                   ▏▌0.3s                                      │
│ draft_trip                                                     ▕██ 2.4s                                    │
│ approval_ops                                                        ▕········ waiting 37m ···········▶    │
│ [Transcript (12 msgs)]  [Variables]  [Events]  [Audit]                                                     │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **Graph overlay**: the published graph of the pinned version (read-only) with per-node status glyph + colour (✓ completed, ▶ running, ⏸ waiting, ✖ failed, – not reached/skipped), iteration count for nodes run more than once (`×6 turns`, loops, map items), the **taken path** drawn solid and untaken branches faded.
- **Node run inspector** (right): tabs Input / Output / Error / Logs / Trace. Agent nodes add **Tool calls** (sub-timeline: tool, class, args, result, ms) and **Usage** (tokens, cost, model). Map/subflow nodes link to child executions. Values over 256 KB load lazily from GCS (engine §8). Sensitive vars render masked (`••••`, reveal requires role, audited).
- **Timeline** (bottom): Gantt of node runs, including retries as separate segments and waits as dotted spans, so "where did the time go" is obvious. Click a segment → selects the node run.
- **Transcript** tab for chat executions: messages with links to the node runs that produced them (same as the simulator).
- **Variables** tab: `vars` snapshot after each node run (scrub with the timeline).
- **Events/Audit** tabs: signals received (user_message, approval_decision, cancel), continue-as-new boundaries, audit records of tool calls.
- **Trace ↗** deep-links to the OpenTelemetry trace (observability.md).

### 10.2 Failed execution and retry from node

```
│ ✖ FAILED at request_confirmations · upstream · "provider API 503" · 3/3 attempts                         │
│   [Retry from request_confirmations]  [Retry from …▾]  [Open in editor with this data]  [View error flow ↗]│
```

- **Retry from node X** starts a new execution on the **same version**, replaying completed node runs before X as pinned outputs (no repeated side effects, engine §11.6). The confirm dialog lists which nodes will be replayed vs re-run, and warns when X is downstream of an external action already performed.
- Retrying on a newer version is not offered (deliberate, engine §11.6); "Open in editor with this data" is the path to fix the flow and test with the same inputs.
- The error-flow execution (e.g. `notify-ops-on-failure`) is linked.

### 10.3 Pending approvals inside an execution

When the execution waits on an `approval`, a banner at the top shows the approval card inline (same component as the inbox, §11), so an operator who arrives from an alert can decide without switching screens.

---

## 11. Approvals (shared with the ops panel)

```
┌ APPROVAL · Send proposal to Lakeshore University? ───────── expires in 22h ─┐
│ Requested by flow Inbound inquiry v7 · exec_7d1 · node approval_ops           │
│ ACTION THAT WILL RUN                                                           │
│   send_proposal { tripId: trp_8f2c, to: coach@stfrancis.edu, note: "…" }       │
│   payload hash 9c1e… (decision is bound to this exact payload)                 │
│ CONTEXT  Trip: Buenos Aires · Mar 10–20 · 22 players · $2,840 pp  [Open trip]  │
│          Opponents: Deportivo Belgrano Femenino (7) · …                         │
│ Form     Discount approved?  ( ) No  ( ) 5%                                     │
│ Comment  [                                             ]                        │
│                               [Reject]  [Approve]                               │
└────────────────────────────────────────────────────────────────────────────────┘
```

- Shows **the exact action and payload** that will execute and the payload hash (security.md: approval bound to payload hash + approver; payload change ⇒ re-approval).
- First-writer-wins: if someone else decided, the card flips to read-only with who/when (API returns 409).
- Expiry countdown; `remindEvery` notifications link here.
- Decisions are also possible via MCP `decide_approval`; the card shows "decided via MCP by <user>".
- To fight approval fatigue: no button has default focus, and Approve is only enabled once the action/context section has been rendered on screen (no blind approve from the list view).

---

## 12. Empty, loading and error states

| Where | State | Treatment |
|---|---|---|
| Flow list | No flows | Three template cards (Inbound inquiry, Pre-departure check, Post-match report) + "Blank flow". |
| Editor | New blank flow | Canvas with a single "Choose a trigger" placeholder node; palette highlights Triggers. |
| Node panel | No test data yet | Input/Output tabs show "Run a test to see real data here — or pin sample output" with a button. |
| Expression preview | No data | "No test data — preview unavailable", type check still runs. |
| Execution viewer | Version graph missing (deleted flow) | Read-only render from the version snapshot (snapshots are immutable, always available). |
| Publish | Server validation unreachable | Publish disabled with retry; never publish on client-only validation. |
| Canvas | > 200 nodes | Limit message per engine §14; suggests extracting a subflow. |

---

## 13. Accessibility & responsiveness

- Canvas is keyboard navigable: Tab cycles nodes in topological order, arrow keys move between connected nodes, `Enter` opens the panel; every node has an accessible name ("Agent node qualify_lead, conversation mode, 2 output ports: completed connected, handoff connected").
- Status always glyph + text, never colour only; contrast AA in light and dark.
- The editor is **desktop-only** (≥ 1280px); on tablet/phone `/ops/flows/:id/edit` opens read-only canvas with a notice. Executions list, execution viewer (stacked layout) and approvals **work on mobile** — operators approve from their phone.
- Respect `prefers-reduced-motion`: no pulsing nodes, no edge animations during test runs.

---

## 14. Implementation notes (React Flow)

- Custom node components per category (`AgentNode`, `ConversationNode`, `LogicNode`, `ActionNode`, `ApprovalNode`, `TriggerNode`, `EndNode`) with dynamic `Handle`s generated from the node type's port list (a shared `portsFor(node)` function used by the canvas **and** the validator, generated from `flow.schema.json` + node catalog so ports can't drift).
- `isValidConnection` enforces one edge per source port and forbids edges into triggers; ports lists drive handle ids (`sourceHandle = port name`).
- Graph state: the flow definition JSON is the single source of truth; React Flow nodes/edges are a projection (positions stored in `node.position`). Autosave PATCHes the draft with optimistic concurrency (`If-Match` draft revision) — two builders editing the same draft get a conflict banner rather than silent overwrite.
- Auto-layout: ELK (layered, left-to-right) on demand, never automatically on every change.
- Execution overlay reuses the same node components with a `runState` prop; data from `GET /v1/executions/:id` + `/node-runs`, live via SSE.
- Large flows: React Flow `onlyRenderVisibleElements`, memoized node components, minimap.
- CEL: CodeMirror 6 + Lezer CEL grammar; evaluation/preview with the JS CEL implementation; the server remains the authority at publish.

---

## 15. Open questions

1. **Node grouping / sticky notes**: n8n has sticky notes, Voiceflow has blocks. Add "frames" (visual groups with a title, no semantics) in v1 for readability of the 30-node demo flows? Proposed: yes, cheap.
2. **Multi-user editing**: optimistic lock + conflict banner in v1; real-time co-editing (CRDT) out of scope.
3. **Agent node prompt editing**: inline in panel vs a full-screen prompt editor with versioned prompt diffs and eval results side by side. Proposed: full-screen editor reachable from the panel, since prompt changes are the most frequent edit.
4. **Approvals default focus** and bulk approval: deliberately no bulk approve in v1 (approval fatigue). Confirm with ops.
5. **Staging per flow** (engine §18.5): if added, the publish dialog gets a "Publish to staging" step and the executions list a channel filter.

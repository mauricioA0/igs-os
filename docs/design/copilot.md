# Ops Copilot — UX

The copilot is how the ops team talks to IGS OS. It lives in a **side panel** (always one keystroke away) and a **command palette** (`⌘K` / `Ctrl K`). It uses **exactly the same tool registry as the MCP server** (`docs/architecture/core-api.md` §5), so what an ops person can do from the panel is what they can do from Claude Code or Claude Desktop, with the same classes, approvals and audit trail.

Visual language follows `docs/design/brand-reference.md`: monochrome chrome, Barlow Condensed uppercase eyebrows, DM Sans for UI text, `.25rem` radius, dark mode first-class. Ops copy is in **Spanish**. Coach-facing copy stays in English and is out of scope here.

> LLM provider: the copilot is provider-agnostic. It runs on whatever model the agent runtime is configured with (OpenAI per the current decision). Nothing in this UX depends on a specific vendor.

---

## 1. Principles

| # | Principle | What it means in the UI |
|---|---|---|
| 1 | **Friction matches risk** | `read` tools run silently. `write-internal` runs inline with a receipt and undo. `write-external` / `destructive` always stops at an approval card. No popups for low-stakes work. |
| 2 | **Show the plan, then the work** | Multi-step requests start with a short, editable plan. Every tool call streams as a visible step. |
| 3 | **Never a silent write** | Every state change shows *what changed, where, by whom (copilot on behalf of X)*, with a link to the audit entry. |
| 4 | **Grounded or it says so** | Answers from documents carry citations. With no source, the copilot says "no encontré esto en la base" instead of guessing. |
| 5 | **Context is explicit** | The copilot always shows what it is looking at (trip, lead, flow, execution) as removable chips. No hidden context. |
| 6 | **Same powers everywhere** | Panel, `⌘K` and MCP clients share tools, classes, scopes and approvals. The server enforces them; the UI only reflects them. |
| 7 | **Turn repetition into automation** | Anything done twice by hand can become a flow ("Convertir en flow"). |

These follow the current agentic-UX consensus: risk-tiered gates, a visible autonomy setting, plan-before-act, streaming state, receipts/logs/rollback ([Agentic Wire checklist](https://www.agenticwire.news/article/agent-ux-design-patterns), [HatchWorks](https://hatchworks.com/blog/ai-agents/agent-ux-patterns/), [Towards AI](https://pub.towardsai.net/designing-for-ai-agents-8-ux-patterns-that-build-trust-in-2026-713a0c926933)). They also avoid the binary "Approve / Reject everything" modal, which trains rubber-stamping ([Ganglani, HITL tool approval patterns](https://www.kunalganglani.com/blog/tool-approval-patterns-ai-agents)).

---

## 2. Surfaces

### 2.1 Side panel (primary)

Docked right, 400px, resizable, collapsible to a 48px rail. Opens with `⌘J` or the rail icon. It persists across navigation; the conversation keeps its thread but the **context chips update** with the current screen.

```
┌──────────────────────────────────────────────── IGS OS ─────────┬─────────────────────────────────┐
│ VIAJES / SAINT FRANCIS · BUENOS AIRES · 12–22 MAR               │ COPILOTO                    ⤢ ✕ │
│                                                                 │─────────────────────────────────│
│  DÍA 3 · MAR 14                                                 │ Contexto:                       │
│  ┌──────────────────────────────────────────────────────┐       │ [Viaje: Lakeshore ✕]        │
│  │ MAÑANA   Entrenamiento AFA        ● confirmado        │       │ [Día 3 ✕]   + agregar           │
│  │ TARDE    vs Deportivo Belgrano F. ◐ solicitado        │       │─────────────────────────────────│
│  │ NOCHE    Tango & asado            ○ pendiente         │       │ Tú                              │
│  └──────────────────────────────────────────────────────┘       │ ¿Qué proveedores faltan         │
│                                                                 │ confirmar?                      │
│                                                                 │                                 │
│                                                                 │ Copiloto                        │
│                                                                 │ ▸ list_unconfirmed_items  0.4s ✓│
│                                                                 │ Faltan 3 de 14 ítems:           │
│                                                                 │ • Bus Río de la Plata (día 1–10)│
│                                                                 │ • Tango & asado (día 3)         │
│                                                                 │ • Árbitros AFA (día 5)          │
│                                                                 │                                 │
│                                                                 │ [Pedir confirmaciones →]        │
│                                                                 │─────────────────────────────────│
│                                                                 │ Sugerencias                     │
│                                                                 │ › ¿Qué dice el contrato del bus │
│                                                                 │   sobre cancelaciones?          │
│                                                                 │ › Cambiá el rival del día 5     │
│                                                                 │─────────────────────────────────│
│                                                                 │ Escribí o usá / para comandos ⏎ │
│                                                                 │ Autonomía: [Preguntar antes ▾]  │
└─────────────────────────────────────────────────────────────────┴─────────────────────────────────┘
```

### 2.2 Command palette `⌘K`

For fast, single-intent actions and navigation. It mixes three result types: **navigate** (go to a trip), **ask** (opens the answer in the side panel) and **do** (a tool, which follows the same class rules).

```
┌───────────────────────────────────────────────────────────────┐
│ ⌘K  pedir confirmaci                                         │
├───────────────────────────────────────────────────────────────┤
│ ACCIONES                                                      │
│ ⚡ Pedir confirmaciones pendientes · Lakeshore   [externa]│
│ ⚡ Marcar ítem como solicitado                       [interna]│
│ PREGUNTAR AL COPILOTO                                         │
│ 💬 "pedir confirmaci…" → abrir en el panel                    │
│ IR A                                                          │
│ → Viaje Lakeshore · BA · 12 mar                           │
│ → Flow "Control pre-salida"                                   │
└───────────────────────────────────────────────────────────────┘
 ↑↓ navegar  ⏎ ejecutar  ⇥ abrir en panel  esc cerrar
```

The class badge (`[lectura]`, `[interna]`, `[externa]`) is visible **before** the action runs. Running an `[externa]` action from `⌘K` never executes it directly; it opens the approval card in the panel.

---

## 3. Context awareness

- **Automatic chips** from the current route: `Viaje`, `Día`, `Ítem`, `Lead`, `Flow`, `Ejecución`, `Aprobación`. Selecting rows in a table adds a multi-chip ("3 ítems seleccionados").
- **Removable and addable.** `+ agregar` opens a picker (trips, leads, flows, documents). The user decides what the copilot sees.
- **Context is sent as references, not dumps.** Chips become IDs in the system context and the agent fetches details through `read` tools. Those fetches show up as steps, so the user sees what was actually read.
- **Stale context warning.** If the trip changed since the last answer (another user confirmed an item), a banner appears: "El viaje cambió desde la última respuesta · Actualizar".
- **Tenant is never a chip.** It comes from the session and is enforced server-side (security.md §tenant isolation).

---

## 4. Tool-call transparency

Each turn renders as a **step list** that streams while the agent works.

```
Copiloto
┌─ Plan ──────────────────────────────────────────── editar ─┐
│ 1. Buscar ítems sin confirmar del viaje                     │
│ 2. Revisar contrato del bus (política de cancelación)       │
│ 3. Proponer pedido de confirmación a 3 proveedores          │
└─────────────────────────────────── [Seguir] [Cancelar] ────┘

▸ list_unconfirmed_items  trip=Lakeshore            0.4s ✓
▾ search_knowledge  "bus cancelación Río de la Plata"   1.1s ✓
    3 fragmentos · 2 documentos
▸ request_provider_confirmations                        ⏸ esperando aprobación
```

- **Plan first** for requests that need 3+ tool calls or any write. The plan is editable: delete a step, reorder, add a note. Single reads skip the plan.
- **Collapsed by default, one click to expand.** Expanding shows the tool name, the input (rendered as a readable form, raw JSON on toggle), the output summary and the duration.
- **States:** `…` running, `✓` ok, `⚠` partial or retried, `✕` failed, `⏸` waiting for approval, `↺` undone.
- **Stop button** while streaming (`esc` too). Stopping cancels pending reads; writes already done stay done and are listed with undo.
- **Plain-language labels** next to tool names for non-technical ops ("Buscando en contratos y políticas").
- **Every step links to the trace** (`/ops/traces/{run_id}#step-n`) for whoever wants to audit cost and latency.

---

## 5. Citations and source previews

Answers grounded in RAG carry inline numbered citations. Hovering or tapping one opens a preview.

```
El contrato permite cancelar sin cargo hasta 30 días antes [1].
Entre 30 y 7 días se cobra el 50% [1]; con menos de 7 días, el 100% [2].

┌ [1] Contrato Transportes Río de la Plata 2026.pdf · p. 4 ──────────┐
│ "…la cancelación con una antelación mayor a treinta (30) días      │
│  corridos no generará cargo alguno. Entre treinta (30) y siete (7) │
│  días se facturará el cincuenta por ciento (50%)…"                 │
│ Fuente: proveedor · vigente hasta 31/12/2026 · subido por Lucía    │
│                                      [Abrir documento] [Copiar]    │
└────────────────────────────────────────────────────────────────────┘
```

- The quoted passage is the **exact retrieved chunk** with the matching sentence highlighted, never a paraphrase.
- **Provenance badges:** `política IGS` (trusted), `proveedor` (external), `giras pasadas`, `guía de destino`. External sources get a subtle outline, because they are untrusted input (security.md: spotlighting).
- **Freshness:** `valid_until` shown; expired documents get a `vencido` badge and a softer answer ("según un contrato vencido…").
- **No source, no claim.** If retrieval returns nothing above threshold: "No encontré esto en los documentos cargados. ¿Querés que lo busque en otro lado o lo cargues?" plus a `Subir documento` action.
- A **"Ver todas las fuentes (5)"** drawer lists every retrieved chunk, including ones not cited, for audit.

---

## 6. Write actions: proposals and approvals

Behavior follows the tool classes in `docs/architecture/security.md`:

| Class | Examples | Copilot behavior |
|---|---|---|
| `read` | `get_trip`, `search_knowledge`, `list_pending_approvals` | Runs immediately, shown as a step |
| `write-internal` | `create_lead`, `draft_trip`, `update_trip_item` (notes, `requested`), `swap_opponent` on non-confirmed trips | Runs **after inline confirmation** at autonomy level "Preguntar antes"; directly at "Autónomo interno". Always produces a **receipt with undo** |
| `write-external` / `destructive` | `send_proposal`, `request_provider_confirmations`, `cancel_trip_item`, `set_trip_status(confirmed/cancelled)`, `swap_opponent` on confirmed trips | **Always** an approval card. No autonomy level skips it |

### 6.1 Approval card

The card describes the **exact action** with a preview of the outcome, not just the tool call. It is bound to a payload hash (security.md): if anything is edited, it becomes a new approval.

```
┌ APROBACIÓN REQUERIDA · externa ─────────────────────────────────────┐
│ Pedir confirmación a 3 proveedores · Lakeshore (12–22 mar)      │
│                                                                     │
│  Para                         Ítems                 Canal            │
│  Transportes Río de la Plata  Bus días 1–10         email           │
│  Tango & Fútbol Guides        Tango & asado día 3   email           │
│  Árbitros AFA Certificados    Partido día 5         WhatsApp        │
│                                                                     │
│  ▸ Ver mensaje (ES)                                                  │
│                                                                     │
│  Efectos: 3 mensajes salen de IGS · ítems pasan a "solicitado"      │
│  Reversible: no (los mensajes no se pueden retirar)                 │
│                                                                     │
│  [Editar]        [Rechazar]        [Aprobar y enviar]               │
│  Solicitado por: Copiloto en nombre de Lucía · hace 5 s             │
└─────────────────────────────────────────────────────────────────────┘
```

- **Effects and reversibility are stated** in plain language.
- **Edit** opens the payload as a form (recipients, message, items). Saving creates a new card.
- **Approver identity:** the person approving can be different from who asked (e.g. a junior ops asks, a lead approves). The card can be **sent to the approvals inbox** (`Mandar a aprobación`) instead of approved inline, if the user lacks `approvals:decide`.
- **Batch, but not rubber-stamp.** Multiple related actions collapse into one card with a per-row checkbox. There is no global "approve all pending" button.
- **Expiry:** cards expire with the agent turn (default 24h) and show `vencida`. Approving an expired card re-checks the state first ("El ítem ya fue confirmado por otra persona").

### 6.2 Autonomy setting

Visible at the bottom of the panel, per user, defaulting to the safest level.

| Level | `read` | `write-internal` | `write-external` |
|---|---|---|---|
| **Sugerir** | runs | proposes only (button to apply) | approval card |
| **Preguntar antes** (default) | runs | inline confirm | approval card |
| **Autónomo interno** | runs | runs + receipt + undo | approval card |

There is no level that auto-approves external actions. That is a server rule, not a UI preference.

---

## 7. Receipts, undo and audit trail

Every write produces a **receipt** in the conversation:

```
✓ Rival del día 5 cambiado
  Deportivo Belgrano Femenino → Escuela de Fútbol Femenino Sur
  por Copiloto en nombre de Lucía · 14:32       [Deshacer] [Ver en auditoría]
```

- **Undo** for `write-internal` actions is available for 10 minutes, or until a dependent action happens (e.g. a confirmation was already requested for that item). Undo is itself a logged write (`reverted_by`).
- **External actions have no undo.** Their receipt offers a **compensating action** instead ("Enviar corrección a los proveedores").
- **Audit view** (`/ops/auditoria`) is append-only (security.md: audit log). Filters: actor (person / copilot-on-behalf-of / flow / MCP client), tool class, trip. Each row links to the conversation turn, the trace and the approval.
- **"Qué hizo el copiloto hoy"**: a daily digest in the panel header (N lecturas, N cambios internos, N aprobaciones pedidas).

---

## 8. Uncertainty and errors

| Situation | UX |
|---|---|
| Ambiguous request ("cambiá el rival") with several matches | Ask one clarifying question with options as buttons ("¿Día 5 o día 8?"), never guess on writes |
| Low retrieval confidence | Answer with a hedged phrase plus citations, and an `Esto no responde mi pregunta` button that logs a retrieval miss (feeds the eval golden set) |
| Tool error, retryable | Step shows `⚠ reintentando (2/3)`; the user can see it and doesn't need to act |
| Tool error, final | Step `✕` with a human message ("El proveedor no tiene email cargado"), a fix action (`Cargar email`) and `Reintentar` |
| Permission denied (scope) | "No tenés permiso para esto. Podés pedirlo a aprobación." + `Mandar a aprobación` |
| Conflicting state | "Mientras preparaba esto, Martín confirmó el ítem. Actualicé el plan." with a diff |
| Model refusal or out-of-scope request | Short, neutral message plus what it *can* do; nothing silent |
| Long-running work (> 20 s) | The turn becomes a background task with a progress row; the user can keep working and gets a notification |
| Prompt injection detected in a source | The source chip shows `contenido sospechoso`; the answer excludes it and says so |

The copilot never invents IDs, prices or policies. Prices come only from `get_quote`; policies only from `search_knowledge` with citations.

---

## 9. Suggested prompts per screen (Spanish)

Shown as 2–3 chips under the input, rotating by context. They are real prompts the evals also use.

| Screen | Suggestions |
|---|---|
| **Resumen** `/ops` | "¿Qué salidas hay en los próximos 30 días y qué les falta?" · "Resumime las aprobaciones pendientes" · "¿Qué leads nuevos entraron esta semana?" |
| **Leads** | "¿Cuáles leads no tienen propuesta todavía?" · "Armá una propuesta para este lead" · "¿Este equipo encaja mejor con Buenos Aires o Río?" |
| **Viaje** | "¿Qué proveedores faltan confirmar?" · "Cambiá el rival del día 5 por uno de nivel parecido" · "¿Qué dice el contrato del hotel sobre late check-out?" · "Calculá cuánto sube el precio si agregamos el tour a Tigre" |
| **Ítem de viaje** | "Pedile confirmación a este proveedor" · "¿Qué alternativas hay si cancela?" |
| **Flows** | "¿Qué flows fallaron hoy y por qué?" · "Creá un flow que avise a ops si un proveedor no confirma en 48 h" |
| **Ejecución** | "Explicame por qué falló este nodo" · "Reintentá desde el nodo que falló" |
| **Aprobaciones** | "¿Qué aprobaciones vencen hoy?" · "Mostrame qué cambia si apruebo esta" |
| **Documentos** | "¿Qué contratos vencen este año?" · "¿Hay contradicciones entre la política de cancelación y los contratos?" |

---

## 10. "Convertir en flow": from conversation to automation

When the user has done a multi-step task in the copilot, the turn footer offers **Convertir en flow**. It is also suggested proactively when the same tool sequence repeats (e.g. third time this week someone asks "¿qué falta confirmar?" then requests confirmations).

Steps:
1. **Extract.** The copilot turns the executed steps into a draft flow graph (flow-engine.md): the tool calls become action nodes, the user's approvals become `approval` nodes, literal values (trip ID, "48 h") become **parameters** the user names.
2. **Pick a trigger.** "¿Cuándo debería correr?" with options: manual, schedule (`cron`), an event (`trip.departure_in(30d)`, `trip_item.status_changed`), or webhook.
3. **Review in the editor.** The draft opens in the flow editor as a **draft**, never published. The diff panel shows "Del chat: 4 nodos · 1 aprobación · 2 parámetros".
4. **Safety check runs** before publish (security.md): any `write-external` node reachable from an untrusted trigger without an `approval` is flagged and blocks publishing.
5. **Test run** against the current trip, in dry-run mode (writes simulated), then **Publicar**.

```
┌ CONVERTIR EN FLOW ───────────────────────────────────────────┐
│ Detecté estos pasos:                                          │
│  1. list_unconfirmed_items   (viaje = parámetro "viaje")      │
│  2. request_provider_confirmations  → requiere aprobación     │
│  3. esperar 48 h                     (inferido de tu pedido)  │
│  4. escalar a ops si sigue pendiente                          │
│                                                               │
│ ¿Cuándo debería correr?                                       │
│  ( ) A mano    (•) 30 días antes de cada salida    ( ) Cron   │
│                                                               │
│ [Cancelar]                       [Abrir borrador en el editor]│
└───────────────────────────────────────────────────────────────┘
```

---

## 11. The same interaction from Claude Code / Claude Desktop (MCP)

An ops person or engineer can run the same work from any MCP client connected to `/api/mcp` (`docs/MCP.md`). The server is the single source of truth, so the guarantees hold there too:

| Concern | In the panel | In an MCP client |
|---|---|---|
| Tools | Registry, filtered by role | Same registry, filtered by token scopes (`read`, `write`, `flows:run`, `approvals:decide`) |
| Risk signal | Class badge | MCP annotations: `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`. Clients use them to prompt before risky calls ([MCP tool annotations](https://www.promptlayer.com/glossary/mcp-tool-annotation), [Outreach MCP docs](https://developers.outreach.io/mcp-server/tool-annotations)) |
| Approval | Approval card | A gated tool **does not perform the change**; it returns `approval_required` with the approval ID and a link to the card in IGS OS. Where the client supports elicitation, the server can ask for confirmation inline; if the client can't put the question to a human, nothing happens ([elicitation recipe](https://django-stateless-mcp.readthedocs.io/en/stable/recipes/elicitation-forms-and-confirmations/)) |
| Deciding approvals | Inbox / card | `decide_approval` only with `approvals:decide`; by default MCP keys can't approve, so a human decides in the panel |
| Citations | Inline + preview | `search_knowledge` returns passages with `doc_id`, page and a deep link the client can show |
| Audit | Same log | Actor recorded as `mcp:<client>` on behalf of the token owner |

Example in Claude Code:

```
> ¿qué falta confirmar para Lakeshore? y pedí las confirmaciones

● igs-os - list_unconfirmed_items (trip: "Lakeshore")  [read]
  ⎿ 3 items pending: bus (days 1–10), tango & asado (day 3), referees (day 5)

● igs-os - request_provider_confirmations (trip_id: "…")   [openWorld]
  ⎿ approval_required · id apr_7f3 · https://igs-os.app/ops/aprobaciones/apr_7f3
    "3 messages to providers need approval in IGS OS before they are sent."

Pedí la aprobación. Cuando alguien la apruebe en IGS OS, los 3 proveedores reciben el pedido.
```

The point for the demo: the panel copilot and Claude Code are **two clients of one operating system**, not two features.

---

## 12. Keyboard and accessibility

- `⌘K` palette · `⌘J` toggle panel · `⌘⏎` send · `esc` stop/close · `⌘.` toggle step details · `⌘⇧A` jump to pending approval.
- The panel is an `aside` with `aria-live="polite"` for streamed text and `aria-live="assertive"` only for approval cards and errors.
- Step states use icon + text, never color alone. Status colors from the brand reference meet WCAG AA in both themes.
- Approval buttons are not adjacent-identical: **Rechazar** is outlined on the left, **Aprobar** is primary on the right, with a 1-second guard against double-click on external approvals.

---

## 13. What the demo shows (2 minutes)

1. On a trip page, ask "¿Qué proveedores faltan confirmar?" → steps stream, answer with 3 items.
2. "¿Qué dice el contrato del bus si cancelan?" → cited answer with source preview.
3. "Pediles confirmación" → approval card with the exact messages → approve → receipts.
4. "Convertir en flow" → draft "30 días antes de cada salida" opens in the editor.
5. Same question from Claude Code over MCP → `approval_required` with the link back to IGS OS.

---

## Sources

- [Agent UX Design Patterns: A 2026 Checklist for Human-Agent UI](https://www.agenticwire.news/article/agent-ux-design-patterns)
- [HatchWorks — Agent UX patterns](https://hatchworks.com/blog/ai-agents/agent-ux-patterns/)
- [Towards AI — 8 UX patterns that build trust in 2026](https://pub.towardsai.net/designing-for-ai-agents-8-ux-patterns-that-build-trust-in-2026-713a0c926933)
- [Ganglani — 10 HITL tool approval patterns for AI agents](https://www.kunalganglani.com/blog/tool-approval-patterns-ai-agents)
- [Onething — Agentic AI UX design](https://www.onething.design/post/agentic-ai-ux-design)
- [21TORR — From UX to AX](https://www.21torr.com/en/blog/artikel/from-ux-to-ax-agentic-ux-design-shift)
- [PromptLayer — MCP tool annotations](https://www.promptlayer.com/glossary/mcp-tool-annotation)
- [Outreach — MCP tool annotations](https://developers.outreach.io/mcp-server/tool-annotations)
- [django-stateless-mcp — Elicitation forms and confirmations](https://django-stateless-mcp.readthedocs.io/en/stable/recipes/elicitation-forms-and-confirmations/)

Secondary sources (blogs, vendor docs); the MCP elicitation details should be checked against the official spec before implementation.

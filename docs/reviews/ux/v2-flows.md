# UX review V2 — Flow editor and execution viewer

Reviewer: V2 (workflow-builder specialist). Reviewed the clickable prototype (`/flows`, `/flows/inbound-inquiry`, `/flows/inbound-inquiry/executions/ex-7f3a`, `/flows/pre-departure-check/executions/ex-2b10`) at 1440×900 on 2026-10-22, against `docs/design/flow-editor.md` and current patterns in n8n, Voiceflow, Zapier, Make, Temporal UI and Retool Workflows.

Primary user under test: **Lucía, ops coordinator in Buenos Aires** — not a developer. She runs tours, knows the business rules, and will edit flows a few times a month. Secondary user: Mauricio-as-builder.

## 1. What works

- **Flows list** gives a good health read at a glance: version, draft state, 7-day runs and failures, and the 3 latest executions with status. Category chips ("5 Conversation · 1 AI · 1 Human") tell you what kind of flow it is without opening it.
- **Draft vs published** is explicit in the editor header ("v7 published", "Draft · 2 unpublished changes", "Publish v8"). That beats n8n's single mutable workflow and matches Voiceflow's publish model.
- **Execution viewer** fundamentals are right: status legend, path taken highlighted and unreached nodes dimmed, "pinned to v7", the waiting reason in the header ("Waiting for ops approval · Lakeshore University"), and **Approve / Reject next to the execution**. Error edges are visibly different (red dashed).
- Approval expiry and reminder cadence are shown ("expires in 1d 22h · reminder every 8h"). Few tools surface this.

## 2. Findings

| # | Finding | Severity | Evidence |
|---|---|---|---|
| F1 | **The editor speaks developer, not ops.** Selecting a node shows a raw JSON config with CEL templates (`{{ nodes.qualify.output }}`, `{{ execution.conversationId }}`) and `Retry: {"maxAttempts":5}`. The node title shows the technical id (`create_lead`) instead of its label. Palette names are engineering terms (Extract, Classify, Switch, Map, Sub-flow). | High | `editor-node.png` |
| F2 | **Canvas is unreadable at the default fit.** The inbound flow is ~25 nodes; at "Fit" node text is ~6px. There is no grouping, so the story ("qualify → create lead → draft trip → review → send") is lost in boxes. | High | `editor.png` |
| F3 | **The approval card doesn't show what is being approved.** The execution's approval panel shows the node's input JSON (`title`, `assignees`, `expiresAfter`) — not the proposal, the recipient, the price, or the payload hash. Approving from here is approving blind. | High | `exec-waiting.png` |
| F4 | **Waits are hard to reason about.** "Resumes 2026-10-24 12:00 UTC" is in UTC (ops is in ART, coaches in US time zones); there's no "resume now", "extend", or "what happens next" affordance. Header status repeats ("Waiting · attempt 1 · waiting…"). | Medium | `exec-wait48.png` |
| F5 | **The log-scale timeline misleads.** A 12 ms node and a 7 min agent node render as similar-looking long green bars; a 22-day wait is the same green as work. Wall-clock waiting and active work need different encodings. | Medium | `exec-waiting.png`, `exec-wait48.png` |
| F6 | **Language mismatch.** Ops surfaces are specified in Spanish (content guide) but the flows prototype is in English. | Medium | all |
| F7 | **No path from "something broke" to "fix it".** A failed node shows an error but no plain-language cause, no suggested action, no "retry with edited input", no comparison against the last successful run. | Medium | spec §execution viewer vs prototype |
| F8 | Minor: "New flow" button looks disabled (grey); no templates; the Next dev overlay shows "1 Issue" on `ex-2b10` (dev-only runtime warning worth checking — outside this review). | Low | `flows.png`, `exec-wait48.png` |

## 3. Benchmark notes

- **n8n** — powerful canvas and node details view (input | config | output side by side, pinned data), but expressions and JSON are front and centre: great for builders, hard for ops. Its AI Workflow Builder (beta, Oct 2025, built on Claude) turns prompts into workflows; independent reviews say it isn't production-ready without human editing ([review](https://growwstacks.com/blog/n8n-ai-workflow-builder-review/), [launch](https://webmail.hunted.space/dashboard/n8n-io/launches/n8n-ai-workflow-builder), [Anthropic case](https://claude.com/customers/n8n)).
- **Zapier** — linear, numbered step list; each step written as a sentence ("Send email in Gmail"). Lowest learning curve; weak for branching.
- **Voiceflow** — conversation-first canvas, a test tool that plays the conversation and highlights the active block, transcripts linked to runs. The model to copy for `say/capture` flows.
- **Make** — visual "scenario" with per-module execution bubbles you can click to see bundles. Excellent for "what did this step receive and produce".
- **Temporal UI** — Timeline draws activities as spans and signals as points, pending work as dashed animated lines, and a compact vs full history toggle ([docs](https://docs.temporal.io/web-ui), [timeline post](https://temporal.io/blog/the-dark-magic-of-workflow-exploration)). Good model for waits vs work.
- **Retool Workflows** — code-first blocks with run history per block; strong for engineers, not ops.

**Positioning:** our differentiator is not the canvas — it's that ops can trust automations: approvals bound to exact payloads, publish-time security checks, evals before publish. The UX should make *that* visible and keep CEL/JSON one click away for builders.

## 4. Proposals

### P1 — "Modo operación": a plain-Spanish layer over the same graph  ·  Impact: High · Effort: M

**Problem:** F1, F2, F6. Lucía can't read or safely edit the flow.

**Proposal:**
- Two views of the same flow: **Pasos** (default for ops) and **Lienzo** (canvas, default for builders). Pasos is a numbered outline, Zapier-style, with branches as indented sub-lists and sentences generated from node config + labels.
- Each node renders a **sentence** ("Crear el lead con los datos del coach", "Esperar hasta 30 días antes de la salida") and the config panel becomes a **form** generated from the JSON Schema, with a variable picker that shows friendly names ("Coach → email") and inserts the CEL under the hood. "Ver expresión" toggles to raw CEL/JSON.
- **Groups** (collapsible sections) on the canvas: "Calificar", "Armar la gira", "Revisión de ops", "Envío". Default zoom shows groups, not 25 boxes.
- Spanish copy across ops surfaces; palette renamed by intent: *Preguntar al coach*, *Decidir*, *Esperar*, *Pedir aprobación*, *Hacer una acción*, *Consultar conocimiento*.

```
INBOUND COACH INQUIRY            [Pasos] [Lienzo]        v7 publicada · borrador +2   [Validar] [Publicar v8]
───────────────────────────────────────────────────────────────────────────────────────────────────────────
 1  Cuando llega un mensaje del coach (web o WhatsApp)
 2  💬 Saludar y explicar qué hacemos
 3  ✦  Calificar la consulta con el agente         → si pide un humano: crear tarea para ops y avisar
 4  ▸ Crear el lead con los datos del coach
 5  ▸ Armar el borrador de la gira                 → si falla 3 veces: tarea para ops
 6  💬 Avisar al coach que ops lo está revisando
 7  ✓ Pedir aprobación a Ops  (vence en 2 días · recordatorio cada 8 h)
      ├ aprobado   → Enviar la propuesta → "Tu propuesta está lista"
      ├ rechazado  → Tarea para ops → "Te va a contactar una persona"
      └ vencido    → Tarea para ops (urgente)
───────────────────────────────────────────────────────────────────────────────────────────────────────────
 Paso 4 · Crear el lead                                                         [Ver expresión]
   Datos del lead      [ Resultado de "Calificar la consulta"  ▾ ]
   Conversación        [ Esta conversación                     ▾ ]
   Si falla            ( ) Detener   (•) Reintentar hasta 5 veces   ( ) Seguir por otro camino
```

### P2 — Approvals and waits as first-class, human-readable moments  ·  Impact: High · Effort: M

**Problem:** F3, F4, F5. The two node types that make our flows special are the least explained.

**Proposal:**
- **Approval card shows the exact thing being approved**: rendered preview (proposal summary, price per person, recipient email, channel), the payload hash fingerprint, who/what requested it (agent run link), and three actions: *Aprobar*, *Editar y aprobar* (creates a superseding approval — already in spec), *Rechazar con motivo*. The node input JSON moves to an "Detalles técnicos" disclosure.
- **Waits speak in local time and offer control**: "Se reanuda el **jue 24 oct, 09:00 (ART)** — en 1 d 18 h", with *Reanudar ahora* (permissioned + audited), *Extender*, and "Después de esto: revisar qué proveedores no confirmaron".
- **Timeline encodes work vs waiting**: active work as solid bars on a linear-per-row scale with the duration label; waits as striped/dashed spans (Temporal-style) labelled "esperando aprobación · 7 h" / "esperando 48 h"; signals (approval decided, coach replied) as points.
- A cross-flow **"Esperando" queue** (filter on the executions list and a widget on Ops Home): everything waiting on a human, sorted by expiry.

```
EXECUTION EX-7F3A  ● Esperando a Ops · vence en 1 d 22 h          [Aprobar] [Editar y aprobar] [Rechazar]
┌ Qué se va a enviar ───────────────────────────────────────────────┐
│ Para: dwhitfield@lakeshore.example (Coach Dana Whitfield)         │
│ Propuesta: Buenos Aires · 10 días · 3 partidos (niveles 6–8)      │
│ Precio: US$ 2.890 por persona · 24 viajeros                       │
│ [Ver propuesta completa]           huella sha256:9f2c…e1  ✓ intacta│
│ Pedido por: agente "Calificar la consulta" · traza →              │
└───────────────────────────────────────────────────────────────────┘
LÍNEA DE TIEMPO
 greet            ▏12 ms
 calificar        ███████ 7 min
 crear lead       ▏84 ms
 armar gira       ▌2,1 s
 revisión de ops  ░░░░░░░░░░░░░░░░░░ esperando · 7 h (vence en 1 d 22 h)
```

### P3 — AI-native: "Describí la automatización" → borrador validado  ·  Impact: High · Effort: L

**Problem:** building a flow from a blank canvas is the biggest learnability cliff, and it's the moment that best shows "AI-native" to IGS.

**Proposal:** a prompt box on `/flows/new` and in the editor ("Cambiar este flow…"), in Spanish:

> "Cuando una gira se confirma, 21 días antes pedile a cada proveedor que confirme; si alguno no responde en 48 h, avisame por WhatsApp y creá una tarea."

The copilot produces a **draft** (never publishes), and the UI shows:
1. The flow in **Pasos** view with each step's provenance ("de tu pedido: '21 días antes'").
2. **Validator results inline**, including the security rule: if an external action is reachable from an untrusted trigger, it auto-proposes inserting an *Aprobación* node (quick fix from flow-editor.md).
3. **Assumptions it made** as editable chips ("Proveedores = todos los ítems pendientes", "Canal de aviso = WhatsApp de ops").
4. A **test run** on a sandbox trip with waits skipped, and the option to save it as an eval case.
5. For edits to an existing flow: a **visual diff** against the current draft before accepting.

Differentiator vs n8n's builder: we gate AI-authored flows behind the same validator, approvals and evals as human-authored ones, so "AI drafted it" never means "AI shipped it".

```
NUEVO FLOW
┌───────────────────────────────────────────────────────────────────────────┐
│ Describí la automatización                                                │
│ Cuando una gira se confirma, 21 días antes pedile a cada proveedor que    │
│ confirme; si alguno no responde en 48 h, avisame y creá una tarea.        │
│                                                       [Generar borrador] │
└───────────────────────────────────────────────────────────────────────────┘
Borrador generado · 7 pasos                         Supuestos: [Todos los ítems pendientes ▾] [WhatsApp de ops ▾]
 1 Cuando una gira pasa a "confirmada"
 2 Esperar hasta 21 días antes de la salida        ← "21 días antes"
 3 Pedir confirmación a cada proveedor  ⚠ acción externa
      ↳ Arreglo sugerido: agregar "Pedir aprobación a Ops" antes   [Aplicar]
 4 Esperar 48 h                                    ← "en 48 h"
 5 Si alguno no confirmó → avisar a ops por WhatsApp + crear tarea
 [Probar con una gira de prueba]  [Guardar como borrador]  [Agregar como caso de eval]
```

### P4 — Debugging for non-developers: explain, compare, retry with edits  ·  Impact: Medium · Effort: M

**Problem:** F7.

**Proposal:**
- **"¿Por qué pasó esto?"** on any execution: a generated, cited explanation built from node runs ("Se fue por *rechazado* porque Lucía rechazó a las 15:02 con el motivo 'precio alto'").
- **Plain-language errors with a next step**: map error classes to sentences + actions ("El mail rebotó: la dirección del coach no existe → *Corregir email y reintentar*").
- **Retry from node with edited input** (Make/n8n pattern) on the same pinned version, audited.
- **Compare with last successful run**: side-by-side I/O diff per node.
- Executions searchable by **trip/lead/account**, and linked from the trip and Account 360 pages ("2 automatizaciones activas para esta gira").

### P5 — Templates and a guided first flow  ·  Impact: Medium · Effort: S

**Problem:** F8 and onboarding. An empty `/flows/new` is intimidating.

**Proposal:** a template gallery tied to IGS jobs-to-be-done — *Seguimiento de propuesta sin respuesta*, *Recordatorio de formularios del roster*, *Confirmación de proveedores*, *Reporte post-partido*, *Encuesta post-gira* — each opening in Pasos view with a 4-step coach mark (trigger → pasos → probar → publicar). Make "New flow" a primary button.

## 5. Priority

| Order | Proposal | Why first |
|---|---|---|
| 1 | P2 Approvals & waits | It's the trust story of the whole product and the demo's key beat |
| 2 | P1 Modo operación | Unblocks the actual users; Pasos view also makes the demo legible on video |
| 3 | P3 Describe → draft | Highest "AI-native" signal for a first-time visitor; depends on P1's Pasos view and the validator (exists) |
| 4 | P4 Debugging | Needed once real executions exist (phase 4+) |
| 5 | P5 Templates | Cheap, do alongside P1 |

Screenshots: scratchpad `ux-v2/` (`flows.png`, `editor.png`, `editor-node.png`, `exec-waiting.png`, `exec-wait48.png`).

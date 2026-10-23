# Content, i18n & accessibility guide

How IGS OS talks, formats and stays usable for everyone. Applies to `apps/web`, to messages produced by flows and agents (`services/core`, `services/worker`), and to the guided tour (`demo-script.md`). Visual tokens come from `brand-reference.md`.

---

## 1. Voice & tone

IGS's own voice (from infinityglobalsports.com) is **short, confident, athletic**: imperative triplets — *Train. Compete. Experience.* · *Real Sport. Real Environments.* We borrow it for headlines and empty states, and stay plain and precise everywhere work gets done.

| Surface | Language | Audience | Tone | Example |
|---|---|---|---|---|
| Landing, tour, proposal hero | English | First-time visitors, coaches | IGS punchy: triplets, uppercase display, no jargon | **RUN EVERY TOUR. ONE SYSTEM.** · *Agents draft. Flows run. Your team decides.* |
| Coach chat & proposal body | English (coach's language if they write in another) | US college/club coaches | Warm, knowledgeable, concise. Concrete numbers. Never salesy pressure | "Great — 22 players, women's D1, Buenos Aires in March. I'll match you with opponents at your level and send a draft itinerary." |
| Ops panel, copilot, notifications | Spanish (rioplatense, *vos*) | IGS ops team in Buenos Aires | Direct, operational, verb-first. Short | "Aprobá la propuesta para enviarla." · "Faltan confirmar 4 proveedores." |
| Flow editor & executions | Spanish UI, technical terms kept (*flow, nodo, trigger, webhook*) | Ops power users, builder | Neutral, exact | "El nodo `draft_trip` falló 2 veces. Próximo reintento en 30 s." |
| Errors anywhere | Same as surface | — | Calm, specific, what happened + what to do. No blame, no "Oops" | "No pudimos contactar al servicio de búsqueda. Reintentamos solos en 10 s." |

Rules
- **Headlines**: max 6 words; triplets only where it reads naturally (landing, tour, proposal, empty states). Never in error messages or tables.
- **Numbers over adjectives**: "3 partidos, 2 entrenamientos" beats "un itinerario completo".
- **Agent ≠ person**: the agent never pretends to be human. In coach chat it introduces itself once as "IGS travel assistant"; in ops it's "el agente" or "Copiloto". Offer a human: "¿Querés que lo vea alguien del equipo?" / "Want someone from our team to take it from here?".
- **No invented facts**: copy templates never state prices, policies or availability that don't come from data (enforced in agent prompts and evals; see `evals-and-testing.md`).
- **Inclusive & respectful**: teams are often minors — say "jugadoras/jugadores" or "players", never physical descriptors; don't show minors' personal data in examples or screenshots (see `security.md`).
- **Brand disclaimer** on every public page footer: *"Demo built by Mauricio Villalba — not an official Infinity Global Sports product."*

### 1.1 Word list
| Use | Avoid | Why |
|---|---|---|
| gira / tour | viaje (for the product object) | "Gira" is what IGS sells; "viaje" is ambiguous with flights |
| propuesta / proposal | cotización, quote (as noun for the whole document) | The document includes itinerary, not only price |
| aprobar / approve | validar, OK | Approval is a formal, logged action |
| proveedor / provider | partner, vendor | Consistent with data model |
| ejecución / execution (of a flow) | run, corrida (in UI) | "Run" stays for agent traces only |
| copiloto / copilot | bot, IA | It's an assistant inside the tool, not a chatbot |
| nivel 1–10 / level 1–10 | "bueno", "fuerte" | Matching is numeric (see knowledge "How we match opponents") |

---

## 2. Microcopy patterns

### 2.1 Agent actions (what the agent did / is doing)
Pattern: **[verb in progress/past] + [object] + [evidence link]**. Streaming status uses present continuous; completed uses past.

| State | Ops (ES) | Coach (EN) |
|---|---|---|
| Tool running | "Buscando rivales de nivel 7…" | "Finding opponents at your level…" |
| Tool done | "Encontré 4 rivales · ver" | "Found 4 matching opponents" |
| Knowledge lookup | "Consultando contratos y políticas…" | "Checking our policies…" |
| Draft created | "Armé un borrador de gira · 10 días · US$ 2.890 por persona · ver" | "Your draft itinerary is ready → View proposal" |
| Handoff | "Le pasé la conversación a Lucía (ops)." | "I've passed this to our team — someone will reply within 24 h." |
| Uncertain | "No encontré información sobre esto en los documentos. ¿Lo cargo como pregunta para el equipo?" | "I don't have that information yet — I've asked our team and will get back to you." |

Citations: chip with **source title · section**, e.g. `[Contrato Palermo Sports Hotel · §4.2]`. Never a bare "[1]". Clicking opens the passage with the cited text highlighted.

### 2.2 Approvals
An approval card always answers four questions, in this order: **what** was decided by the agent, **why** (key facts), **what will happen** if approved (exact side effect and recipient), **who/when**.

| Element | Copy (ES) |
|---|---|
| Title | "Aprobar propuesta — Lakeshore University" |
| Effect line | "Al aprobar, se envía la propuesta a coach@stfrancis.example y la gira pasa a *Propuesta enviada*." |
| Primary | "Aprobar y enviar" (verb + effect; never just "OK" or "Confirmar") |
| Secondary | "Rechazar" → requires a reason (textarea, min 10 chars): "Contale al agente qué cambiar" |
| Expiry | "Vence en 47 h. Si nadie decide, se avisa a ops." |
| Done | "Aprobado por vos · 14:32 · enviado" |
| Payload changed | "La propuesta cambió desde que se pidió la aprobación. Revisala de nuevo." |
| Already decided | "Esta aprobación ya la resolvió Juan a las 14:30 (rechazada)." |

Destructive/external actions (cancel trip, send to coach, charge deposit) are **never** one click from a list: they open the card first. The approve button shows the side effect inline.

### 2.3 Errors
Pattern: **what happened** + **what we're doing / what you can do** + optional **details link** (for ops: execution id, trace). Never expose stack traces or raw provider errors to coaches.

| Situation | Ops (ES) | Coach (EN) |
|---|---|---|
| LLM/provider timeout, auto-retry | "El agente tardó más de lo normal. Reintentando (2/3)…" | "One moment — still working on it." |
| Retries exhausted | "El nodo `draft_trip` falló 3 veces. Ver detalle · Reintentar desde este nodo" | "Sorry, I couldn't finish your draft. Our team has been notified and will email you today." |
| Validation | "Falta la fecha de inicio. Completala para continuar." | "What dates are you considering? Even a rough month helps." |
| Permission | "No tenés permiso para publicar flows. Pedíselo a un admin." | — |
| Rate limit (demo) | "Llegaste al límite de preguntas de la demo por hora. Mostramos la última respuesta verificada." | — |
| Offline | "Sin conexión. Los cambios se guardan cuando vuelvas." | "You're offline — we'll send your message when you reconnect." |
| Empty state (good news) | "Todo confirmado. Nada pendiente hoy." | — |

### 2.4 Status labels
Single source of truth for labels and colors (tokens in §5.2):

| Domain | Values (ES / EN) |
|---|---|
| Trip | Borrador / Draft · Propuesta enviada / Proposed · Confirmada / Confirmed · En curso / In progress · Finalizada / Completed · Cancelada / Cancelled |
| Trip item | Pendiente / Pending · Solicitado / Requested · Confirmado / Confirmed · Cancelado / Cancelled |
| Execution | En curso / Running · Esperando / Waiting · Completada / Completed · Falló / Failed · Cancelada / Cancelled |
| Approval | Pendiente / Pending · Aprobada / Approved · Rechazada / Rejected · Vencida / Expired |

Labels always include text — never color alone.

---

## 3. Numbers, dates, currency

All formatting goes through `Intl` with an explicit locale; never hand-built strings. Data is stored in UTC (timestamps), ISO dates (`YYYY-MM-DD`) for trip days, and integer **USD** amounts (IGS prices in USD by policy).

| Type | `es-AR` (ops) | `en-US` (coaches) | Notes |
|---|---|---|---|
| Integer | 1.234 | 1,234 | |
| Decimal | 1.234,5 | 1,234.5 | |
| Currency (USD) | US$ 2.890 | $2,890 | `Intl.NumberFormat(locale, { style: "currency", currency: "USD", currencyDisplay: es ? "symbol" : "narrowSymbol" })`; in es-AR always show **US$** to avoid confusion with ARS `$`. No decimals for prices ≥ 100 |
| Percent | 30 % | 30% | |
| Short date | 12/03/2027 | 03/12/2027 | Avoid numeric dates in coach-facing copy — ambiguous across locales |
| Medium date | 12 mar 2027 | Mar 12, 2027 | Default everywhere |
| Range | 12–21 mar 2027 | Mar 12–21, 2027 | `Intl.DateTimeFormat#formatRange` |
| Weekday + date | vie 12 mar | Fri, Mar 12 | Itinerary days |
| Time | 14:30 | 2:30 PM | |
| Relative | hace 2 min · en 23 días | 2 min ago · in 23 days | `Intl.RelativeTimeFormat` |
| Duration | 1 h 20 min | 1h 20m | |
| Phone | +54 11 5555-0101 | +1 (555) 010-1000 | Store E.164 |

Time zones
- Itinerary times render in the **destination's** zone (`America/Argentina/Buenos_Aires`, `America/Sao_Paulo`, `America/Costa_Rica`), labeled once per page ("Horario de Buenos Aires").
- Ops timestamps render in the user's zone (default ART).
- Deadlines sent to coaches (deposit due, approval expiry in emails) render in the coach's zone when known, else US Eastern with the zone abbreviation.
- Temporal timers use absolute UTC instants computed server-side; the UI never computes deadlines.

Units: distances km (es) / mi + km in parentheses (en, proposal only); temperatures °C (es) / °F (°C) (en).

---

## 4. i18n approach

**Decision: `next-intl`** for `apps/web`; a small message catalog on the Python side for agent/flow templates.

Why `next-intl` and not "built-in":
- Next.js App Router has no built-in message translation; its i18n guide covers locale routing via `proxy` plus your own dictionaries. `next-intl` adds what we need on top: ICU MessageFormat (plurals, gender, select — Spanish needs plural agreement: "1 proveedor sin confirmar" / "4 proveedores sin confirmar"), works in Server Components (no client bundle for strings on server-rendered pages), typed keys, and formatting helpers wired to the same `Intl` rules as §3.
- Alternatives considered: hand-rolled dictionaries (fine for 2 locales but no ICU plurals, re-inventing formatting), `react-i18next` (client-first, heavier on RSC).

Configuration
- Locales: `es-AR` (default for `/ops/**`), `en-US` (default for `/`, `/chat`, `/proposal/**`).
- **No locale prefix in URLs** for ops (`localePrefix: "never"`): locale comes from the user preference cookie, then `Accept-Language`, then route default. The ops header has an `ES / EN` switch (useful for English-speaking leadership).
- **Proposal language is data, not URL**: `trips.locale` (from the lead's conversation language) decides the proposal's language, so the same link always renders the same document.
- Messages in `apps/web/messages/{es-AR,en-US}.json`, namespaced by surface (`ops.home`, `ops.approvals`, `flows.nodes`, `chat`, `proposal`, `tour`). Node type labels/descriptions come from the flow schema's `title`/`description` with translations in the catalog keyed by node type.
- CI: a check fails on missing keys in either locale and on unused keys.

Server side (`services/core`, `services/worker`)
- Agent replies: the model answers in the conversation's language (instruction + language detected on the first coach message, persisted on the conversation). Evals include a Spanish-speaking coach.
- Templated messages (approval requests, notifications, emails) use a Python catalog (`babel` + ICU-compatible `MessageFormat`), same keys as the web where shared. Never let the LLM produce the text of a system notification that has a template.
- Dates/currency in emails formatted with Babel using the same table as §3.

---

## 5. Accessibility — WCAG 2.2 AA

Target: **WCAG 2.2 level AA** on every surface on the demo path (landing, ops home, executions, approvals, copilot, proposal, chat) and the flow editor's read-only mode. The flow editor's edit mode targets AA with a documented keyboard alternative (§5.4).

### 5.1 Contrast checks on the brand palette
Computed with relative luminance (WCAG formula), approximate from the HSL tokens in `brand-reference.md`. AA thresholds: **4.5:1** normal text, **3:1** large text (≥24 px, or ≥18.66 px bold) and UI components/graphics.

| Pair | Ratio ≈ | Normal text | Large / UI |
|---|---|---|---|
| foreground `0 0% 10%` on cream background `40 7% 95%` | 15.7:1 | ✅ | ✅ |
| muted-fg `0 0% 40%` on cream | 5.2:1 | ✅ | ✅ |
| muted-fg on muted `40 5% 90%` | 4.5:1 | ⚠️ borderline — avoid for body text; use foreground | ✅ |
| foreground `0 0% 95%` on dark background `0 0% 5%` | 17.4:1 | ✅ | ✅ |
| dark muted-fg `0 0% 60%` on dark background | 6.8:1 | ✅ | ✅ |
| dark muted-fg on dark muted `0 0% 15%` | ≈4.9:1 | ✅ | ✅ |
| primary-fg white on primary black (buttons) | 21:1 | ✅ | ✅ |
| border `40 5% 85%` on cream (input outlines) | ≈1.3:1 | — | ❌ **inputs need a stronger outline**: use `0 0% 55%` (≈3.6:1) for form control borders; keep `--border` for dividers only |
| Argentina blue `210 50% 67%` on cream | ≈2.2:1 | ❌ | ❌ → use only as **fill** with dark text on it (≈8:1), or darken to `210 55% 38%` for text |
| Brazil gold `#FFCB05` on cream | ≈1.4:1 | ❌ | ❌ → fill only, with black text (≈13:1) |
| Brazil green `#009c3b` on cream | ≈3.3:1 | ❌ | ✅ large/UI only; for text use `151 100% 22%` |
| USA red `#B22234` on cream | ≈5.9:1 | ✅ | ✅ |
| destructive `0 84.2% 60.2%` on cream | ≈3.4:1 | ❌ | ✅ → for **text** use `0 74% 42%` (≈5.9:1); keep the brand value for fills/icons |

Status tokens to add (text-safe on cream; lighter variants for dark mode, each ≥4.5:1 on `0 0% 5%`):

| Token | Light (on cream) | Dark (on near-black) |
|---|---|---|
| `--success` | `142 72% 29%` (#15803D) ≈5.0:1 | `142 69% 58%` |
| `--warning` | `26 90% 37%` (#B45309) ≈5.0:1 | `38 92% 60%` |
| `--danger` | `0 74% 42%` (#B91C1C) ≈5.9:1 | `0 91% 71%` |
| `--info` | `221 83% 40%` ≈6.5:1 | `213 94% 68%` |

Each status badge = text label + icon + tinted background (`hsl(var(--x) / .12)`), so meaning never relies on color (1.4.1). Re-verify all ratios with a contrast tool when tokens land in `globals.css` (add an automated check — §5.6).

### 5.2 Focus
- Visible focus on every interactive element: **2 px solid `--ring`, 2 px offset**; on dark, `--ring` is `0 0% 90%`. Never `outline: none` without a replacement.
- 2.4.11 Focus Not Obscured: sticky headers, the copilot panel and tour cards must not cover the focused element — use `scroll-margin-top` equal to header height; the tour card avoids the spotlight target.
- Focus order follows reading order; route changes move focus to the page `<h1>` (announced).
- 2.5.8 Target Size: interactive targets ≥ 24×24 CSS px (aim 40 px in ops tables and mobile chat).

### 5.3 Keyboard & structure (all surfaces)
- Skip link "Saltar al contenido" / "Skip to content".
- Landmarks: `header`, `nav` (ops sidebar), `main`, `aside` (copilot), `footer`. One `h1` per page.
- Tables (trips, executions) use real `<table>` with `scope`; sortable headers are buttons with `aria-sort`.
- Dialogs/sheets: focus trap, `Esc` closes, focus returns to trigger. The copilot panel is a non-modal `aside` with `⌘K`/`Ctrl+K` to open and a visible button too (shortcuts are never the only way).
- Forms: visible labels (no placeholder-only), errors linked via `aria-describedby`, error summary at top on submit. 3.3.7 Redundant Entry: don't ask again for data already given in the same flow (e.g. approval rejection reason pre-fills the last draft). 3.3.8 Accessible Authentication: admin login must allow password managers/passkeys, no cognitive puzzles.
- Drag-and-drop anywhere (trip item reorder, canvas) has a non-drag alternative (2.5.7 Dragging Movements): move up/down buttons, "Mover a día…" menu.

### 5.4 Flow canvas (React Flow) keyboard model
Canvases are the riskiest component. Requirements:
- Canvas is a focusable region (`role="application"` only while in edit mode; read-only uses `role="group"` with `aria-roledescription="flow diagram"`), labelled "Flow {name}, versión {n}".
- **Arrow keys** move focus between nodes following edges (→ next along the default port, ← previous, ↑/↓ siblings); `Tab` leaves the canvas. `Enter` opens the node's side panel (config in editor, I/O in executions). `Esc` returns focus to the canvas.
- Each node exposes an accessible name: "{type}: {label}, estado {status}, {n} salidas" and its ports as a list in the side panel.
- **Equivalent list view** toggle ("Ver como lista"): an ordered, nested list of nodes and connections with the same actions (inspect, retry from node, add after). This is the conformance path for screen reader users and for 2.5.7.
- Zoom/pan with `+`/`-`/`0` and arrow keys with `Shift`; controls also visible as buttons.
- Live execution updates on the canvas announce **only state changes of the focused node or failures**, through a polite live region; no announcement per animation frame.

### 5.5 Motion
- Respect `prefers-reduced-motion: reduce`: no node "lighting up" animation (states switch instantly), no spotlight transition in the tour, no auto-scrolling hero, no parallax. Streaming text appears in chunks without a typing animation.
- No content flashes more than 3 times per second. Loading skeletons are static shimmer-free under reduced motion.
- Animations ≤ 200 ms for UI feedback; the "Replay live" in the tour is user-initiated and pausable.

### 5.6 Streaming chat & copilot (screen readers)
Token streaming is hostile to screen readers if done naively. Rules:
- The message list is a `role="log"` with `aria-live="polite"` and `aria-relevant="additions"`.
- **Don't stream tokens into the live region.** Render streaming text in a container with `aria-busy="true"`; when the message completes (`done` event), flip `aria-busy="false"` and append the final message to the log once, so it's announced as a whole.
- Tool activity chips ("Buscando rivales…") are announced once via a separate polite status region (`role="status"`), debounced to at most one announcement every 2 s; completion of a long task (>5 s) is announced ("Borrador listo").
- A visually hidden "El asistente está escribiendo…" status while busy; a **Stop** button (keyboard reachable) to cancel generation.
- Citations are real links with the source title as accessible name, not "[1]".
- Input: `textarea` with label, `Enter` sends, `Shift+Enter` newline, documented in a hint; send button with accessible name.
- Proposal cards in chat are links with descriptive text ("Ver propuesta: Buenos Aires, 12–21 mar 2027").
- Errors in chat announced assertively only when they block the user.

### 5.7 Proposal & PDF
- Semantic headings per day; the itinerary is a list, not a table of divs.
- Images have alt text describing the place ("La Bombonera stadium, Buenos Aires"); decorative imagery `alt=""`.
- Print stylesheet keeps contrast and link URLs visible; the PDF is generated from the same semantic HTML (browser print), with document language set (`lang="en"`).

### 5.8 Language & reading
- `lang` set on `<html>` per locale and on any inline foreign-language span (e.g. Spanish place names in English proposals don't need it, but a Spanish quote does).
- Body text ≥ 16 px; line length ≤ 80 characters on reading surfaces; Barlow Condensed never below 18 px or for paragraphs (condensed faces hurt legibility at small sizes).
- Uppercase only for short labels/headlines (≤ 6 words); screen readers read the source text, so write it in sentence case and apply `text-transform`.

### 5.9 Verification
| Check | Tool | When |
|---|---|---|
| Automated rules | `@axe-core/playwright` in the e2e demo-story test | Every PR (blocks on serious/critical) |
| Contrast of tokens | Script computing ratios from `globals.css` tokens | Every PR touching tokens |
| Keyboard-only run of the demo script | Manual checklist | Before sharing the link / recording |
| Screen reader smoke (VoiceOver + Safari, NVDA + Firefox) | Manual: chat streaming, approval card, canvas list view | Before sharing the link |
| Reduced motion | Playwright with `reducedMotion: "reduce"` | e2e suite |
| Zoom 200% / reflow 320 px | Manual + Playwright viewport | Before sharing the link |

### 5.10 Component checklist
| Component | Key requirements |
|---|---|
| Button | Native `<button>`; verb label; loading state keeps width and sets `aria-busy`; min target 24 px |
| Badge (status) | Text + icon; status tokens from §5.1; not interactive unless it's a filter (then a toggle button with `aria-pressed`) |
| Card / approval card | Heading inside; primary action names the effect; reject requires reason with labelled textarea |
| KPI / Stat | Number + label in the same accessible name ("4 proveedores sin confirmar"); trend described in text, not only arrow color |
| Table | Real table, sortable headers with `aria-sort`, row actions as buttons with row context in the name |
| Tabs | WAI-ARIA tabs pattern with arrow-key navigation |
| Toast | `role="status"` (or `alert` for failures), stays ≥ 6 s, pausable on hover/focus, never the only place an error is shown |
| Copilot panel | Non-modal `aside`, `⌘K` + button, focus management, streaming rules §5.6 |
| Flow canvas | §5.4 keyboard model + list view |
| Tour overlay | `role="dialog"` non-modal, focus to card on step, `Esc` exits, reduced motion |
| Charts (eval trends, KPIs) | Data table alternative, labeled axes, colors from status/accent tokens with ≥3:1 against background, patterns or direct labels instead of legend-only |

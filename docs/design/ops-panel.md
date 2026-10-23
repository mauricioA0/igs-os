# Ops panel — screen-by-screen UX

Status: design spec, no code yet. Applies to `apps/web` under `/ops`. The spec is in English; **UI copy is in Spanish** (the ops team works from Buenos Aires) and appears here in quotes. Visual rules come from [brand-reference.md](brand-reference.md); data and endpoints come from [core-api.md](../architecture/core-api.md), [data-model.md](../architecture/data-model.md) and [security.md](../architecture/security.md).

Out of scope here (other specs): flow editor and execution viewer, the copilot drawer internals, the coach chat and the public proposal.

---

## 0. Shell and shared rules

### 0.1 Who uses it and how
- **Ops coordinator** (main user): runs 5–20 live trips, chases providers, approves what agents propose. Desktop, two monitors, keyboard-heavy, all day.
- **Sales**: works the leads pipeline, sends proposals.
- **Owner**: glances at Hoy and the numbers; approves the high-stakes items.

The panel's job is to answer **"what needs me right now?"** and to make **every agent action visible, attributable and reversible**.

### 0.2 Layout

```
┌──────────────┬──────────────────────────────────────────────────────────────┐
│ IGS OS       │  ⌘K Buscar viajes, leads, proveedores…        ◐  🔔3  MV ▾  │
│ ──────────── ├──────────────────────────────────────────────────────────────┤
│ ● Hoy      3 │                                                              │
│   Viajes     │   <page header: EYEBROW · H1 (display font) · actions>       │
│   Leads      │                                                              │
│   Aprobac.  2│   <page body>                                                │
│   Proveedores│                                                              │
│   Conocim.   │                                                    ┌────────┤
│ ──────────── │                                                    │Copiloto│
│   Flows      │                                                    │drawer  │
│   Ejecuciones│                                                    │(⌘J)    │
│   Trazas     │                                                    │        │
│ ──────────── │                                                    │        │
│ ⌘J Copiloto  │                                                    └────────┤
└──────────────┴──────────────────────────────────────────────────────────────┘
```

- **Sidebar** (240 px, collapsible to 56 px icons with `[`): counts on Hoy and Aprobaciones are live (pending items for the current user's role). Flows/Ejecuciones/Trazas are linked, specified elsewhere.
- **Top bar**: global search (⌘K command palette: jump to any trip/lead/provider, run actions like "Pedir confirmaciones del viaje…"), theme toggle, notifications, user menu (role, tenant).
- **Copilot drawer** (⌘J): right side, 420 px, pushes content on ≥1440 px, overlays below. Always **scoped to the current page** (a trip, a lead, a document); the scope chip is visible and removable. Its write actions follow the same tool classes as MCP and never bypass approvals.

### 0.3 Visual rules (from the brand)
- Monochrome chrome on cream (`background 40 7% 95%`) in light, near-black (`0 0% 5%`) in dark. **Dark mode is first-class** for ops.
- **Barlow Condensed**, uppercase, tracking `.1em`: eyebrows, page titles, KPI numbers, table column headers. **DM Sans** for everything dense (tables, forms, timeline). Montserrat only in marketing-like headers.
- Radius `.25rem` on inputs, buttons, badges; `.5rem` on cards. No shadows except for overlays.
- **Country accents** only as a 3 px left rule on trip rows/cards and as the destination chip dot: Argentina `210 50% 67%`, Brasil `#009c3b`, Costa Rica `#B2896C` (warm neutral, no official accent on the site), España TBD.
- Status colors are added for the ops tool (not on the marketing site), muted and AA-compliant on both themes:

  | Token | Meaning | Used for |
  |---|---|---|
  | `success` | done / confirmed | `confirmed`, `won`, `succeeded`, `ready` |
  | `warning` | waiting on someone | `pending`, `requested`, `waiting`, `qualified` |
  | `danger` | broken / at risk | `failed`, `cancelled`, `lost`, `expired`, overdue |
  | `info` | in progress / system | `running`, `ingesting`, `proposed`, `in_progress` |
  | `neutral` | inert | `draft`, `new`, `skipped` |

  Status is never color-only: every badge has a label and, in dense tables, an icon.

### 0.4 Attribution (the core UX promise)
Every change shown anywhere carries **who did it**, as an actor chip:

| Actor | Chip | Example copy |
|---|---|---|
| Person | avatar + name | "Lucía G." |
| Agent | ✦ + agent name | "✦ Agente de ventas" |
| Flow | ⛓ + flow name + version | "⛓ Control pre-salida v3" |
| MCP client | ⌁ + client name | "⌁ Claude Code (Mauricio)" |
| System | ⚙ | "⚙ Sistema" |

Source: `audit_log.actor_type/actor_id`. Clicking an agent/flow chip opens the execution or agent run that made the change.

### 0.5 Density
Two densities, toggled per user (`D`): **Cómodo** (row height 44 px, default for owner/sales) and **Compacto** (32 px, default for ops). Numbers are tabular (`font-variant-numeric: tabular-nums`). Dates use the trip's local timezone with relative hints ("en 4 días").

### 0.6 Global states
| State | Pattern |
|---|---|
| Loading | Skeleton rows/cards matching the final layout; no spinners for full pages. Partial refresh shows a 2 px top progress bar. |
| Empty | Short sentence + one primary action + (where useful) "Preguntale al copiloto". Never an empty table header alone. |
| Error | Inline banner in the affected region with the RFC 9457 `title`, a "Reintentar" button and a "Copiar ID de traza" link (`trace_id`). The rest of the page keeps working. |
| Offline / stale | Top banner "Sin conexión — los datos pueden estar desactualizados". Mutations are disabled, not queued. |
| Permission | Actions the role can't perform are hidden in menus and disabled with a tooltip on primary buttons ("Requiere rol ops"). |

Mutations are optimistic only for low-risk internal writes (notes, `requested`); anything gated or external waits for the server and shows the resulting approval.

### 0.7 Global keyboard shortcuts
| Keys | Action |
|---|---|
| `⌘K` | Command palette / search |
| `⌘J` | Toggle copilot (scoped to page) |
| `g h` / `g v` / `g l` / `g a` / `g p` / `g c` | Go to Hoy / Viajes / Leads / Aprobaciones / Proveedores / Conocimiento |
| `j` / `k` | Next / previous row or card |
| `Enter` / `o` | Open selected |
| `/` | Focus the page filter |
| `x` | Select row (bulk actions) |
| `D` | Toggle density |
| `?` | Shortcut sheet |
| `Esc` | Close drawer/modal, clear selection |

---

## 1. Hoy (Today)

**Purpose.** One screen that lists everything that needs a human today, ranked by urgency, plus the week's departures. Default landing page.

**Data.** `GET /approvals?status=pending`, `list_unconfirmed_items` (via `GET /trips` + items), `GET /trips?status=confirmed&from=today&to=+7d`, `GET /executions?status=failed&since=24h`, `GET /leads?status=new`.

### Wireframe
```
HOY · JUEVES 22 DE OCTUBRE                                  [Pedir confirmaciones ▾]

┌ REQUIERE ACCIÓN ──────────────────────────────────────────────────────────────┐
│ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐               │
│ │ 2           │ │ 7           │ │ 3           │ │ 1           │               │
│ │ APROBACIONES│ │ SIN CONFIRM.│ │ SALIDAS 7D  │ │ INCIDENTES  │               │
│ │ 1 vence hoy │ │ 2 vencidos  │ │ próx: lun   │ │ flow fallido│               │
│ └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘               │
└───────────────────────────────────────────────────────────────────────────────┘

┌ TU COLA ─────────────────────────────────────────── Ordenar: urgencia ▾ ──────┐
│ ▲ ALTA  Aprobar envío de propuesta · Lakeshore U. W-Soccer   ⛓ Consulta v2│
│         "Propuesta BA 10 días, US$ 2.840 pp"              vence en 3 h  [Ver] │
│ ▲ ALTA  Hotel sin confirmar · Palermo Sports Hotel · Gustavus     sale en 4 d │
│         Pedido hace 52 h, sin respuesta                [Recordar] [Abrir viaje]│
│ ● MEDIA Flow fallido · Control pre-salida v3 · nodo "Enviar email"            │
│         SMTP 550 · 1 reintento                       [Ver ejecución] [Reint.] │
│ ● MEDIA Lead nuevo sin calificar · Club Denver Elite U17          hace 2 h    │
│ …                                                                             │
└───────────────────────────────────────────────────────────────────────────────┘

┌ SALIDAS DE ESTA SEMANA ───────────────────────────────────────────────────────┐
│ ▌lun 26 · Lakeshore U. · Buenos Aires · 24 viajeros · 18/20 confirmados ▓▓▓░│
│ ▌mié 28 · Gustavus Adolphus · Río       · 19 viajeros ·  9/14 confirmados ▓▓░░│
└───────────────────────────────────────────────────────────────────────────────┘
```
`▌` = country accent rule.

### Components
- **KPI tiles** (4): number in display font, label eyebrow, one-line context; clicking filters "Tu cola".
- **Queue list** ("Tu cola"): unified items of type `approval | unconfirmed_item | failed_execution | new_lead | overdue_payment (future)`, each with urgency, subject, actor chip, due/relative time, 1–2 inline actions.
- **Departures strip**: trip rows with confirmation progress bar (`confirmed / total items`).
- Header action **"Pedir confirmaciones ▾"**: runs `request_provider_confirmations` for one or all departing trips (write, starts a flow; shows the resulting execution id).

### Ranking
Urgency score = due time proximity (approval `expires_at`, departure date) × severity (gated customer-facing > provider unconfirmed < 72 h before day > failed execution > new lead). Explained on hover ("Alta porque sale en 4 días y el hotel no confirmó").

### States
- Empty: "Nada pendiente. Todas las salidas de la semana están confirmadas." + link to Viajes.
- Partial failure: each section loads independently; a failed section shows its own error banner.
- Real time: queue updates via SSE/poll (30 s); new items slide in with a subtle highlight, never reorder under the cursor while the user is hovering.

### Interactions
- Approve/reject inline only for low-risk approvals; anything customer-facing or destructive opens the Approval detail (§6) — **no one-click approve for external actions**.
- "Recordar" on an unconfirmed item = `update_trip_item` note + re-request (write-external → creates an approval if policy says so).
- Snooze an item (`s`): hides it until a chosen time; stored per user.

### Shortcuts
`j/k` move, `Enter` open, `a` approve (only when inline-allowed), `r` reject (opens comment), `s` snooze, `1–4` filter by KPI tile.

### Density
Compact by default; queue rows 2 lines max.

---

## 2. Viajes (Trips list)

**Purpose.** Find any trip fast and see portfolio health: what's departing, what's at risk.

**Data.** `GET /trips?status=&from=&to=&country=&q=` (cursor pagination), with computed `items_confirmed/items_total`, `travelers`, `unconfirmed_overdue`.

### Wireframe
```
VIAJES                                                      [+ Nuevo viaje] [⇣ CSV]

[Buscar…/]  Estado: Todos ▾  Destino: ● AR ● BR ● CR  Salida: Próx. 60 días ▾  Deporte ▾
Vista: ▤ Tabla  ▦ Tarjetas  ▥ Calendario                      42 viajes · 3 en riesgo

┌─┬───────────────────────────────┬──────────┬───────────┬────────┬──────────┬─────────┬────────┐
│▌│ EQUIPO / VIAJE                │ DESTINO  │ FECHAS    │ VIAJ.  │ ESTADO   │ CONFIRM.│ PRECIO │
├─┼───────────────────────────────┼──────────┼───────────┼────────┼──────────┼─────────┼────────┤
│▌│ Lakeshore U. · W Soccer D1│ ● BA, AR │ 26/10–4/11│   24   │ Confirm. │ 18/20 ⚠ │ 2.840  │
│▌│ Gustavus Adolphus · M Soccer  │ ● Río,BR │ 28/10–6/11│   19   │ Confirm. │  9/14 ⚠ │ 3.150  │
│▌│ Denver Elite U17 · M Soccer   │ ● BA, AR │ 12/03–21/03│  22   │ Propuesto│   —     │ 2.610  │
└─┴───────────────────────────────┴──────────┴───────────┴────────┴──────────┴─────────┴────────┘
```

### Components
- **Filter bar**: text search (team, coach, organization), status multi-select, country chips (with accent dots), departure window presets, sport, saved views ("Mis viajes", "En riesgo", "Este mes").
- **Views**: Table (default for ops), Cards (owner; card = country accent top rule, team, dates, progress ring), Calendar (month grid of trips as bars, colored by country).
- **Risk marker ⚠**: any unconfirmed item within 7 days of its day, or a failed execution attached to the trip.
- Bulk actions (with `x` selection): "Pedir confirmaciones", "Exportar", "Asignar responsable".

### States
- Empty (no trips at all): "Todavía no hay viajes. Se crean desde un lead o los arma el agente de ventas." + "Ir a Leads".
- Empty (filters): "Ningún viaje coincide con los filtros." + "Limpiar filtros".
- Loading: 8 skeleton rows; filters stay interactive.
- Error: banner over the table; filters preserved in the URL so reload restores state.

### Interactions
- Filters and view live in the URL (shareable).
- Column sort; column visibility per user.
- Row hover shows a mini timeline preview (days with match icons) after 400 ms.

### Shortcuts
`/` filter, `j/k`, `Enter`, `x` select, `v` cycle views, `n` new trip (from lead picker).

### Density
Compact table default; price column right-aligned USD without decimals ("US$ 2.840").

---

## 3. Detalle de viaje (Trip detail)

**Purpose.** The workspace for one trip: see the whole itinerary, act on each item, know who changed what, and ask the copilot about it.

**Data.** `GET /trips/{id}` (items, providers), `GET /trips/{id}/quote`, lead + contact, `GET /executions?subject=trip:{id}`, audit trail (`audit_log` by subject, see open question), pending approvals for the trip.

### Wireframe
```
VIAJES / SAINT FRANCIS U.
▌SAINT FRANCIS U. · WOMEN'S SOCCER D1                    [Confirmado ▾] [Propuesta ↗] [⋯]
 ● Buenos Aires, Argentina · 26 oct – 4 nov (10 días) · 24 viajeros · Coach: Ann Miller

┌ RESUMEN ─────────────┬──────────────────────┬──────────────────────┬────────────────┐
│ 18/20 CONFIRMADOS    │ PRESUPUESTO vs COTIZ │ PARTIDOS 3 · NIVEL 7 │ FLOWS ACTIVOS 1│
│ ▓▓▓▓▓▓▓▓▓░ 2 pend.   │ 3.000 / 2.840 pp ✓   │ rivales 6–8          │ Pre-salida v3  │
└──────────────────────┴──────────────────────┴──────────────────────┴────────────────┘

[ Itinerario ] [ Proveedores ] [ Actividad ] [ Flows ] [ Cotización ]        ⌘J Preguntar

ITINERARIO                         Filtro: Todos · Pendientes · Partidos     ☐ Mostrar notas
┌ DÍA 1 · LUN 26 OCT ──────────────────────────────────────────────────────────────────┐
│ MAÑANA   ✈ Llegada EZE · Transfer           Transportes RdlP     ✔ Confirmado      │
│ TARDE    🏨 Check-in Palermo Sports Hotel    Palermo Sports       ✔ Confirmado      │
│ NOCHE    — libre —                                                                  │
├ DÍA 2 · MAR 27 OCT ──────────────────────────────────────────────────────────────────┤
│ MAÑANA   ⚽ Entrenamiento con DT AFA          Complejo Costanera   ◷ Pedido · 52 h ⚠ │
│ TARDE    ⚽ PARTIDO vs Deportivo Belgrano Fem. (nivel 7)            ✔ Confirmado     │
│          ✦ Agente de ventas eligió este rival · cambiado por Lucía G. 12/10   [⇄]  │
│ NOCHE    🎭 Tango & asado                    Tango & Fútbol       ○ Pendiente      │
└──────────────────────────────────────────────────────────────────────────────────────┘
…
```

Right column on ≥1440 px (otherwise the "Actividad" tab):
```
ACTIVIDAD                                    Todos ▾ (Personas · Agentes · Flows)
✦ Agente de ventas  propuso el viaje (v1)                         10/10 14:02
👤 Lucía G.          cambió rival día 2: Academia Palermo → Deportivo Belgrano   12/10
⛓ Pre-salida v3     pidió confirmación a 6 proveedores                       20/10 09:00
⌁ Claude Code (MV)  marcó "Transfer EZE" como confirmado                     21/10 18:40
   ↳ "El proveedor confirmó por WhatsApp" · ver traza
```

### Components
- **Header**: country accent rule, team + program in display font, status dropdown (`set_trip_status`; `confirmed`/`cancelled` are gated → opens approval preview, see §6), link to public proposal (signed URL), overflow (duplicate, export PDF, audit export).
- **Summary tiles**: confirmation progress; **budget vs quote** (lead `budget_per_person_usd` vs trip `price_per_person_usd`, green ✓ if within, warning if over, "sin presupuesto" if null; click → Cotización tab); matches count + opponent level range vs team level; active flows.
- **Itinerario tab**: day sections, three slot rows each. Item row = kind icon, title, provider, status badge, age of status ("Pedido · 52 h"), overdue ⚠, actor chip of last change when relevant. Row actions on hover/`.`: "Marcar pedido", "Marcar confirmado", "Agregar nota", "Cambiar rival" (match only), "Cancelar" (gated, destructive).
- **Swap opponent panel** (`⇄`): side sheet with ranked candidates from `POST /catalog/opponents:match` (level, city, description, similarity), current one marked; choosing one calls `swap_opponent` (gated if trip is `confirmed` → creates approval and the row shows "Cambio pendiente de aprobación").
- **Proveedores tab**: providers grouped by kind with items per provider, each provider's confirmation status rolled up, contact, "Pedir confirmación" per provider.
- **Actividad tab / column**: unified feed from `audit_log` + execution events for this trip, filter by actor type, each entry links to trace/execution; before/after diff on expand.
- **Flows tab**: executions with `subject = trip:{id}` (status, current node, waiting on…), "Ejecutar flow…" (manual trigger, `flows:run`).
- **Cotización tab**: breakdown from the pricing snapshot (`trips.pricing`), per-person and total, margin visible to owner only; "Recotizar" creates a new snapshot (internal write) and never changes a sent proposal silently.
- **"Preguntar sobre este viaje"** (⌘J): opens copilot scoped to `trip:{id}` with suggested prompts: "¿Qué falta confirmar?", "Resumí el viaje para el coach", "¿Hay rivales más fuertes disponibles el día 5?".

### Travelers count
Shown as "24 viajeros" from the lead `group_size` (+ staff). Player personal data (names, passports, medical) is **not** shown here and never sent to the copilot (security.md: player data stays in its own encrypted table); a future "Viajeros" tab with restricted access is out of v0.

### States
- Loading: header skeleton + 3 day skeletons.
- Not found / no access: "Este viaje no existe o no tenés acceso." + back to Viajes.
- Draft/proposed trip: banner "Propuesta enviada el 10/10 — el coach todavía no confirmó" with "Reenviar" (gated).
- Cancelled: read-only, grey header, banner with who/when/why.
- Item write error: the row reverts and shows an inline error with retry; other rows unaffected.
- Concurrent edit: if another actor changed the item since load, the action is rejected and the row shows "Lo cambió ✦ Pre-salida v3 hace 1 min — Recargar".

### Interactions
- Click a status badge cycles allowed next states (pending → requested → confirmed); disallowed transitions are not offered.
- Inline notes (Enter to save, autosave on blur).
- Deep links: `/ops/trips/{id}?day=2&item={itemId}` scroll and highlight.

### Shortcuts
`1–5` tabs, `j/k` items, `c` confirm, `p` mark requested, `n` note, `w` swap opponent (match), `⌘J` copilot, `e` open public proposal.

### Density
Compact; slots collapse when empty ("— libre —" single line). Day headers sticky while scrolling.

---

## 4. Leads (pipeline kanban)

**Purpose.** Move inquiries to proposals to won deals; see what the sales agent already did with each lead.

**Data.** `GET /leads?status=` (columns), contact, conversation summary, linked trip.

### Wireframe
```
LEADS                                   [Buscar…/]  Fuente ▾  Deporte ▾  Destino ▾  [+ Lead]

NUEVO (4)          CALIFICADO (6)      PROPUESTA ENVIADA (5)   GANADO (12)     PERDIDO (3)
┌──────────────┐   ┌──────────────┐    ┌──────────────┐        ┌──────────┐    ┌──────────┐
│▌Denver Elite │   │▌Saint Mary's │    │▌Gustavus     │        │ …        │    │ …        │
│ U17 · M Socc.│   │ W Volley D2  │    │ M Soccer D3  │        │          │    │          │
│ ● AR · mar 27│   │ ● BR · jun 27│    │ ● BR · oct 26│        │          │    │          │
│ 22 · US$3.000│   │ 16 · —       │    │ 19 · 3.150 pp│        │          │    │          │
│ ✦ vía chat   │   │ ✦ calificado │    │ enviada hace │        │          │    │          │
│ hace 2 h     │   │ por agente   │    │ 6 días ⚠     │        │          │    │          │
└──────────────┘   └──────────────┘    └──────────────┘        └──────────┘    └──────────┘
```

### Components
- **Columns** = `lead_status` enum. Column header: count + sum of potential revenue (group size × price when known).
- **Lead card**: country accent, organization + program, destination + month, group size + budget, source chip (`chat | webhook | manual | flow`, with ✦ when an agent created/qualified it), age, stale marker (proposal sent > 5 days without reply).
- **Lead drawer** (click): contact (coach name, email, organization), qualification fields (sport, gender, age group, level 1–10 with the level rubric tooltip, dates, duration, budget, goals), **conversation summary** + "Ver conversación", linked trip/proposal, activity feed, actions: "Armar viaje" (`draft_trip`), "Enviar propuesta" (gated → approval), "Marcar ganado/perdido" (with reason).
- Drag between columns = `PATCH /leads/{id}` status; moving to "Propuesta enviada" without a sent proposal is blocked with an explanation.

### States
- Empty pipeline: "Sin leads todavía. Llegan solos desde el chat del coach o un webhook." + "Probar el chat" link.
- Empty column: dashed placeholder, no copy.
- Error on drag: card snaps back with a toast "No se pudo mover: {title}".

### Interactions
- Card quick actions on hover: "Armar viaje", "Abrir conversación".
- Lost requires a reason (select: precio, fechas, eligió otro, sin respuesta, otro).
- A lead qualified by the agent shows the extracted fields with a ✦ marker until a human edits/confirms them ("Revisar datos extraídos").

### Shortcuts
`h/l` move between columns, `j/k` between cards, `Enter` open drawer, `m` move (then column number), `t` armar viaje.

### Density
Cards fixed at 4 lines; columns scroll independently; horizontal scroll on narrow screens.

---

## 5. Proveedores (Providers directory)

**Purpose.** Know who we work with, how to reach them, and how reliable they are.

**Data.** `GET /providers` (+ opponents/experiences as related catalog), derived stats from `trip_items` (requests, confirmations, median confirmation time).

### Wireframe
```
PROVEEDORES                      [Buscar…/]  Tipo ▾  Ciudad ▾  País ▾       [+ Proveedor]

┌───────────────────────────┬───────────┬──────────────┬────────────┬───────────┬──────────┐
│ NOMBRE                    │ TIPO      │ CIUDAD       │ PRECIO     │ CONFIRMA  │ PEND.    │
├───────────────────────────┼───────────┼──────────────┼────────────┼───────────┼──────────┤
│ Palermo Sports Hotel      │ Hotel     │ ● Buenos Aires│ 85 /pers/n│ 96% · 9 h │ 1 ⚠      │
│ Transportes Río de la Plata│Transporte│ ● Buenos Aires│ 30 /pers/d│ 100% · 3 h│ 0        │
│ Barra Athletes Inn        │ Hotel     │ ● Río        │ 95 /pers/n │ 88% · 26 h│ 2        │
└───────────────────────────┴───────────┴──────────────┴────────────┴───────────┴──────────┘
```

Provider detail (side sheet): contact (with copy buttons), unit price + unit, linked clubs/experiences, upcoming items across trips (with status), reliability stats, notes, related documents (contracts from the knowledge base, with "valid until"), activity.

### Components
Filter bar; table; detail sheet; "Pedir confirmación de todo lo pendiente" per provider (write-external → approval policy applies).

### States
- Empty: "Cargá tu primer proveedor o importá un CSV." + "Importar".
- Stats with too few data points show "—" with tooltip "Menos de 3 pedidos".
- Contract expired: warning badge "Contrato vencido" linking to the document.

### Interactions
Inline edit of price/contact for ops+ (internal write, audited, re-indexes catalog via outbox). CSV import with preview and validation errors per row.

### Shortcuts
`/`, `j/k`, `Enter`, `e` edit, `n` new.

### Density
Compact table; numbers right-aligned.

---

## 6. Aprobaciones (Approvals inbox)

**Purpose.** The human gate. Show **exactly** what will execute, who asked for it and why, and let a person approve, reject or edit it. Keep approvals rare and meaningful (security.md: approval fatigue).

**Data.** `GET /approvals?status=pending|approved|rejected|expired`, approval `details` (proposed action + payload), the requesting execution/node or agent run, `POST /approvals/{id}:decide`.

### Wireframe
```
APROBACIONES          Pendientes (2) · Resueltas · Vencidas          Asignadas a: ops ▾

┌ LISTA ─────────────────────────────┐ ┌ DETALLE ──────────────────────────────────────────┐
│● Enviar propuesta a Ann Miller     │ │ ENVIAR PROPUESTA AL COACH            vence en 3 h │
│  Lakeshore U. · ⛓ Consulta v2  │ │ Pedido por ⛓ Consulta entrante v2 · nodo          │
│  vence en 3 h                      │ │ "Aprobación de ops" · ejecución #8f2c ↗           │
│                                    │ │                                                    │
│○ Cancelar ítem "Tigre Delta"       │ │ QUÉ VA A PASAR                                     │
│  Gustavus · ⌁ Claude Code (MV)     │ │ Se envía un email a ann.miller@sfu.example con el │
│  vence mañana                      │ │ link de la propuesta (US$ 2.840 pp, 10 días, BA). │
└────────────────────────────────────┘ │                                                    │
                                       │ CAMBIOS                         [Diff] [JSON]      │
                                       │ trip.status      proposed  →  proposed (sin cambio)│
                                       │ email.to         —         →  ann.miller@sfu…      │
                                       │ email.subject    —         →  "Your Buenos Aires…" │
                                       │ email.body       ▸ ver mensaje (preview)           │
                                       │                                                    │
                                       │ POR QUÉ (del agente)                               │
                                       │ "El coach confirmó fechas y presupuesto; los 3     │
                                       │  rivales están dentro de ±1 nivel." ✦ ver traza    │
                                       │                                                    │
                                       │ Huella del pedido  sha256:3f9a…c21e  ⧉             │
                                       │                                                    │
                                       │ Comentario (opcional) [______________________]     │
                                       │ [Rechazar]   [Editar y aprobar]   [Aprobar ⏎]      │
                                       └────────────────────────────────────────────────────┘
```

### Components
- **List**: pending first, sorted by `expires_at`; each item: action title (verb first), subject, requester actor chip, expiry countdown, risk class badge (`Externo`, `Destructivo`).
- **Detail**:
  - **"Qué va a pasar"**: plain-language sentence generated from the action type template (not by the LLM), so the human reads deterministic copy.
  - **Cambios**: before → after diff of the exact payload; toggle raw JSON. Customer-facing messages render as a preview of what the recipient sees.
  - **"Por qué"**: the agent's stated rationale, marked as model output, with link to the trace. Never the only basis: the diff is.
  - **Huella del pedido** (payload hash): `sha256` of the canonical payload, copyable. The decision is bound to this hash (security.md §3.2).
  - **Editar y aprobar**: edits the payload in a form generated from the action schema; on save the hash changes, the edited version is shown side by side and the user must approve the new version explicitly (a new approval record linked to the original).
  - Decision buttons: Rechazar (comment required), Aprobar. Enter = Aprobar only after the detail has been on screen ≥ 1.5 s and the diff scrolled into view (prevents rubber-stamping).
- **Resueltas / Vencidas** tabs: history with decider, time, comment and outcome of the resumed execution.

### States
- Empty: "No hay nada para aprobar. Los agentes solo te piden permiso para acciones externas o destructivas."
- Expired while open: banner "Venció a las 14:00 — el flow siguió por la rama 'expirado'". Buttons disabled.
- Already decided by someone else: banner with who/when; buttons disabled.
- Payload changed since load (hash mismatch from server): "El pedido cambió desde que lo abriste" + reload; the old decision is never applied.
- Decision error: stays on the item, inline error, nothing optimistic.

### Interactions
- After a decision, focus moves to the next pending item.
- Bulk approve is **not** offered for external/destructive classes.
- Notifications: new approval for my role → badge + optional browser notification.

### Shortcuts
`j/k` list, `⏎` approve (with the guard above), `r` reject (focus comment), `e` edit, `t` open trace, `Esc` back to list.

### Density
Two-pane at ≥1280 px; single pane with back navigation below.

---

## 7. Conocimiento (Knowledge base)

**Purpose.** Manage what the agents know and verify it: upload documents, watch ingestion, and test questions with citations before trusting the agents.

**Data.** `GET /documents`, `GET /ingestion-jobs/{id}`, `POST /documents:upload-url` → `POST /documents/{id}:ingest`, `DELETE /documents/{id}`, `POST /search` (`{query, filters, k, rerank}`).

### Wireframe
```
CONOCIMIENTO                 [Buscar…/]  Tipo ▾  País ▾  Estado ▾         [⇡ Subir documentos]

┌ DOCUMENTOS ─────────────────────────────────────────────────────────────────────────────┐
│ TÍTULO                         │ TIPO      │ META            │ ESTADO        │ CHUNKS │   │
│ Política de cancelación 2027   │ Política  │ —               │ ✔ Listo       │ 4      │ ⋯ │
│ Contrato Palermo Sports Hotel  │ Contrato  │ BA · vence 3/27 │ ✔ Listo       │ 22     │ ⋯ │
│ Guía Río para equipos          │ Guía      │ Río             │ ◌ Embeddings… │ ▓▓▓░ 61%│   │
│ Reporte gira Gustavus 2025     │ Reporte   │ BA              │ ✖ Falló parse │ —      │ ↻ │
│ Mail proveedor (sospechoso)    │ Email     │ —               │ ⚑ Cuarentena 3│ 9      │ ⋯ │
└─────────────────────────────────────────────────────────────────────────────────────────┘

┌ PROBAR UNA PREGUNTA ────────────────────────────────────────────────────────────────────┐
│ [¿Los ciudadanos de EE.UU. necesitan visa para Brasil?          ]  Rerank ☑  k=5  [→]  │
│                                                                                         │
│ 1  0.82  Requisitos de ingreso para ciudadanos de EE.UU.  · Política · ¶2              │
│    "…Brazil: US citizens need an electronic visa (e-visa) applied online before…"  ↗   │
│ 2  0.61  Mejor época para viajar · Política · ¶1                                    ↗   │
│ …                                                                                       │
│ ☐ Mostrar respuesta del agente con citas                                                │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

### Components
- **Upload**: drag-and-drop zone (PDF, DOCX, HTML, EML, MD), metadata form per file (type, country, city, provider, valid until), signed URL upload with per-file progress, duplicate detection by content hash ("Ya existe: {título}").
- **Documents table** with status from `documents.status` and the live ingestion stage from `ingestion_jobs.status` (`queued → parsing → chunking → embedding → indexing → succeeded/failed`) as a stage stepper on hover/detail; chunk count; embedding model.
- **Document detail** (sheet): metadata, version history (re-uploads), stage timings (`stats`), chunks list with text preview, **quarantined chunks** (security.md §3.1 ingestion hygiene) with "Revisar": show the flagged text and reason; actions "Liberar" / "Mantener en cuarentena" (audited).
- **Probar una pregunta** (retrieval playground): query, filters (type/country/city), rerank toggle, `k`; results = rank, score, document title, type, location (paragraph/page), highlighted passage, open source at the cited spot. Optional "respuesta del agente con citas" (answer + numbered citations; uncited sentences visually flagged).
- "Agregar a evals" on a tested question: saves query + expected document to the retrieval golden set (feeds evals-and-testing.md).

### States
- Empty: "Subí políticas, contratos y guías: los agentes responden solo con lo que está acá." + upload.
- Ingestion failed: row error with stage and message, "Reintentar" (new job), "Ver detalle".
- Search with no results: "Sin resultados relevantes (umbral 0.35). Puede que falte un documento." + "Subir documento".
- Search error: inline in the playground; table unaffected.

### Interactions
- Status updates live while any document is ingesting (poll job every 2 s, stop when terminal).
- Delete = soft delete with confirmation listing chunk count; removes vectors asynchronously; audited.

### Shortcuts
`u` upload, `/` filter, `q` focus "Probar una pregunta", `Enter` run query, `j/k` results.

### Density
Compact table; playground results 3 lines each, expandable.

---

## 8. Component inventory (for the design system)

| Component | Used in | Notes |
|---|---|---|
| `AppShell` (sidebar, top bar, copilot slot) | all | collapsible sidebar, live counts |
| `PageHeader` (eyebrow, H1 display, meta line, actions) | all | country accent rule optional |
| `KpiTile` | Hoy, Trip detail | display-font number, context line, click-to-filter |
| `StatusBadge` | all | token per status table §0.3, icon + label |
| `ActorChip` | all | person / agent / flow / MCP / system |
| `CountryChip` + accent rule | Viajes, Trip, Leads, Providers | |
| `DataTable` (sort, column visibility, density, bulk select, URL state) | Viajes, Providers, Knowledge | keyboard navigable |
| `FilterBar` + saved views | lists | |
| `Timeline` (day / slot / item rows) | Trip detail | sticky day headers |
| `ActivityFeed` (audit + executions) | Trip, Lead drawer, Provider | filter by actor type, before/after expand |
| `Kanban` | Leads | drag with keyboard alternative (`m`) |
| `SideSheet` | swap opponent, provider, document, lead | |
| `DiffView` (fields + JSON + message preview) | Approvals | |
| `HashBadge` | Approvals | copy, monospace |
| `StageStepper` | Knowledge | ingestion stages |
| `UploadDropzone` | Knowledge | signed URL, per-file progress |
| `CitationList` | Knowledge playground, copilot | rank, score, passage, deep link |
| `EmptyState`, `ErrorBanner` (with trace id), `Skeleton*` | all | |
| `CommandPalette`, `ShortcutSheet` | global | |

All interactive components: visible focus ring (`ring` token), ≥ 32 px hit targets in compact density, full keyboard support, `aria-live="polite"` for queue and ingestion updates.

---

## 9. Gaps found against the current data model / API

These are needed by the screens above and are not yet in [data-model.md](../architecture/data-model.md) / [core-api.md](../architecture/core-api.md):

1. **`approvals.payload_hash` and `approvals.proposed_action jsonb`** (action type + canonical payload) — security.md binds decisions to a hash, but the table only has `details`. Also `risk_class` (`write-external | destructive`) and `superseded_by` for "Editar y aprobar".
2. **Audit trail per subject**: no `GET /audit?subject_type=&subject_id=` endpoint; Trip/Lead/Provider activity feeds need it (merged with executions).
3. **Item status timestamps**: only `confirmed_at` exists; "Pedido · 52 h" needs `requested_at` (or derive from audit).
4. **Trip list aggregates**: `items_confirmed`, `items_total`, `at_risk` should come computed from `GET /trips` (avoid N+1 from the web).
5. **Incidents**: no table; v0 derives them from failed executions + overdue unconfirmed items. A real `incidents` entity (on-trip issues: injury, bus late) is out of v0.
6. **Provider reliability stats**: derived from `trip_items`; needs an endpoint (`GET /providers/{id}/stats`) or a materialized view.
7. **Today queue**: a single `GET /ops/queue` endpoint that ranks items server-side would keep ranking logic testable and consistent with the copilot's "¿qué tengo pendiente?".
8. **Travelers count**: from `leads.group_size`; staff count not modeled.
9. **Quarantine**: `document_chunks` needs `quarantined boolean` + `quarantine_reason` (security.md mentions it; data-model.md doesn't list it).
10. **Lost reason** on leads (`lost_reason`).

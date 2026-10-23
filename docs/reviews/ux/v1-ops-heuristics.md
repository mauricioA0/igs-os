# V1 — Ops panel: heuristic evaluation + WCAG 2.2 AA spot audit

Reviewer: V1 (senior UX). Date: 2026-10-22. Scope: the clickable ops prototype (`apps/web/src/app/(prototype)/ops/**`), mock data.
Pages: `/ops`, `/ops/trips`, `/ops/trips/t-2711`, `/ops/approvals`, `/ops/leads`, `/ops/accounts`, `/ops/accounts/acc-lakeshore`.
Baseline: `docs/design/ops-panel.md`, `docs/design/content-and-accessibility.md`.

Method: Next dev server, headless Chromium 1440×900 (light + dark) and 390×844 (mobile), axe-core 4.10 (wcag2a/2aa/21aa/22aa + best-practice), scripted Tab walk (25 stops per page), console capture. Screenshots live in the session scratchpad `…/scratchpad/ux-v1/` and are referenced by filename (`<page>-<light|dark|mobile>.png`). Automated checks cover a fraction of WCAG; everything else below is manual judgement.

**Overall:** the panel already does the hard things right — the approvals screen shows *exactly* what will happen with a message preview and a payload hash, every agent action is attributed, statuses always carry text (never colour alone), and dark mode holds up. The problems are mostly about **scale and the field** (a coordinator on the ground with a phone), **consistency of the copy**, and a handful of real a11y failures that are cheap to fix now.

## Severity scale
- **S1 Blocker** — breaks a core task or a WCAG A/AA criterion for some users.
- **S2 Major** — slows the core loop or erodes trust in the agent output.
- **S3 Minor** — polish, consistency.

## Findings

### S1 — Blockers

| # | Finding | Where | Heuristic / WCAG |
|---|---|---|---|
| 1 | `<html lang="en">` on a Spanish UI. Screen readers read "Buen día, Lucía" with English phonetics; hyphenation and spellcheck also wrong. (`apps/web/src/app/layout.tsx:30`; coach pages are English, ops are Spanish — needs per-route `lang`.) | all ops pages (`audit.json`) | WCAG 3.1.1 Language of Page (A) |
| 2 | Mobile ops is unusable: the full sidebar renders above the content and eats the first screen; no collapsible nav, no bottom bar. The persona that most needs mobile is the coordinator *on tour*. | `ops-home-mobile.png`, `trip-t2711-mobile.png` | Flexibility & efficiency; WCAG 1.4.10 Reflow passes (no h-scroll) but the task fails |
| 3 | Hydration error on the account page (Next dev overlay "1 Issue", console: *"server rendered text didn't match the client"*). Likely `Intl` es-AR time strings ("04:30 p. m.") formatted differently by Node ICU vs Chrome in a client component (`ops/accounts/[id]/_timeline.tsx` / `_mock/format.ts`). Cause not verified. In prod this re-renders the tree on load (flash + lost focus). | `account-lakeshore-light.png` (bottom-left badge) | Error prevention / visibility of system status |
| 4 | Citation links have no accessible name beyond "[4]", "[5]" — Tab walk on the account page lands on a run of identical-sounding links. | `/ops/accounts/acc-lakeshore` tab stops | WCAG 2.4.4 Link Purpose (A) |
| 5 | Colour contrast failures: lost-lead cards use `opacity-70` over muted text → **3.24:1** (6 nodes); amber "ATENCIÓN" health badge **4.42:1** at 8.3 pt. | `leads-light.png` (Perdido column), `account-lakeshore-light.png` header | WCAG 1.4.3 Contrast (AA) |

### S2 — Major

| # | Finding | Where | Heuristic |
|---|---|---|---|
| 6 | Trips table rows: links inside rows (IGS-27xx) show **no visible focus** (9 stops with `outline: none` and no ring). | `/ops/trips` tab walk | WCAG 2.4.7 Focus Visible (AA) / 2.4.11 |
| 7 | No skip link: every page starts with 7 sidebar stops before content. | all pages tab walk | WCAG 2.4.1 Bypass Blocks (A) |
| 8 | Leads kanban overflows at 1440 px: the "Perdido" column is clipped with no scroll affordance or column collapse. | `leads-light.png` right edge | Visibility; aesthetic & minimalist |
| 9 | Trip detail: every confirmed item shows a "Reabrir" button at the same weight as "Confirmar". 10 of 13 items carry an action that *undoes* confirmed work, one click away, no confirm, no undo. | `trip-t2711-light.png` | Error prevention |
| 10 | Inconsistent button order in item actions: "Confirmar · Volver a pendiente" (primary left) vs "Marcar solicitado · Confirmar" (primary right). Muscle memory will misclick. | `trip-t2711-light.png` D1 vs D4 | Consistency & standards |
| 11 | Approvals: no "Editar y aprobar" (spec'd in ops-panel.md), no stated outcome on expiry ("vence en 47 h" → then what?), no keyboard shortcuts despite a queue workflow. | `approvals-light.png` | User control & freedom; efficiency |
| 12 | Home duplicates the same alerts in two places (Northfield card *and* "Atención · 5"), and the activity feed uses unexplained avatars `IA` / `FL` / `OP`. | `ops-home-light.png` | Minimalist design; recognition over recall |
| 13 | KPI copy is ambiguous: "SIN CONFIRMAR 10 — ítems de giras confirmadas". KPIs aren't links to the filtered list. | `ops-home-light.png` | Match with the real world; efficiency |

### S3 — Minor

| # | Finding | Where |
|---|---|---|
| 14 | Destination cell breaks into "Buenos / Aires · / Argentina" across lines; trip code wraps "IGS-/2709". Same on the trip header ("DESTINO"). | `trips-light.png`, `trip-t2711-light.png` |
| 15 | Mixed languages and grammar in Spanish UI: provider kinds "Transport / Hotel / Venue / Guide / Referee"; "1 ABIERTOS"; "HUMAN IN THE LOOP" eyebrow on Aprobaciones. | `trip-t2711-light.png`, `approvals-light.png` |
| 16 | Currency format drifts: "US$ 2.890" (trips/home) vs "USD 2.890" (approvals). content-and-accessibility.md mandates **US$** for es-AR. | `approvals-light.png` |
| 17 | Sidebar background stops at viewport height on long pages (white panel ends at ~900 px, both themes). | `trip-t2711-light.png`, `approvals-dark.png` |
| 18 | Lead cards: coloured dots (dark/light blue, green) with no legend. | `leads-light.png` |
| 19 | Account timeline citation numbers appear out of order ([2],[3],[6],[5],[4],[1]) because the list is reverse-chronological; readers scanning for "[1]" go to the bottom. | `account-lakeshore-light.png` |
| 20 | Landmarks: two `<aside>` without labels on home and trip pages (axe `landmark-unique`). | `audit.json` |

What already works (keep): status badges always text + colour; "Qué se va a hacer" + message preview + payload hash on approvals; attribution on every activity row; "Último contacto hace 64 días" highlighted on stakeholders; filters as segmented buttons with counts; no horizontal scroll on mobile; dark theme contrast in the approvals flow.

## Proposals

### P1 — "Field mode": mobile ops for the coordinator on tour (fixes #2, #7)
**Problem.** During a tour the coordinator lives on the phone; today the phone shows a sidebar.
**Proposal.** Below 768 px: hide the sidebar, add a bottom tab bar (Hoy · Aprobaciones · Gira actual · Copiloto), and make "Hoy" default to *the trip in progress* (today/tomorrow items, one-tap confirm, call the provider). Add a skip link on desktop.

```
┌──────────────────────────┐
│ EN CURSO · DÍA 5 DE 10   │
│ NORTHFIELD · BUENOS AIRES│
├──────────────────────────┤
│ HOY                      │
│ 09:30 Sesión táctica  ✓  │
│ 15:00 Tour Monumental ✓  │
│ 20:00 Tango y asado   ⚠  │
│  El proveedor no confirmó│
│  [ Llamar ] [ Confirmar ]│
│ MAÑANA                   │
│ 17:00 vs Palermo FC   ⚠  │
│  Falta árbitro           │
├──────────────────────────┤
│ Hoy  Aprob(4)  Gira  IA  │
└──────────────────────────┘
```
**Impact:** high — it's the moment the product proves itself (on-tour incident journey). **Effort:** M (layout + one new view reusing trip-item components).

### P2 — Approvals as a keyboard-first queue with edit-and-approve (fixes #11)
**Problem.** Approvals is the heart of the product but it's a one-at-a-time mouse flow; editing means rejecting and waiting.
**Proposal.** `J/K` move, `A` approve, `R` reject (requires reason), `E` edit-and-approve (inline-editable preview; editing creates a superseding approval with a new hash, shown as a diff). Show the expiry outcome next to the timer ("si vence: el flow escala a Martín"). Keep the no-bulk-approve rule for external actions.

```
┌ Pendientes · 4 ─────────┐ ┌ ENVIAR PROPUESTA A BROOKFIELD ─────────────┐
│▶ SALE AFUERA  47 h      │ │ Si vence: escala a Martín Ríos              │
│  Enviar propuesta…      │ │ ┌ Vista previa (editable) ───────────────┐ │
│  INTERNO      4 h       │ │ │ Hi Coach Okafor, … Price: US$ 2,890 …  │ │
│  Mover partido 18:30    │ │ └────────────────────────────────────────┘ │
│  …                      │ │ hash 7f3a9c2e → (editado) b81e04d1  diff ▸ │
│ J/K mover               │ │ [A Aprobar y enviar] [E Editar] [R Rechazar]│
└─────────────────────────┘ └────────────────────────────────────────────┘
```
**Impact:** high — throughput of the human-in-the-loop, and the strongest demo moment. **Effort:** M.

### P3 — Accessible, trustworthy citations (fixes #4, #19)
**Problem.** "[4][5]" links are unreadable to assistive tech and hard to map for everyone.
**Proposal.** Render citations as chips with channel + date + who ("Email · 15 oct · Karen Liu"), `aria-label` "Fuente: email de Karen Liu del 15 de octubre"; hovering/focusing a chip previews the quoted passage; numbering follows the order in the brief, not the timeline.

```
…pidió prórroga hasta el 31 de octubre [✉ 15 oct · Karen Liu]. La coach pidió
un rival de nivel 7 [☎ 21 oct · Dana Whitfield]…
        ┌──────────────────────────────────────────────┐
        │ ✉ Re: saldo de la gira IGS-2711 · 15 oct      │
        │ "…move the balance due date to October 31…"   │
        │ Abrir en línea de tiempo →                    │
        └──────────────────────────────────────────────┘
```
**Impact:** high for trust in Account 360 + fixes an A-level failure. **Effort:** S.

### P4 — Safer trip-item actions (fixes #9, #10)
**Problem.** "Reabrir" on every confirmed item, inconsistent button order.
**Proposal.** One rule everywhere: primary action on the right. Confirmed items show only status + an overflow menu (`⋯ → Reabrir`, with a reason and undo toast). Pending items: `[Marcar solicitado] [Confirmar]`.
```
│ Llegada a Ezeiza y traslado     CONFIRMADO  ⋯ │
│ Clínica comunitaria  PENDIENTE [Solicitado][Confirmar] │
```
**Impact:** medium-high (prevents silent regressions in confirmations). **Effort:** S.

### P5 — One "Hoy" queue instead of duplicated widgets (fixes #12, #13)
**Problem.** Alerts appear twice; KPI copy is ambiguous and not actionable; activity avatars are cryptic.
**Proposal.** Merge trip alerts + approvals into a single ranked queue ("Lo que necesita tu decisión hoy"), each row with its source; KPIs become links ("10 ítems sin confirmar →" opens `/ops/trips?f=sin-confirmar`); replace `IA/FL/OP` with icon + label ("Agente", "Flow", "Persona").
**Impact:** medium. **Effort:** S–M.

### P6 — Quick a11y and copy pass (fixes #1, #5, #6, #14–18, #20)
`lang="es"` on ops routes (`en` on coach routes); contrast: drop `opacity-70` on lost cards (use muted text token at ≥4.5:1) and darken the warning badge foreground; visible focus ring on table row links; skip link; label the asides; `whitespace-nowrap` on codes/destinations; Spanish provider kinds and plurals; US$ everywhere; full-height sidebar; legend for lead dots. **Impact:** medium (unblocks AA). **Effort:** S (≈ one PR).

## Suggested order
P6 (cheap, unblocks AA) → P3 → P4 → P2 → P1 → P5. Fix #3 (hydration) before any demo recording — the dev overlay badge is visible in screen captures.

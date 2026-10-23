# V5 — Visual system review

Scope: visual consistency of the web prototypes against the design system (`apps/web/src/app/globals.css`, `src/components/ui`, `docs/design/brand-reference.md`), plus a benchmark against best-in-class ops/AI products. Read-only review, 2026-10-22.

Method: dev server (shared instance on :3203), Playwright screenshots of 14 routes × light/dark at 1440×900 and 3 routes at 390×844 (stored in the session scratchpad `ux-v5/`), plus a code audit of private styles.

## 1. What already works

- **The ops shell has a real identity.** Barlow Condensed uppercase headings, cream background, black active nav item and tight 4px corners read as Infinity Global Sports, not as a generic shadcn admin. `BUEN DÍA, LUCÍA` + KPI tiles + "Esperan tu aprobación" is a strong Today screen.
- **The proposal is the best screen in the product.** Dark editorial hero, country-blue rule under the hero, stat strip, the brand triplets as section titles. It looks like the marketing site, which is exactly the goal for coach-facing surfaces.
- **The Account 360 page communicates trust.** The summary with inline citations `[4][5]`, stakeholder cards with influence dots and "Último contacto hace 64 días" in warning colour are the right visual language for an AI product.
- **Dark mode is coherent on ops and /design**, and the status palette in /design (success/warning/danger/info + country accents) is well balanced in both themes.

## 2. Findings

| # | Finding | Evidence | Severity |
|---|---|---|---|
| F1 | **Two different apps.** Ops uses a left sidebar with the `INFINITY / GLOBAL SPORTS · OS` lockup and Spanish copy; Flows uses a top bar with an `IGS·OS FLOWS` wordmark, no sidebar and English copy. Clicking "Flows" in the ops sidebar drops you into another product. | `ops-light.png` vs `flows_inbound-inquiry-light.png` | High |
| F2 | **Private palettes bypass the tokens.** `flows/flows.css` redefines the whole theme as `--fx-*` (bg, fg, card, border, primary…) instead of using `globals.css`. Its dark mode only follows `prefers-color-scheme`, so the `.dark`/`.light` class toggle from /design doesn't reach Flows. Proposal and chat use 10 and 12 unique arbitrary colours respectively (`bg-[#…]`, `hsl(…)` in classes). Only ops imports `@/components/ui` (9 imports); proposal, chat and flows import none. | code audit | High |
| F3 | **Rainbow node categories.** Flow nodes colour-code by category (AI purple `258 52% 52%`, conversation blue, integration green, human orange). This contradicts `docs/design/flow-editor.md` ("shape per category, colour reserved for state") and the brand rule "colour comes from country accents and imagery, not the chrome". In the execution viewer, category colours and state colours (green/red/amber) compete. | `flows_inbound-inquiry-*.png`, `flows.css` | Medium |
| F4 | **Off-brand action hierarchy.** The execution viewer's primary action is a saturated green `Approve` button; elsewhere primary actions are black (light) / white (dark). Three button languages coexist: black primary, outlined secondary, green success. | `flows_…executions_ex-7f3a-dark.png` | Medium |
| F5 | **Unreadable canvas at "fit".** At the default zoom the 20+ node inbound flow renders node titles around 6–7px; the minimap is a solid grey block over the canvas. The first impression of the flagship feature is "tiny boxes". | `flows_inbound-inquiry-light.png` | High (demo impact) |
| F6 | **The timeline says nothing.** Execution timeline bars are all green on a log scale; a 7-minute agent turn and a 2ms set node look similar; waits and approvals are not visually distinct from work. | `…executions_ex-7f3a-dark.png` | Medium |
| F7 | **Off-scale type.** 31 arbitrary font sizes (`text-[11px]` ×20, `text-[10px]` ×7, `text-[9px]` ×2, 13px, 15px). 9–10px is below the legibility floor for an ops tool and won't pass WCAG zoom expectations comfortably. There is no `2xs` step in the scale. | code audit | Medium |
| F8 | **Mobile ops is a desktop page stacked.** At 390px the full sidebar renders above the content; the Today screen starts below the fold. | `m-ops.png` | Medium |
| F9 | **No loading, empty or streaming states in the prototypes.** `Skeleton` and `EmptyState` exist in `components/ui` but no prototype route uses them; motion is ad-hoc (26 `transition`/`animate-` usages, no shared durations or easings). | code audit | Low (prototype) → High (real API) |
| F10 | **Badge zoo.** Uppercase outlined badges (`DECIDE`, `ATHLETIC DIRECTOR`), filled status badges (`SALE AFUERA`, `ATENCIÓN`) and coloured chips (`RIESGO`, `COMPROMISO`) use different shapes for the same "label" role on one page. | `ops_accounts_…-light.png` | Low |

Dev-only noise seen in screenshots (Next.js dev indicator overlapping the sidebar user block, "1 Issue" toast on the account page) is not part of the product, but the issue on the account route is worth checking in the dev overlay.

## 3. Benchmark — what best-in-class does that we don't yet

| Product | Pattern worth taking | Gap in IGS OS |
|---|---|---|
| **Linear** | Theme generated from 3 inputs (base, accent, contrast) in a perceptual colour space (LCH); the 2024 redesign cut ~98 theme variables to 3 and reduced chrome noise to raise hierarchy and density. | We hand-maintain HSL tokens twice (globals + `--fx-*`), no contrast control. |
| **Vercel (Geist)** | 10-step grey and accent scales with fixed roles per step (backgrounds 100–200, borders 400–600, text 900–1000); borders as hairlines. | Our greys are single tokens (`muted`, `border`, `accent`) — not enough steps for dense UIs like the canvas and tables. |
| **Attio** | Record pages: one consistent header (identity, status, owner), attributes as a quiet two-column list, everything else as tabs/timeline; dense tables with inline editing. | Account and trip pages each invented their own header. |
| **Superhuman** | Keyboard-first: every action has a shortcut shown inline; speed as a feature; the command palette is the product. | Shortcuts are specified in `ops-panel.md` but no `Kbd` hints appear in the UI. |
| **Notion AI** | AI-authored content is visibly marked in place (subtle mark + "AI" provenance), with accept/discard right there. | AI provenance is shown differently on each screen ("IA" square in Today, sparkle icon in Account summary, "Agente de …" text in approvals). |

Sources: [Linear — How we redesigned the Linear UI](https://linear.app/now/how-we-redesigned-the-linear-ui), [sspai on Linear's LCH themes](https://sspai.com/post/104449), [Vercel Geist](https://vercel.com/geist), [Vercel design.md](https://vercel.com/design.md).

## 4. Proposals

### P1 — One shell, one wordmark (fixes F1, F8) · Impact high · Effort S–M

Move Flows inside the ops layout. The sidebar becomes the only global navigation; Flows gets a full-bleed canvas page inside it (sidebar collapsible to icons with `[`). One wordmark everywhere: `IGS OS` in Barlow Condensed with the country-accent dot, `INFINITY GLOBAL SPORTS` only on coach-facing pages. Ops copy in Spanish, including Flows ("Flujos", "Publicar v8", "Validar").

```
┌──────┬───────────────────────────────────────────────────────────┐
│ IGS● │ ← Flujos   CONSULTA ENTRANTE   v7 publicada  Borrador · 2  │
│  OS  │                                   [Validar] [Publicar v8] │
│ ▣ Hoy├──────────┬─────────────────────────────────┬──────────────┤
│ ✓ Apr│ Nodos    │            canvas               │  Inspector   │
│ ✈ Gir│          │                                 │              │
│ ☷ Cli│          │                                 │              │
│ ⧉ Flu│          │                                 │              │
└──────┴──────────┴─────────────────────────────────┴──────────────┘
mobile (<768px): sidebar → bottom tab bar (Hoy · Aprobaciones · Giras · Clientes · Más)
```

### P2 — Token consolidation + generated scales (fixes F2, F7, F10) · Impact high · Effort M

1. Delete `--fx-*` and arbitrary colours; Flows, chat and proposal consume `globals.css` tokens and `components/ui`. Dark mode via the shared `.dark` class strategy only.
2. Generate the neutral and accent ramps in **OKLCH** from three inputs, Linear-style, and expose Geist-style 10-step scales with fixed roles:

```css
/* inputs */
--base-hue: 70;        /* warm cream neutral, from brand 40 7% 95% */
--accent: oklch(0.72 0.08 245);   /* argentina blue */
--contrast: 1;         /* 0 = low, 1 = default, 2 = high-contrast mode */

/* generated (example light values) */
--gray-1:  oklch(0.975 0.004 var(--base-hue));  /* app bg (cream)      */
--gray-2:  oklch(0.955 0.005 var(--base-hue));  /* subtle bg, canvas   */
--gray-4:  oklch(0.90  0.006 var(--base-hue));  /* hover, chips        */
--gray-6:  oklch(0.84  0.006 var(--base-hue));  /* borders             */
--gray-8:  oklch(0.62  0.006 var(--base-hue));  /* placeholder, icons  */
--gray-11: oklch(0.45  0.005 var(--base-hue));  /* muted text (AA)     */
--gray-12: oklch(0.20  0.004 var(--base-hue));  /* text                */
/* semantic tokens keep their names and point at steps */
--muted-foreground: var(--gray-11);
--border: var(--gray-6);
```

3. Type scale: add `--text-2xs: 0.6875rem` (11px) as the floor, ban `text-[9px]`/`[10px]` via a lint rule (`no-restricted-syntax` on class strings), map the 20 `text-[11px]` to `text-2xs`.
4. One `Badge` with three variants only: `label` (outlined, uppercase eyebrow), `status` (dot + text, colour = state), `kind` (filled neutral). Risk/commitment/decision become `kind` with an icon, not a colour.

Impact: one theme to tune, high-contrast mode for free (`--contrast: 2`), Flows follows the theme toggle, ~70 arbitrary values removed.

### P3 — Calm canvas: shape for category, colour for state, semantic zoom (fixes F3, F5, F6) · Impact high (demo) · Effort M

- Category = **shape + glyph**, never colour: AI nodes have a notched corner and ✦ glyph, conversation nodes a speech-bubble tail, logic nodes are diamonds/compact, human approval nodes have a thick black top rule (the brand's "decision" mark). All nodes monochrome on cream.
- Colour only for **runtime state**, and only in the execution viewer: left 3px bar + dot (success/warning/danger/info).
- **Semantic zoom**: below 70% zoom, nodes collapse to readable pills (`✦ Calificar consulta`) at ≥12px; full cards above 70%. Default view fits the *happy path*, not the whole graph.
- Minimap → thin outline strip with the viewport frame, same tokens.
- Timeline: bars coloured by state; waits/approvals rendered hatched with their wall-clock label ("esperando a Lucía · 21 h"), compute shown solid. Time axis linear within "work", compressed across waits.

```
Light, zoom 60%:                         Execution, same flow:
 ( ✦ Calificar consulta )                 ▌● ✦ Calificar consulta    7 min
        │                                 ▌● ▶ Crear lead            84 ms
 [ ▶ Crear lead ]                         ▌◐ ▀ Revisión de ops  ░░░░ esperando 21 h
        │                                     (approved ▸ rejected ▸ expired)
 ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀
 [ Revisión de ops ]  ← black top rule = human decision
```

### P4 — One action language + AI ink (fixes F4, Notion gap) · Impact medium · Effort S

- Buttons: `primary` (black/white), `secondary` (outlined), `ghost`, `destructive` (outlined red text, filled only inside confirmation dialogs). No green buttons; "Aprobar" is primary, the success state shows after the action.
- **AI ink**: one consistent mark for anything an agent wrote or proposed — a 2px left rule in the accent colour + `IA` eyebrow + source/agent name on hover, applied to summaries, activity feed, approval payloads, chat bubbles from the concierge, and copilot answers. Human-authored content never gets it. This replaces the three current AI markers.

```
▎IA · Agente de operaciones · hace 17 min
▎Detectó que Árbitros AFA no tiene terna a las 17:00 y pidió
▎aprobación para mover el partido a las 18:30.   [Ver traza]
```

### P5 — States & motion tokens (fixes F9) · Impact medium (high once the API is real) · Effort S

Shared `--duration-fast: 120ms`, `--duration-base: 200ms`, `--ease-out: cubic-bezier(.2,.8,.2,1)`; every list/page gets `Skeleton` and `EmptyState` from `components/ui`; streaming text uses a single caret style (the chat's block caret) and a "pensando…" shimmer on the AI-ink rule; all honour `prefers-reduced-motion`. Keyboard hints rendered with `Kbd` next to primary actions (`Aprobar ⏎`, `Rechazar ⌫`, `⌘K`), Superhuman-style.

### P6 — Signature idea: **"La Tira" — every tour is a strip** · Impact very high (memorability) · Effort M

Take the proposal's best element — the dark hero with the thin country-colour rule — and make it IGS OS's signature object: **a horizontal day strip for every tour**, the same component everywhere a tour appears.

- Day 1 … N as segments; the segment fill encodes the day type (travel, match, training, experience, free) in monochrome patterns; the top rule is the destination's country accent (Argentina blue, Brazil green/gold, Costa Rica blue, Spain gold).
- Today's position is a stadium-scoreboard marker (`DÍA 5/10`) in Barlow Condensed.
- Status dots appear *on the strip* where something needs attention (unconfirmed referee on day 6, approval pending on day 8).
- Scales from a 4px sparkline (trip list rows, account timeline) to a full-width interactive strip (trip detail, proposal hero, Today's "en curso" card, execution viewer for trip-scoped flows).

```
NORTHFIELD COLLEGE · MEN'S SOCCER                         DÍA 5/10
▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔ (argentina blue)
│ ✈ │ ⚽ │ ◎ │ ⚽ │▐█▌│ ⚽●│ ★ │ ⚽ │ ◎ │ ✈ │
  1   2   3   4   5   6   7   8   9   10
                  ▲ hoy      ● falta árbitro

trip list row:  LAKESHORE · BA   ▁▃▁▃▁▅▁▃▁▁  dia −23   ● 2
```

Why it works: it is unmistakably *sports-tour* (not a generic SaaS timeline), it reuses the brand's own visual device, it compresses the product's core object into a glance, and it gives the demo a recognisable thread from coach proposal → ops Today → execution. It also becomes a natural OG image and PDF header.

## 5. Suggested order

1. P2 (tokens) — unblocks everything else; do it before wiring real data in phase 5.
2. P1 (one shell) and P4 (actions + AI ink) — small, high visibility.
3. P3 (calm canvas) — before recording the demo video.
4. P6 (La Tira) — the signature; build as a `components/ui/tour-strip.tsx` presentational component with controlled `selectedDay`.
5. P5 alongside the real API integration.

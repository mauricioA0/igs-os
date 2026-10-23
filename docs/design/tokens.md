# Design tokens — IGS OS

Source of truth: `apps/web/scripts/tokens.mjs` → generates `apps/web/src/app/tokens.css`, imported by `globals.css` and exposed as Tailwind colors (`bg-*`, `text-*`, `border-*`). Never edit `tokens.css` by hand.

```bash
pnpm --filter web tokens          # regenerate + contrast report
pnpm --filter web tokens:check    # CI: fails if tokens.css is stale or any pair is below AA
```

## Inputs (three values)

| Input | Value | Meaning |
|---|---|---|
| `BASE_HUE` | 75 | Warm neutral hue: the cream of infinityglobalsports.com (`hsl 40 7% 95%`) |
| `ACCENT_HUE` | 245 | Brand accent: Argentina blue (`hsl 210 50% 67%`) |
| `CONTRAST` | 0 | 0 default, 1 high-contrast (darker muted text, stronger borders) |

Everything is OKLCH, gamut-fitted to sRGB before checking. **142 contrast pairs** are verified per run, in both themes (text ≥ 4.5:1, UI borders/focus/edges ≥ 3:1, tinted badges checked as actually rendered: ink on a 10% tint over the card). Current result: 0 failing.

## Scales and roles

- **Neutral ramp** `gray-1 … gray-12` (Radix/Geist roles): 1–2 app background, 3–5 surfaces/hover, 6–7 borders, 8–9 strong borders/placeholder, 11 muted text (AA), 12 text.
- **Semantic** (names unchanged, so existing utilities keep working): `background`, `foreground`, `card`, `popover`, `primary`, `secondary`, `muted`, `muted-foreground`, `accent` (neutral hover surface), `border`, `input` (3:1 for form borders), `ring`, `destructive`, `surface-inverse` (+ `-foreground`, `-muted`) for dark heroes inside light pages.
- **Hue ramps** — `success`, `warning`, `danger`, `info`, `brand` (Argentina blue), `ai`. Each has:
  - `X` ink — text and icons, AA on card, background and its own soft tint
  - `X-soft` tinted background, `X-border` soft border
  - `X-fill` solid background + `X-fill-foreground`
- **Country accents** — `argentina`, `brazil-green`, `brazil-gold`, `brazil-lime`, `usa-red`, `usa-navy`, `costa-rica`, `spain`, `warm` are **decorative** (stripes, dots, fills). For text use the `-ink` variant (`text-argentina-ink`), which passes AA on cream and on cards.
- **Flow canvas** — `canvas`, `canvas-dot`, `edge` (3:1 on canvas), `edge-active`, `node-ai`, `node-conversation`, `node-logic`, `node-integration`, `node-human`. Node category is carried by shape and glyph; these only tint the glyph and border. Run state uses the status ramps.

## Type

Tailwind's default steps are the fixed scale (xs 12 · sm 14 · base 16 · lg 18 · xl 20 · 2xl 24 · 3xl 30 · 4xl 36 · 5xl 48 · 6xl 60 · 7xl 72) plus **`text-2xs` = 11px, the floor**. `text-[9px]` and `text-[10px]` are not allowed; `text-[11px]` → `text-2xs`. `.display` (condensed uppercase headings) and `.eyebrow` (12px condensed label) are global classes.

Motion: `--duration-fast|base|slow`, `--ease-out|in-out`; reduced motion zeroes durations. `.hatch` draws hatched segments (waiting time on timelines) in `currentColor`.

## Badge — one component

`Badge` (`@/components/ui`) has three variants: `status` (default: soft tint + ink; tones `neutral | info | success | warning | danger | brand | ai | solid | live`, optional `dot`), `label` (outlined uppercase eyebrow for categories) and `kind` (filled neutral, optional `icon`). `StatusBadge status=… domain=… lang="es"|"en"` and `StatusDot` read one shared vocabulary, `statusVocabulary`, with a tone and es/en labels for every status in the product:

| Domain | Statuses |
|---|---|
| `trip` | draft, proposed, confirmed, in_progress (live), completed, cancelled |
| `item` | pending, requested, confirmed, completed, cancelled |
| `lead` | new, qualified, proposal_sent, won, lost |
| `approval` | pending, approved, rejected, expired, superseded |
| `execution` | pending, running, waiting, succeeded, completed, failed, skipped, cancelled |
| `flow` | draft, published, archived |
| `account` | prospect, active, past, churned |
| `health` | green, amber, red |
| `sentiment` | positive, neutral, negative, unknown |
| `fact` | status, commitment, risk, preference, budget, decision |

Without `domain`, the first domain that defines the status decides its tone.

## Theme

`.dark` / `.light` on `<html>` **or on any subtree** wins; otherwise the OS setting. `ThemeToggle` (`@/components/ui`) cycles system → light → dark and stores the choice in `localStorage["igs-theme"]`; `RootDocument` applies it before paint (no flash). A surface that must always be dark (the coach experience, UX #6) passes `theme="dark"` to `RootDocument` or puts `className="dark"` on its root element. Never use `@media (prefers-color-scheme)` in feature CSS.

## Language (WCAG 3.1.1)

`apps/web/src/app/_document/root-document.tsx` exports `RootDocument({ lang, theme })`: the `<html>`/`<body>` shell with fonts, globals and the theme script. Today `app/layout.tsx` renders `<RootDocument lang="es">` (the ops app is most of the product). To give coach-facing pages `lang="en"`, Next 16 needs one root layout per route group:

1. `(app)/layout.tsx` → `return <RootDocument lang="es">{children}</RootDocument>` (X3).
2. `(public)/layout.tsx` → `<RootDocument lang="en" theme="dark">` (X7; X8 moves the landing `page.tsx` into `(public)`).
3. Delete `app/layout.tsx` in the same change, and move `/design` under `(app)` or give it its own root layout (it already marks its content `lang="en"`).

Until then, English pages should put `lang="en"` on their top-level element (language of parts).

## Private palettes to remove (by owner)

### Flows — `flows.css` (`--fx-*`) → tokens

| Private | Token | Utility |
|---|---|---|
| `--fx-bg` | `background` | `bg-background` |
| `--fx-fg` | `foreground` | `text-foreground` |
| `--fx-card` | `card` | `bg-card` |
| `--fx-muted` | `muted` | `bg-muted` |
| `--fx-muted-fg` | `muted-foreground` | `text-muted-foreground` |
| `--fx-border` | `border` | `border-border` |
| `--fx-primary` / `--fx-primary-fg` | `primary` / `primary-foreground` | `bg-primary text-primary-foreground` |
| `--fx-canvas` | `canvas` | `--xy-background-color: var(--canvas)` |
| `--fx-dot` | `canvas-dot` | React Flow `<Background color="var(--canvas-dot)">` |
| `--fx-ai` | `node-ai` | `text-node-ai border-node-ai` |
| `--fx-conversation` | `node-conversation` | |
| `--fx-logic` | `node-logic` | |
| `--fx-integration` | `node-integration` | |
| `--fx-human` | `node-human` | |
| `--fx-ok` | `success` (+ `success-soft`) | |
| `--fx-fail` | `danger` | |
| `--fx-wait` | `warning` | animate with `.hatch` for waiting segments |
| `--fx-run` | `info` | |
| `.fx-display` / `.fx-eyebrow` | `.display` / `.eyebrow` | |
| edge stroke `--fx-muted-fg` | `edge`; selected/active `edge-active` | |
| `@media (prefers-color-scheme: dark)` block | delete — tokens follow `.dark` | |
| edge label `font-size: 10px` | `var(--text-2xs)` | |

### Proposal and chat — arbitrary values → tokens

| Arbitrary | Token / utility |
|---|---|
| `bg-[hsl(0_0%_10%)]`, `bg-[hsl(0_0%_5%)]`, `bg-[hsl(0_0%_8%)]` (dark hero/sections) | `bg-surface-inverse` (or put the section in a `.dark` subtree and use `bg-background`/`bg-card`) |
| `text-[hsl(0_0%_95%)]` on dark | `text-surface-inverse-foreground` |
| `text-[hsl(0_0%_60%)]`, `[70%]`, `[75%]` on dark | `text-surface-inverse-muted` |
| `bg-[hsl(40_7%_95%)]` | `bg-background` |
| `bg-[hsl(40_5%_90%)]` | `bg-muted` |
| `border-[hsl(40_5%_85%)]`, `bg-[hsl(40_5%_85%)]` | `border-border` / `bg-border` |
| `text-[hsl(0_0%_40%)]`, `[45%]` | `text-muted-foreground` |
| `text-[hsl(0_0%_10%)]`, `border-[hsl(0_0%_10%)]`, `ring-[hsl(0_0%_10%)]` | `text-foreground`, `border-foreground`, `ring-ring` |
| `text-[hsl(210_50%_67%)]` (Argentina accent as text) | `text-argentina-ink` (AA); decorative fills keep `bg-argentina` |
| hero glows `radial-gradient(… hsl(210_50%_67%/0.35) …)` | `color-mix(in oklch, var(--argentina) 35%, transparent)` |
| `text-[#009c3b]` | `text-brazil-green-ink` |
| `bg-[#BFFF78]` | `bg-brazil-lime` |
| `text-[9px]`, `text-[10px]`, `text-[11px]` | `text-2xs` |
| `text-[13px]`, `text-[15px]` | `text-sm` / `text-base` |

### Ops prototype — `ops/_components/bits.tsx`

| Private | Replacement |
|---|---|
| `Pill` (tones neutral/info/success/warning/danger/live) | `<Badge tone=…>`; uppercase pills → `<Badge variant="label">`; `live` → `tone="live"` |
| `TRIP_STATUS`, `ITEM_STATUS`, lead/approval/account maps in `_mock/format.ts` | `<StatusBadge status=… domain=…>` (labels and tones come from `statusVocabulary`) |
| `CountryTag` (private) | `CountryTag` from `@/components/ui` |
| `ActorIcon` `text-[10px]` | `Avatar kind="agent"` or `text-2xs` |
| `Kpi` | `Stat` from `@/components/ui` |

### Lint (proposal for whoever owns `eslint.config.mjs`)

Add a `no-restricted-syntax` rule rejecting class strings that match `text-\[(9|10)px\]`, `#[0-9a-fA-F]{3,8}` and `hsl\(` inside `className`, so private palettes don't come back.

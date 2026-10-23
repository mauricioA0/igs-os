# IGS site style — measured contract (2026-10-22)

Measured with `getComputedStyle` on https://infinityglobalsports.com (home, plan-a-tour, college-soccer-tours, about), desktop 1440 and mobile 390. **This replaces the earlier cream/monochrome interpretation**: the real site is near-black, photographic, with huge condensed uppercase headlines. Every IGS OS surface (ops included) follows it. Ops is dark by default; a light theme stays available but is secondary.

## Color (exact)

| Token | Value | Where on the site |
|---|---|---|
| `--bg` | `#0D0D0D` (rgb 13,13,13) | page + sections |
| `--surface` | `#171717` | cards, nav active text |
| `--surface-2` | `#262626` (rgb 38,38,38) | footer, raised panels |
| `--fg` | `#F2F2F2` | text, headlines |
| `--fg-strong` | `#FFFFFF` | eyebrows on photos |
| `--muted` | `#999999` | body paragraphs, sub-headlines |
| `--muted-headline` | `#7A7A7A` | first half of two-tone headlines ("MORE THAN A TOUR.") |
| `--line` | `rgba(255,255,255,0.10)` | pills, borders, dividers |
| `--line-strong` | `rgba(255,255,255,0.20)` | hover borders |
| `--nav-idle` | `rgba(255,255,255,0.70)` | idle nav pills |
| Accent | none in chrome; color comes from photography and status only (success/warning/danger/info kept accessible on dark) | |

## Typography (exact)

| Role | Font | Size / line-height / tracking | Case |
|---|---|---|---|
| Hero headline | Klein Condensed 900 → **Barlow Condensed 800/900** | 60px / 48px (0.8) / −1.5px (−0.025em); mobile ~40px | UPPER |
| Mega headline | same | 128px / 102.4px (0.8) / −3.2px (−0.025em); clamp() down on mobile | UPPER, two-tone (muted first line, fg second) |
| Section title | **DM Sans 400** | 48px / 38.4px (0.8) / −2.88px (−0.06em) | Title case |
| Large statement | DM Sans 400 | 60px / 60px / −3.6px (−0.06em) | sentence |
| Card title | DM Sans 400 | 30px / 28.5px / −1.5px (−0.05em) | sentence |
| Small title | DM Sans 400 | 20px / 16px / −1.2px | Capitalize |
| Eyebrow (wide) | **DM Sans 600** | 22px / 33px / **+8.25px (0.375em)** | UPPER |
| Eyebrow (compact) | **Montserrat 600** | 16px / 24px / +0.4px, color `--muted` | UPPER |
| Body | **Montserrat 400** | 16px / 24px; long copy 18px / 28px in `--muted` | |
| Small | Montserrat 400 | 14px / 20px `--muted` | |
| Nav / buttons | Montserrat 600 | 12px / 12–16px | Capitalize |

Fonts loaded by the site: DM Sans 400/600/700, Montserrat 400/500/600, Klein Condensed 800. We use Barlow Condensed (Google Fonts, free) at 800/900 in place of the commercial Klein Condensed. Never ship Klein files.

## Components (exact)

- **Nav**: a centered pill group on a dark bar. Each item: Montserrat 12px/600, `padding: 0 16px`, `border-radius: 9999px`, ~32px tall. Active: `bg #FFFFFF`, `color #171717`. Idle: transparent, `color rgba(255,255,255,.7)`, hover → white. Right side: "Contact Us →" pill `bg rgba(255,255,255,.1)`, `padding 0 20px`. Logo mark at left (white square with ▶ cut-out → we use our own "IGS OS" mark, never their logo).
- **Buttons**: pills. Primary = white bg, `#171717` text. Secondary = `rgba(255,255,255,.1)` bg, white/70 text → white on hover. Always with a trailing arrow `→` for navigation CTAs. Icon buttons: round, `rgba(255,255,255,.1)`.
- **Cards**: flat, `#171717` or photo-backed, radius small (4–12px), 1px `--line` border at most; titles in DM Sans 400 tight tracking.
- **Sections**: generous vertical padding 56–64px (mobile 40px); max-width ~1280px with 24–32px gutters.
- **Photography**: full-bleed images with dark gradient overlays carry color. We have no licensed photos: use CSS-only "stadium" art (gradients/noise/light streaks) or neutral licensed stock placeholders — **never IGS's own images or logo**.
- **Footer**: `#262626`, columns (Programs / Company / Destinations), marquee line in condensed uppercase with letter-spacing ("TRAIN. COMPETE. EXPERIENCE." / "ARGENTINA · BRAZIL · WORLD CUP").
- **Motion**: subtle; marquee and fade-ins only; respect reduced motion.

## Mapping for IGS OS

- Ops shell = the site header pattern: dark top bar, "IGS OS" mark, centered pill nav (Hoy · Viajes · Clientes · Aprobaciones · Leads · Flows · Trazas), right pill "Copiloto ⌘J". Mobile: bottom pill bar.
- Dashboard (Hoy) = site rhythm: mega two-tone headline ("HOY EN / OPERACIÓN."), wide eyebrow with date, KPI numbers in Barlow Condensed 900 huge, the red client (Lakeshore) as a photo-style spotlight card, then the attention list.
- Flows editor = Voiceflow-style canvas (blocks containing stacked steps, step library left, editor panel right, dotted grid, top bar Test/Publish, test chat) in this dark palette.
- Coach surfaces = closest to the site (hero, pill nav, footer, marquee).

## Shared names (G1 implements; everyone else uses these — no private palettes, no arbitrary hex)

Tailwind tokens (dark is the default for every surface): `bg-background` (#0D0D0D), `bg-card` (#171717), `bg-raised` (#262626), `text-foreground` (#F2F2F2), `text-muted-foreground` (#999), `text-muted-headline` (#7A7A7A), `border-line` (white/10), `border-line-strong` (white/20), plus existing status tones (success/warning/danger/info) re-tuned for dark.

Typography utilities (globals.css):
- `.type-mega` — Barlow Condensed 900, `clamp(3rem, 8vw, 8rem)`, lh .8, tracking −.025em, uppercase
- `.type-hero` — Barlow Condensed 800, `clamp(2.5rem, 4.2vw, 3.75rem)`, lh .8, tracking −.025em, uppercase
- `.type-section` — DM Sans 400, `clamp(2rem, 3.4vw, 3rem)`, lh .8, tracking −.06em
- `.type-statement` — DM Sans 400, `clamp(2rem, 4.2vw, 3.75rem)`, lh 1, tracking −.06em
- `.type-card` — DM Sans 400, 1.875rem, lh .95, tracking −.05em
- `.type-small-title` — DM Sans 400, 1.25rem, lh .8, tracking −.06em
- `.eyebrow-wide` — DM Sans 600, 1.375rem (mobile 1rem), lh 1.5, tracking .375em, uppercase
- `.eyebrow` — Montserrat 600, 1rem (ops: .75rem), tracking .025em, uppercase, muted
- `.headline-muted` — color #7A7A7A (wrap the first line of two-tone headlines)
- `.kpi-number` — Barlow Condensed 900, 4rem, lh .85, tabular-nums
- `.marquee` — infinite horizontal scroll strip of condensed uppercase phrases (paused under reduced motion)
- `.stadium-art` — CSS-only photographic-feeling backdrop (dark gradients, light streaks, subtle noise) for heroes/spotlights in lieu of photos

Components (`@/components/ui`):
- `Button` variants: `primary` (white pill, #171717 text), `secondary` (white/10 pill, white/70 → white), `ghost`, `danger`; sizes sm/md/lg; `withArrow` prop adds `→`; always `rounded-full`, Montserrat 600 12–14px
- `PillNav` / `PillNavItem` (active = white pill), `PillGroup` container (`bg white/5`, `border-line`, rounded-full, p-1)
- `IconButton` (round white/10)
- `Card` (flat #171717, `border-line`, radius 8px), `SpotlightCard` (stadium-art backdrop + overlay)
- `Badge` (pills on dark), `Stat` using `.kpi-number`
- `SiteFooter` (#262626, columns + `.marquee`)

Rules: dark default (`<html class="dark">` unless the user picked light); keep WCAG AA (G1 verifies with `pnpm tokens:check`); mobile 390px must look like the site's mobile.

Build hygiene (many agents in apps/web at once): **never run `next build`/`next dev` inside apps/web**. Use `pnpm typecheck`, `pnpm lint`, `pnpm test`. To look at your screen, rsync apps/web to your own scratch copy (exclude `.next`, symlink `node_modules`) and run it there on your own port against the local API (`uv run uvicorn igs_core.app:create_app --factory --port <yours>`, DATABASE_URL=postgres://igs:igs@localhost:5433/igs). Compare against the site screenshots in <scratchpad>/igs-style/.

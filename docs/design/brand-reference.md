# Brand reference — infinityglobalsports.com (extracted 2026-10-22)

Source: production CSS `/assets/index-CdxNilpQ.css` and homepage. The site is a Vite + Tailwind + shadcn-style build (HSL CSS variables). Use this as the visual baseline so IGS OS feels like *their* product.

## Character
Editorial, athletic, monochrome. Black/white/cream with tight corners, big condensed uppercase display type, photography-led. Color comes from **country accents** and imagery, not from the UI chrome.

Copy voice: short, punchy, imperative triplets — "Train. Compete. Experience." · "Built For Teams. Designed For Growth." · "Real Sport. Real Environments." · "Global Game. Local Culture."

## Typography
| Role | Font | Notes |
|---|---|---|
| Display | `Klein Condensed` → fallback **Barlow Condensed** (Google, 400–900) | Klein is commercial; we use Barlow Condensed. Uppercase, tracking `.1em`–`.12em` for eyebrows; tight `-.025em` on big headings |
| Body | **Montserrat** (300–800) | |
| Alt UI | **DM Sans** (300–700) | Imported by the site; good for dense app UI |

## Color tokens (HSL, as on the site)
| Token | Light | Dark |
|---|---|---|
| background | `40 7% 95%` (cream) | `0 0% 5%` |
| foreground | `0 0% 10%` | `0 0% 95%` |
| card | `0 0% 100%` | `0 0% 10%` |
| primary / primary-fg | `0 0% 0%` / `0 0% 100%` | `0 0% 100%` / `0 0% 0%` |
| secondary | `0 0% 10%` | `0 0% 15%` |
| muted / muted-fg | `40 5% 90%` / `0 0% 40%` | `0 0% 15%` / `0 0% 60%` |
| accent | `40 7% 92%` | `0 0% 12%` |
| border | `40 5% 85%` | `0 0% 18%` |
| destructive | `0 84.2% 60.2%` | same |
| ring | `0 0% 10%` | `0 0% 90%` |
| radius | `.25rem` (cards up to `.75rem`) | |

## Country accents (use for destination tags, trip cards, charts)
| Country | Colors |
|---|---|
| Argentina | `--argentina-blue: 210 50% 67%` |
| Brazil | green `#009c3b` (151 100% 30%), gold `#FFCB05` / `48 100% 50%`, lime `#BFFF78` |
| USA (teams) | red `#B22234`, navy `#002776` |
| Warm neutral | `#B2896C` |

## Rules for IGS OS
- Chrome stays monochrome; status colors (success/warning/danger/info) must be added for an ops tool — keep them muted and accessible (WCAG AA).
- Display font only for headings, KPIs and section eyebrows; body/UI in DM Sans or Montserrat.
- Coach-facing surfaces (chat, proposal) = closest to the marketing site (light cream, photography). Ops surfaces = same tokens, denser, dark mode first-class.
- Footer on every public page: "Demo built by Mauricio Villalba — not an official Infinity Global Sports product."

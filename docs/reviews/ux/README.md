# UI/UX review — consolidated proposals (2026-10-22)

Five reviewers walked the running prototypes with screenshots, axe-core and the demo script:

| Review | Focus |
|---|---|
| [v1-ops-heuristics.md](v1-ops-heuristics.md) | Nielsen heuristics + WCAG 2.2 AA on the ops panel and Account 360 |
| [v2-flows.md](v2-flows.md) | Flow editor and execution viewer vs n8n, Voiceflow, Zapier, Temporal UI |
| [v3-coach.md](v3-coach.md) | Coach chat and proposal: brand fidelity, trust, conversion, mobile |
| [v5-visual-system.md](v5-visual-system.md) | Visual consistency, tokens, dark mode, benchmark vs Linear/Attio/Vercel |

## Blocking issues (fix before anything else)

- `lang="en"` on a Spanish UI; hydration error on `/ops/accounts/[id]` (date/time formatting, shows as "1 Issue" in dev).
- Lakeshore's story contradicts itself across screens (execution waiting for approval, trip confirmed and departing Nov 14, proposal Mar 2027).
- Contrast failures (lost-lead cards 3.24:1, amber badge 4.42:1); citations rendered as "[4]" with no accessible name.
- Flows uses its own palette and its dark mode ignores the theme switch; 31 ad-hoc font sizes, some at 9–10 px.

## Proposals, ranked by impact ÷ effort

| # | Proposal | Sources | Impact | Effort |
|---|---|---|---|---|
| 1 | **One coherent Lakeshore story + "Start the 2-minute tour"**: Lakeshore is a March 2027 inquiry waiting for approval on every surface; approving it updates approval, execution, trip, account timeline and proposal. One primary CTA and a 6-step rail replace five cards (time-to-wow ~5 s) | V4 P1, P2 | Very high | S–M |
| 2 | **Copilot with a pre-loaded question and trustworthy citations**: "¿Cómo está Lakeshore y qué falta para que firmen?" streams tool steps and an answer whose citations are chips ("Email · 15 oct · Karen Liu") with a preview of the quoted passage; shows the `claude mcp add` line | V4 P3, V1 P3 | Very high (the AI-native moment) | M |
| 3 | **One product, one visual system**: flows inside the ops shell and in Spanish; OKLCH token scales from three base values; 11 px minimum type; one badge component; node category by shape/glyph, color only for state; readable zoomed-out canvas; accessibility pass (lang, contrast, focus) | V5 P1–P3, V1 P6 | High (credibility, craft) | M |
| 4 | **Approvals people can trust and move fast through**: show what will actually be sent (recipient, proposal, price, fingerprint) instead of node JSON; edit-and-approve with diff and new hash; J/K/A/R/E shortcuts; waits in destination local time with resume/extend; one "waiting on a person" list | V2 P2, V1 P2 | High (core promise: human in control) | M |
| 5 | **"Describí la automatización"**: Spanish prompt → draft flow with stated assumptions, validator run, one-click insert of the approval the security rule requires, sandbox test, save as eval case; never auto-publishes. Plus an ops-friendly "Pasos" view next to the canvas | V2 P3, P1 | High (memorable, AI-native) | L |
| 6 | **Proposal that converts**: price as a package (no margin line items), "Reserve — $867 deposit" CTA in hero/after price/sticky on mobile (creates a deposit approval for ops), dark photographic look like infinityglobalsports.com with licensed stock, trust strip, PDF ≤ 5 pages | V3 1–3 | High for IGS's business | S–M |
| 7 | **"La Tira" — signature trip strip**: each trip as a horizontal strip of days in the country color, scoreboard-style "DÍA 5/10", alert dots on the affected day; same component as sparkline in lists and interactive in trip detail, proposal, Today and executions | V5 P6 | Medium–high (brand memorability) | M |
| 8 | **Field mode on mobile**: bottom bar (Hoy · Aprobaciones · Gira · Copiloto); Today opens on the live trip with one-tap confirm/call | V1 P1 | Medium (real ops value, less demo value) | M |

Also worth doing later: safer item actions and a single Today queue (V1 P4–P5), debugging aids — "why did this happen?", retry with edited input, compare runs (V2 P4), templates and a guided first flow (V2 P5), "Your tour so far" panel and mobile quick-reply fixes (V3).

## Suggested order

1. Blocking issues + #1 (story and tour) — removes the credibility risk.
2. #2 and #4 — they land on top of the wave-2 backend (copilot/MCP, approvals API).
3. #3 — visual unification while moving prototypes to `features/*` (docs/architecture/frontend.md).
4. #6 and #7 — brand and conversion polish.
5. #5 and #8 — larger bets once the core demo is solid.

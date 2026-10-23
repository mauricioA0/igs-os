# V3 — Coach-facing review: brand, trust, conversion

Reviewer: V3 (brand & conversion). Scope: `/chat` (390 px and 1440 px) and `/proposal/t-2711` (desktop, mobile, A4 PDF), compared with infinityglobalsports.com (desktop + mobile), 2026-10-22. Screenshots: `scratchpad/ux-v3/*.png`, `proposal.pdf` (local, not committed).

## What works

- **Voice.** "Train. Compete. Experience." and "Built for teams. Designed for growth." reuse IGS's triplets; the proposal reads like their brand.
- **Proposal structure.** Hero facts strip (dates · matches · travelers · per person), opponents with level meter, day-by-day, included/not included, price breakdown, 3 next steps. Logical, scannable, complete.
- **Chat transparency.** Tool chips ("Searching opponents · women · college · level 7", "Checking entry requirements") show the agent's work; quick replies speed qualification; the "Prototype · scripted demo" chip and footer disclaimer are honest.
- **Not impersonating.** Text "IGS" mark instead of their logo, fictional client, disclaimer on every page.

## Findings

| # | Area | Finding | Severity |
|---|---|---|---|
| F1 | Brand | The IGS site is **dark-first and photo-led** (near-black, Bombonera team photo, huge condensed white type). Our chat is light cream with no imagery; the proposal body is cream after a dark hero. It reads "generic SaaS", not IGS. | High |
| F2 | Conversion | The proposal **has no primary CTA**. It ends with "Questions? Reply in the chat". No "Reserve your spot — $867 deposit" button, no expiry countdown, no sticky price on mobile (page is 7,363 px tall on 390 px). | High |
| F3 | Commercial risk | The price breakdown shows **"Operations & planning $522"** and per-line costs — it exposes margin and invites line-by-line negotiation. | High |
| F4 | Trust | No trust signals a coach needs before paying: named tour leader, AFA-certified coaches, safety/insurance, testimonials from programs ("Saint Francis", "Gustavus Adolphus" are on IGS's site), cancellation policy link. | Medium |
| F5 | Chat desktop | Phone frame centered in a 1440 px viewport with ~70% empty space; the spec's "Your tour so far" panel (docs/design/coach-experience.md) isn't there. | Medium |
| F6 | Chat mobile | Quick replies scroll horizontally and are **cut off without an affordance**; disabled send button looks the same as enabled; footer disclaimer competes with the input. (The "N" bubble over the input is Next's dev indicator — dev only.) | Medium |
| F7 | Consistency | Opponent cards show **"7/10"**; coach-experience.md says the numeric `levelScore` is internal and the coach should see a label relative to their team ("Your level", "+1 stronger"). | Low |
| F8 | AI disclosure / handoff | "Online · replies instantly" implies a person; there's no visible "Talk to a person" path. Spec requires the AI to always identify itself and offer handoff. | Medium |
| F9 | Print/PDF | A4 export = 8 pages; hero facts wrap ("MAR 6 – MAR / 15"); letter-spaced eyebrows extract as "T H E  TO U R" (hurts copy-paste/accessibility); no page header/footer with proposal id/validity. | Low |

## Proposals

### P1 — Go dark and photo-led, like infinityglobalsports.com (F1)

Make coach-facing surfaces dark by default (the design system already has the dark tokens) and give every key screen a licensed photo (stock, not IGS's): chat header strip, proposal hero, a full-bleed image per city/stadium section.

```
┌──────────────────────────────────────────────┐ ← #0d0d0d
│ INFINITY GLOBAL SPORTS          ⤓ Download PDF│
│ [ full-bleed stadium photo, 40% dark overlay ]│
│ LAKESHORE UNIVERSITY                          │ ← Barlow Condensed 96px
│ BUENOS AIRES 2027                             │
│ TRAIN. COMPETE. EXPERIENCE.                   │
│ MAR 6–15 │ 3 MATCHES │ 24 PLAYERS │ $2,890 pp │
└──────────────────────────────────────────────┘
```
Impact: high (first impression for IGS = "this is our product"). Effort: S–M (tokens exist; needs 4–6 licensed photos + `.dark` scope on coach routes).

### P2 — One clear path to "Reserve" (F2)

Primary CTA in three places: hero, after the price, and a sticky bottom bar on mobile with price + validity. The button opens a confirm step (roster size, deposit amount, terms) → creates a `deposit requested` approval for ops (no payments in v0, per spec).

```
mobile, sticky ─────────────────────────────────
│ $2,890 pp · valid 14 days    [ RESERVE → ]   │
───────────────────────────────────────────────
hero:  [ RESERVE YOUR SPOT — $867 DEPOSIT ]  [ Ask a question ]
```
Impact: high (turns a brochure into a funnel; shows end-to-end ops loop in the demo). Effort: S.

### P3 — Package the price, don't itemize the margin (F3)

Show "What your $2,890 covers" as grouped categories without amounts (Stay, Transport, Competition, Coaching, Experiences, 24/7 Support), plus deposit/balance schedule. Keep the itemized cost breakdown in the **ops** view only.

```
INVESTMENT
$2,890 PER PERSON · group total $69,360
✓ Stay  ✓ Private transport  ✓ 3 matches + referees
✓ 4 AFA-licensed sessions  ✓ Experiences  ✓ 24/7 tour leader
Deposit 30% ($867) to reserve · balance 45 days before departure
```
Impact: high (commercially safer; a real IGS ops lead would flag the current table). Effort: XS.

### P4 — Trust band before the price (F4, F8)

A compact band between itinerary and investment: tour leader card (photo, name, "bilingual, 9 seasons"), 3 badges (AFA-licensed coaching · Private transport · Insurance coordinated), one testimonial from a fictional program, links to cancellation & safety policy. In the chat header, replace "Online · replies instantly" with "AI tour concierge · a person reviews every proposal" and add "Talk to a person".

```
┌ YOUR TOUR LEADER ─────┐ ┌ ✓ AFA-licensed coaches  ┐
│ (photo) Lucía F.      │ │ ✓ Private bus, 24/7     │
│ Bilingual · 9 seasons │ │ ✓ Insurance coordinated │
└───────────────────────┘ └─────────────────────────┘
"Our players still talk about La Bombonera." — Head Coach, Westbrook College
```
Impact: medium-high (deposit decisions are trust decisions; also fixes AI disclosure). Effort: S.

### P5 — Desktop chat with a live "Your tour so far" panel (F5)

Two columns on ≥1024 px: chat left, live tour card right filling as the agent qualifies (sport, level, dates, travelers, focus, matched opponents), ending with "Proposal ready" + preview thumbnail. Mobile keeps the full-screen chat with a collapsible summary chip.

```
┌ chat ──────────────────────┐┌ YOUR TOUR SO FAR ─────────┐
│ …24 players, March 6–15    ││ Women's soccer · NCAA D1  │
│ ✓ Searching opponents…     ││ Level ≈ 7 · Buenos Aires  │
│ Perfect. I found 3…        ││ Mar 6–15 · 24 players     │
│                            ││ Opponents ●●○ matched     │
│ [Competitive + culture] …  ││ ▸ Proposal ready  [Open]  │
└────────────────────────────┘└───────────────────────────┘
```
Impact: medium (uses the empty 70%, makes the agent's structured extraction visible — strong "AI-native" signal). Effort: M.

### P6 — Mobile chat ergonomics (F6)

Wrap quick replies to two rows (or fade edge + chevron), larger 44 px targets, enabled/disabled send states, move the disclaimer into the conversation start (once) instead of under the input.

Impact: medium. Effort: XS.

### P7 — Relative opponent level + print polish (F7, F9)

Replace "7/10" with "Your level" / "+1 stronger" / "−1 easier" chips; print stylesheet: keep hero facts on one line (`white-space: nowrap`), real letter-spacing via `letter-spacing` only on screen (or `font-feature` alternatives) so text extracts cleanly, running footer "Proposal t-2711 · valid until Nov 5, 2026 · page n/N", target ≤5 A4 pages by condensing day cards into a table.

Impact: low-medium. Effort: S.

## Suggested order

P3 → P2 → P1 → P4 → P6 → P5 → P7 (cheap, high-impact commercial fixes first; brand overhaul next; then layout work).

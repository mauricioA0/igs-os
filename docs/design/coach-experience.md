# Coach experience — chat, proposal, trip portal
> **Note (2026-10-22):** payment examples below predate the alignment with IGS's published terms (US$95 enrollment fee, US$500 installments, balance 110 days before departure). The product and seed use the real terms; see packages/py-common/fixtures and docs/delivery/use-cases.md. <!-- Superseded payment terms -->

> Owner: U5 · Status: design draft · Inputs: [brand-reference.md](brand-reference.md), [security.md](../architecture/security.md) §3.7, [flow-engine.md](../architecture/flow-engine.md) (`inbound-inquiry` flow), live site infinityglobalsports.com (structure checked 2026-10-22).

Everything a coach touches must feel like **infinityglobalsports.com itself**, not like a SaaS tool bolted on. Ops surfaces can be dense; coach surfaces are editorial, calm and photography-led.

## 1. Who and what

| | |
|---|---|
| **Primary user** | Head coach / program director of a US or Canadian college, high-school or club team. Planning 6–12 months ahead, often on a phone between practices, sometimes on a laptop with the AD. |
| **Secondary** | Assistant coach, athletic director, team manager (same trip, different questions: budget, safety, paperwork). |
| **Not the user** | Players and parents. The chat is aimed at coaches (this matters for COPPA positioning, see §6). |
| **Job to be done** | "Help me find out, quickly and without a sales call, whether a tour fits my team's level, dates and budget — and give me something I can forward to my AD." |

Three surfaces, one journey:

```
 infinityglobalsports.com                     email / link              confirmed trip
┌───────────────────────┐   proposal ready  ┌──────────────┐  deposit  ┌──────────────┐
│ 1. Inquiry chat       │ ────────────────▶ │ 2. Proposal  │ ────────▶ │ 3. Trip      │
│ widget + full page    │                   │ /p/{token}   │           │ portal       │
└───────────────────────┘                   └──────────────┘           └──────────────┘
   qualify (agent)          ops approval        review / forward          itinerary updates,
   answers (RAG)            (flow node)         ask questions             checklist, forms
```

## 2. Brand application (coach surfaces)

Taken from [brand-reference.md](brand-reference.md). Coach surfaces use the **light cream** theme by default; dark only where the marketing site uses it (hero overlays, final CTA band).

| Element | Rule |
|---|---|
| Background | `background 40 7% 95%` cream; cards pure white `0 0% 100%`, `radius .25rem` (`.75rem` max for the chat sheet). |
| Display type | Barlow Condensed (Klein fallback), **UPPERCASE**, tracking `.1em` for eyebrows, `-.025em` for big headings. Used for: hero titles, day numbers, prices, section eyebrows. |
| Body | Montserrat for long-form (proposal); DM Sans for UI text inside chat bubbles and forms (denser, more legible at 14–15px). |
| Primary button | Black fill, white uppercase label, tracking `.1em`, square-ish corners — same as "Plan Your Team's Tour" on the site. Secondary = 1px black outline. |
| Color | Monochrome chrome. Color only from **country accents** (Argentina blue `210 50% 67%`, Brazil green `#009c3b` / gold `#FFCB05`, Costa Rica: use warm neutral `#B2896C` until the site defines one) and photography. |
| Imagery | Full-bleed match / stadium / city photos with dark gradient overlay for text. Placeholder set for the demo lives in `apps/web/public/demo/` (licensed stock or own photos — never hotlink the IGS site). |
| Voice | Short, confident, imperative triplets ("Train. Compete. Experience."). In chat: warm, specific, no exclamation spam, no emojis except ⚽-style sport glyph in the launcher if any. |
| Footer (all public pages) | "Demo built by Mauricio Villalba — not an official Infinity Global Sports product." |

Section rhythm copied from the site: **eyebrow (small caps) → condensed headline → one paragraph → checklist or grid → black CTA**.

## 3. Surface 1 — Inquiry chat

### 3.1 Entry points

| Entry | Behaviour |
|---|---|
| **Embeddable widget** on their site (`<script src=".../widget.js" data-tenant="igs">`) | Floating launcher bottom-right. Replaces/augments "Plan Your Team's Tour" and "Contact Us" CTAs: those buttons can open the widget pre-filled (`data-intent="plan-tour"`, `data-destination="argentina"`). |
| **Full-page chat** `/chat` (and `/chat?destination=brazil&sport=soccer`) | Link for emails, QR codes at college showcases, and for the public demo. Same component, full viewport. |
| **Destination tab CTA** ("Explore Argentina") | Opens widget with destination pre-selected → agent skips that question. |

Widget isolation: rendered in an **iframe** (style isolation from their CSS, no access to host cookies), communicates via `postMessage` only for open/close/resize and pre-fill params. CSP-friendly; < 60 KB JS for the launcher, chat bundle lazy-loaded on open.

### 3.2 Why "WhatsApp-like", and where it stops

Coaches already plan trips on WhatsApp/iMessage, so we borrow the **interaction model**: bubbles left/right, timestamps, read ticks, typing indicator, quick-reply chips, attachments-as-cards. We do **not** copy WhatsApp's look (no green, no wallpaper): the chrome is IGS monochrome, agent bubbles are white cards on cream, coach bubbles are black with white text.

### 3.3 Wireframes — widget

Launcher (closed), desktop:

```
                                                        ┌──────────────────────────┐
                                                        │ PLAN YOUR TEAM'S TOUR  → │  ← black pill, uppercase,
                                                        └──────────────────────────┘    appears after 8s scroll or
                                                                          ( ◉ )        on CTA click; dismissible
```

Open widget, desktop (400×640 sheet, anchored bottom-right):

```
┌────────────────────────────────────────────┐
│ ∞ INFINITY GLOBAL SPORTS          ─   ✕   │  black header bar
│ Tour planning · replies in seconds         │  muted subline
├────────────────────────────────────────────┤
│ ⓘ Please don't share players' personal     │  persistent, dismiss-to-collapse
│   info (birthdates, passports) here.       │  (security.md §3.7)
├────────────────────────────────────────────┤
│                                            │
│  ┌──────────────────────────────────┐      │
│  │ Hi coach — I'm the IGS tour       │      │  agent bubble: white card,
│  │ planner. Tell me about your team  │      │  DM Sans 15px
│  │ and I'll sketch a tour in minutes.│      │
│  └──────────────────────────────────┘      │
│  ( Soccer )( Rugby )( Field hockey )        │  quick-reply chips:
│  ( Volleyball )( Basketball )( Other )      │  1px outline, uppercase 12px
│                                            │
│                 ┌───────────────────────┐  │
│                 │ Women's soccer, D1,   │  │  coach bubble: black
│                 │ 24 players, March     │  │
│                 └───────────────────── ✓✓┘  │
│                                            │
│  ● ● ●  Checking opponents at your level…  │  typing + tool-status line
├────────────────────────────────────────────┤
│ [ Type your message…              ] [ ➤ ]  │
│ Talk to a person · Privacy                 │  footer links
└────────────────────────────────────────────┘
```

Mobile (widget opens as full-screen sheet, same as `/chat`):

```
┌──────────────────────────┐
│ ←  INFINITY GLOBAL SPORTS│
│    Tour planning         │
├──────────────────────────┤
│ ⓘ Don't share players'  │
│   personal info here. ✕  │
├──────────────────────────┤
│ ┌──────────────────────┐ │
│ │ Great — D1 women's   │ │
│ │ soccer, 24 players.  │ │
│ │ Which destination?   │ │
│ └──────────────────────┘ │
│ ┌────────┐┌────────┐     │  destination chips become
│ │ARGENT. ││ BRAZIL │     │  mini photo cards with
│ │▔▔▔▔▔▔▔▔││▔▔▔▔▔▔▔▔│     │  country-accent underline
│ └────────┘└────────┘     │
│ ┌────────┐┌────────┐     │
│ │COSTA R.││NOT SURE│     │
│ └────────┘└────────┘     │
│                          │
├──────────────────────────┤
│ [ Message…        ] [➤] │  sticky; respects safe-area
└──────────────────────────┘
```

Full-page `/chat`, desktop: two columns — chat (max 640px) on the left, **live "Your tour so far" summary card** on the right that fills in as slots are captured. On mobile the summary collapses into a pill above the composer ("4 of 7 details ✓ ▾").

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ ∞ INFINITY GLOBAL SPORTS                                    Talk to a person  ☰   │
├──────────────────────────────────────────────┬────────────────────────────────────┤
│                                              │  YOUR TOUR SO FAR                  │
│   [chat thread as above]                     │  ───────────────────────────────── │
│                                              │  Sport ........ Soccer (W)     ✓   │
│                                              │  Level ........ NCAA D1        ✓   │
│                                              │  Group ........ 24 + 3 staff   ✓   │
│                                              │  Destination .. Argentina      ✓   │
│                                              │  Dates ........ Mar 7–16       ✓   │
│                                              │  Budget ....... —              ·   │
│                                              │  Goals ........ —              ·   │
│                                              │  ───────────────────────────────── │
│                                              │  [ EDIT DETAILS ]                  │
├──────────────────────────────────────────────┤                                    │
│ [ Type your message…                 ] [ ➤ ] │  photo of destination (accent bar) │
└──────────────────────────────────────────────┴────────────────────────────────────┘
```

The summary card is driven by the flow's captured variables (`vars.*` of the `inbound-inquiry` execution), so what the coach sees is exactly what ops will see. Clicking a row lets the coach correct it inline (sends a structured correction event, not free text).

### 3.4 Conversational qualification

The agent (an `agent` node in `inbound-inquiry`) needs seven slots before it can draft a tour. UX principles:

1. **Accept everything at once.** "Women's D1 soccer, 24 players, Argentina in March, ~$3k" fills five slots in one turn; the agent confirms in one line and only asks for what's missing.
2. **One question per turn**, always with quick replies when the answer space is small.
3. **Never interrogate before giving value.** After 2–3 slots, offer something concrete ("Teams at your level usually play Deportivo Belgrano Femenino — level 7, strong set pieces") before asking for the rest.
4. **Answer side questions immediately** (visas, safety, deposits) from the knowledge base with a small citation chip, then return to the next missing slot.
5. **No price before qualification** — but never dodge: "Tours to Buenos Aires usually run $2,400–$3,200 per person; I can be precise once I know dates and group size." (range comes from the KB policy, grounded).

| Slot | Question (if missing) | Quick replies | Notes |
|---|---|---|---|
| Sport + gender | "Which program is traveling?" | Soccer · Rugby · Field hockey · Volleyball · Basketball → then Men's · Women's · Coed | |
| Level | "What level do you compete at?" | NCAA D1 · D2 · D3 · NAIA · JUCO · Club/ECNL · High school | Mapped to `levelScore` 1–10 silently; never show the number to the coach. |
| Age group | asked only if club/HS | U13 · U15 · U17 · U19 | Triggers minors' data rules downstream. |
| Group size | "Roughly how many players and staff?" | number stepper `[ 22 ▾ ] players [ 3 ▾ ] staff` | Inline mini-form inside the bubble. |
| Destination | "Where would you like to go?" | Argentina · Brazil · Costa Rica · Not sure | Photo chips (mobile wireframe above). "Not sure" → agent recommends based on dates/level. |
| Dates / length | "When, and for how long?" | Spring break · May–June · Summer · Pick dates | "Pick dates" opens a month range picker; 8–14 day slider. |
| Budget + goals | "Anything we should optimize for?" | Competitive games · Culture · Budget-friendly · Service hours | Optional; skippable with "Skip". |

Contact capture (name, email, school/club) comes **last**, framed as "Where should I send your proposal?" — a 3-field inline card, not free text. Email is validated client-side; the phone field is optional and marked as such.

### 3.5 Message types (component inventory)

| Type | Rendering |
|---|---|
| `text` | Bubble; light markdown (bold, lists, links) rendered without `dangerouslySetInnerHTML`. |
| `quick_replies` | Chips under the last agent bubble; disappear after use; keyboard-navigable (←/→, Enter). |
| `form` | Inline card with 1–3 fields (stepper, date range, contact). Submits as structured data. |
| `opponent_card` | Small card: club name, city, level label ("Strong club / D1-level"), one-line style. Used to show value early. |
| `citation` | Chip under an answer: "From: Entry requirements for US citizens ↗" opens a side sheet with the source excerpt. Only for KB-grounded answers. |
| `tool_status` | Single muted line under typing dots: "Checking opponents at your level…", "Drafting your itinerary…". Never shows raw tool names. |
| `proposal_card` | Rich card when the proposal is ready (see 3.7). |
| `handoff` | System card: "Sofía from IGS joined the chat" with avatar (see 3.6). |
| `system` | Centered muted text for state changes ("Chat continued by email"). |

### 3.6 Handoff to a human

Triggers: coach taps **"Talk to a person"** (always visible), types intent like "can I speak to someone", the agent hits a guardrail (discount negotiation, custom contract, complaint, safety incident), or the flow's `approval` node is waiting longer than the SLA while the coach is still online.

```
┌──────────────────────────────────────────┐
│        ── Connecting you with our team ──│  system line
│  ┌────────────────────────────────────┐  │
│  │ (photo) SOFÍA M. · Tour specialist │  │  handoff card
│  │ Buenos Aires · usually replies in  │  │
│  │ ~10 min (Mon–Fri, 9–18 ART)        │  │
│  │ I've shared your tour details with │  │
│  │ her — no need to repeat anything.  │  │
│  └────────────────────────────────────┘  │
│  Out of hours? ( Email me instead )       │
│                ( Book a 20-min call ↗ )   │
└──────────────────────────────────────────┘
```

Rules:
- The human sees the full transcript + the "Your tour so far" summary in the ops panel; the coach is told so explicitly ("no need to repeat anything").
- While a human owns the thread the agent is **silent** (the flow is paused on the human node); a small label "IGS team" replaces "Tour planner" on bubbles so the coach always knows who is talking.
- Agent bubbles are labeled **"Tour planner (AI)"** from the first message. No pretending to be human.
- If nobody picks up within the SLA, the coach gets a choice (email / call booking), never a dead end.

### 3.7 Proposal ready

When ops approves (approval node in `inbound-inquiry`), the agent posts:

```
┌──────────────────────────────────────────┐
│ ┌──────────────────────────────────────┐ │
│ │ [ full-width photo: La Bombonera ]   │ │
│ │ ARGENTINA · 10 DAYS                  │ │  condensed, uppercase
│ │ SAINT FRANCIS WOMEN'S SOCCER         │ │
│ │ Mar 7–16 · 3 matches · from $2,890pp │ │
│ │ [ VIEW YOUR PROPOSAL → ]             │ │  black button
│ └──────────────────────────────────────┘ │
│ I also emailed it to coach@sfu.edu.      │
└──────────────────────────────────────────┘
```

If approval is still pending when the coach leaves, the proposal arrives by email; the chat shows "Your proposal is being reviewed by our team — you'll get it by email within 1 business day."

### 3.8 States & edge cases

| State | UX |
|---|---|
| First load | Greeting + sport chips within 300 ms (static, no model call). |
| Agent thinking > 2s | Typing dots + tool-status line; > 15s → "Still working on it — matching opponents takes a moment." |
| Model/API error | "Something went wrong on our side. Try again, or leave your email and we'll follow up." + Retry chip. Message is not lost (persisted before the call). |
| Offline | Composer disabled, banner "You're offline — messages will send when you reconnect"; queued bubbles shown with a clock icon. |
| Returning coach | Thread restored (conversation id in localStorage for the widget, signed link for email returns). "Start a new inquiry" in the ⋯ menu. |
| Injection / off-topic | Agent politely steers back; never reveals system prompt or tools. Covered by red-team evals. |
| PII typed anyway | Input PII detector masks DOB/passport/phone patterns before sending; the coach sees "We hid a date of birth from this message to protect your players' privacy." |
| Spanish / Portuguese coach | Agent answers in the coach's language; UI chrome stays English in v0 (i18n-ready strings). |

### 3.9 Accessibility & performance (chat)

- Thread is an ARIA `log` with `aria-live="polite"`; streaming text is announced per completed message, not per token.
- All quick replies are buttons with visible focus (2px `ring`), 44×44 px minimum targets on mobile.
- Color contrast: black on cream and white on black exceed AA; muted text `0 0% 40%` on cream ≥ 4.5:1 (verify in the design-system page).
- `prefers-reduced-motion`: no typing-dot animation, no slide-ins.
- Streaming via SSE; first token target < 1.5 s p50 (observability SLO).

## 4. Surface 2 — Proposal page

URL: `/p/{token}` — unguessable token (not the trip UUID), expires/rotates when the proposal is superseded. Public, no login, `noindex`. Generated from `getTrip` + `quoteTrip` snapshot (`trips.pricing`), so the price shown is exactly what ops approved.

### 4.1 Structure (mirrors the marketing site's rhythm)

1. **Hero** — full-bleed destination photo, dark overlay; eyebrow `PROPOSAL · ARGENTINA`; headline `SAINT FRANCIS WOMEN'S SOCCER`; subline `Buenos Aires · March 7–16, 2027 · 24 players + 3 staff`; prepared-by line with the ops specialist's name; proposal version and valid-until date.
2. **At a glance** — 4-up stat strip in display type: `10 DAYS` · `3 MATCHES` · `4 TRAINING SESSIONS` · `5 EXPERIENCES`.
3. **Itinerary** — day-by-day, the core of the page.
4. **Your opponents** — one card per match.
5. **Experiences** — photo cards.
6. **What's included / not included** — checklists (same pattern as "What to Expect").
7. **Investment** — price per person + breakdown.
8. **Next steps** — deposit CTA, questions, download.
9. **Footer** — IGS footer + demo disclaimer.

### 4.2 Desktop wireframe

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ ∞ INFINITY GLOBAL SPORTS                          [ ⤓ PDF ]  [ ASK A QUESTION ]  │
├──────────────────────────────────────────────────────────────────────────────────┤
│░░░░░░░░░░░░░░░░░░░░░░░░ full-bleed photo, gradient overlay ░░░░░░░░░░░░░░░░░░░░░░│
│░  PROPOSAL · ARGENTINA                                                         ░│
│░  SAINT FRANCIS                                                                ░│
│░  WOMEN'S SOCCER                                                               ░│
│░  Buenos Aires · Mar 7–16, 2027 · 24 players + 3 staff                         ░│
│░  Prepared by Sofía M. · v2 · valid until Nov 30                               ░│
├──────────────────────────────────────────────────────────────────────────────────┤
│   10 DAYS     │   3 MATCHES    │   4 TRAINING SESSIONS   │   5 EXPERIENCES       │
├──────────────────────────────────────────────────────────────────────────────────┤
│ ITINERARY                                                  ┌───────────────────┐ │
│ ─────────                                                  │ INVESTMENT        │ │
│ 01  SAT MAR 7   ARRIVAL                                    │ $2,890            │ │
│     Morning   Airport pickup · private bus                 │ per player        │ │
│     Evening   Welcome dinner · Palermo                     │ ───────────────── │ │
│                                                            │ Hotel (9 nights)  │ │
│ 02  SUN MAR 8   TRAIN                                      │ Transport         │ │
│     Morning   AFA-certified training session               │ Matches & refs    │ │
│     Afternoon La Bombonera stadium tour        [photo]     │ Training          │ │
│                                                            │ Experiences       │ │
│ 03  MON MAR 9   COMPETE ●                                  │ Tour leader 24/7  │ │
│     Afternoon MATCH vs Deportivo Belgrano Femenino         │ ───────────────── │ │
│               Level: D1-comparable · strong set pieces     │ Coaches: 1 free   │ │
│     Evening   Tango class & asado                          │ per 15 players    │ │
│                                                            │                   │ │
│ 04  TUE MAR 10  RECOVER                                    │ [ RESERVE WITH    │ │
│     …                                                      │   30% DEPOSIT → ] │ │
│                                                            │ Ask a question    │ │
│                                                            └───────────────────┘ │
│                                                              ↑ sticky on desktop │
├──────────────────────────────────────────────────────────────────────────────────┤
│ YOUR OPPONENTS                                                                   │
│ ┌──────────────────────┐ ┌──────────────────────┐ ┌──────────────────────┐       │
│ │ DAY 03 · MATCH 1     │ │ DAY 06 · MATCH 2     │ │ DAY 09 · MATCH 3     │       │
│ │ DEPORTIVO BELGRANO   │ │ HOCKEY… / CLUB …     │ │ …                    │       │
│ │ FEMENINO             │ │                      │ │                      │       │
│ │ Buenos Aires         │ │                      │ │                      │       │
│ │ ■■■■■■■□□□ Strong    │ │ ■■■■■■□□□□ Competitive│ │ ■■■■■■■■□□ Stretch  │       │
│ │ Quick wingers, strong│ │ …                    │ │ …                    │       │
│ │ set pieces.          │ │                      │ │                      │       │
│ │ Scouting report incl.│ │                      │ │                      │       │
│ └──────────────────────┘ └──────────────────────┘ └──────────────────────┘       │
├──────────────────────────────────────────────────────────────────────────────────┤
│ EXPERIENCES          [photo card] [photo card] [photo card] [photo card]         │
├──────────────────────────────────────────────────────────────────────────────────┤
│ WHAT'S INCLUDED                          │ NOT INCLUDED                          │
│ ✓ Hotel, twin/triple rooms, breakfast    │ – International flights (we can quote)│
│ ✓ Private bus for the whole stay         │ – Travel & medical insurance (req.)   │
│ ✓ All matches with certified referees    │ – Lunches & dinners not listed        │
│ ✓ Bilingual tour leader 24/7             │                                       │
├──────────────────────────────────────────────────────────────────────────────────┤
│ NEXT STEPS                                                                       │
│ 1 Review with your AD   2 Reserve with a 30% deposit   3 Balance 45 days before  │
│ [ RESERVE WITH 30% DEPOSIT → ]   [ ⤓ DOWNLOAD PDF ]   [ BOOK A CALL ]            │
├──────────────────────────────────────────────────────────────────────────────────┤
│ footer · Demo built by Mauricio Villalba — not an official IGS product           │
└──────────────────────────────────────────────────────────────────────────────────┘
```

Itinerary details:
- Day number in display type (`01`, `02`…), weekday + date, and a **day theme word** in uppercase borrowed from the site's vocabulary: `ARRIVAL · TRAIN · COMPETE · EXPLORE · RECOVER · CULTURE · DEPARTURE`.
- Match days get a filled dot `●` and a country-accent left border.
- Each slot (Morning/Afternoon/Evening) is one line; experiences can expand to show photo + description.
- Days with nothing scheduled read "Free afternoon — your tour leader can suggest options", never blank.

Opponent level, coach-friendly:
- Show a **10-segment bar** plus a label relative to the visiting team: `Comparable`, `Competitive`, `Stretch`, `Developmental`. The raw `levelScore` is internal.
- One-sentence style description from the catalog + "Scouting report included".

Investment block:
- Big display price per player; "per player · USD"; breakdown lines from `quoteTrip` (labels only, or labels + amounts if ops toggles "show breakdown amounts" on the trip).
- Coach/staff rule, deposit %, balance date — all from the KB policies, rendered from structured data (not LLM text).
- Price disclaimer: "Price valid until {validUntil}. Flights not included."

### 4.3 Mobile wireframe

```
┌──────────────────────────┐
│ ∞ IGS            ⤓   ?   │
│░░░░░░░░░░░░░░░░░░░░░░░░░░│
│░ PROPOSAL · ARGENTINA   ░│
│░ SAINT FRANCIS          ░│
│░ WOMEN'S SOCCER         ░│
│░ Mar 7–16 · 27 people   ░│
├──────────────────────────┤
│ 10 DAYS  │ 3 MATCHES     │  2×2 stat grid
│ 4 TRAIN. │ 5 EXPER.      │
├──────────────────────────┤
│ ITINERARY                │
│ ▸ 01 SAT · ARRIVAL       │  accordion per day
│ ▾ 03 MON · COMPETE ●     │  (match days open by
│   PM  MATCH vs Belgrano  │   default)
│       ■■■■■■■□□□ Strong   │
│   EV  Tango & asado      │
│ ▸ 04 TUE · RECOVER       │
│ …                        │
├──────────────────────────┤
│ OPPONENTS  ◀ card ▶      │  horizontal snap scroll
├──────────────────────────┤
│ INCLUDED ✓ …             │
├──────────────────────────┤
│ $2,890 per player        │
│ [ RESERVE · 30% DEPOSIT ]│  sticky bottom bar after
└──────────────────────────┘  scrolling past investment
```

### 4.4 Print / PDF

- "Download PDF" = `window.print()` with a dedicated print stylesheet (A4 and US Letter): cover page = hero; one section per page break (`break-before: page` on Itinerary, Opponents, Investment); no sticky elements, no buttons; links printed as short URLs; photos at reduced resolution; black-and-white safe (accents become border weights).
- Footer on every printed page: trip title · proposal version · page N/M · demo disclaimer.
- A server-rendered PDF (for email attachments) is a later option; v0 relies on print CSS.

### 4.5 Interactions

| Action | Result |
|---|---|
| **Ask a question** | Opens the chat sheet scoped to this proposal (conversation linked to the trip); agent answers from the proposal + KB; changes requested ("swap the Tigre trip for a second training") become a **change request** for ops, not an automatic edit. |
| **Reserve with 30% deposit** | v0: opens a confirmation form (name, role, institution, billing contact) → creates a "deposit requested" event for ops; real payment out of scope. Copy says exactly that: "Our team will send the deposit invoice within 1 business day." |
| **Forward to AD** | Share button copies the link; Open Graph image = hero + team name + dates. |
| Superseded proposal | Banner "A newer version of this proposal is available → v3"; old version stays readable. |

## 5. Surface 3 — Trip portal (confirmed teams)

For coaches (and invited staff) once the deposit is in. Login via **magic link** to the coach's email (no passwords). The portal is the coach's single place for "what's happening and what do I still owe you".

### 5.1 Information architecture

```
Trip portal
├─ Overview         countdown, next action, latest updates
├─ Itinerary        live version of the proposal itinerary (with change badges)
├─ Checklist        what IGS needs from the team, with due dates
├─ Documents        IGS → team: invoices, travel guide, rooming confirmation
├─ Messages         thread with ops (agent can answer FAQs; humans own changes)
└─ Team access      invite assistant coach / AD / team manager (staff only)
```

### 5.2 Desktop wireframe — Overview

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ ∞ INFINITY GLOBAL SPORTS · TRIP PORTAL        Lakeshore W. Soccer ▾   Sofía ⓘ│
├───────────────┬──────────────────────────────────────────────────────────────────┤
│ Overview  ●   │  ARGENTINA · MAR 7–16, 2027                                      │
│ Itinerary  2  │  ┌────────────────────────┐ ┌───────────────────────────────────┐│
│ Checklist 3/7 │  │ 136                    │ │ NEXT ACTION                       ││
│ Documents     │  │ DAYS TO DEPARTURE      │ │ Upload rooming list (team level)  ││
│ Messages   1  │  │                        │ │ Due Feb 5 · 30 days before travel ││
│ Team access   │  └────────────────────────┘ │ [ START → ]                       ││
│               │                             └───────────────────────────────────┘│
│               │  UPDATES                                                          │
│               │  ● Feb 2  Match 2 moved to Thursday afternoon (opponent request)  │
│               │           Day 06 → Day 07 · View change                           │
│               │  ● Jan 20 Hotel confirmed: Palermo Sports Hotel                   │
│               │  ○ Jan 12 Deposit received — thank you!                           │
│               │                                                                   │
│               │  PAYMENTS                                                         │
│               │  Deposit 30% ✓ paid · Balance $XX,XXX due Jan 21                  │
└───────────────┴──────────────────────────────────────────────────────────────────┘
```

Mobile: sidebar becomes a bottom tab bar (`Overview · Itinerary · Checklist · Messages`), Documents and Team access under "More".

### 5.3 Itinerary updates

- Same day-by-day component as the proposal, but **live**: each item shows status (`Confirmed` / `Pending` / `Changed`) — only coach-relevant statuses, never internal provider states like "requested".
- Changes since the coach's last visit are highlighted with a `CHANGED` badge and a before/after line ("Was: Wed afternoon · Now: Thu afternoon"). An "Acknowledge" button records that the coach saw it (ops sees acknowledgment in the panel).
- Every change is announced by email + portal update; the agent never edits the itinerary itself — changes come from ops actions or approved flows.

### 5.4 Checklist & forms — minors' data rules

The checklist is where player-level data enters the system, so it follows [security.md §3.7](../architecture/security.md) strictly:

| Item | Collected how | Rules |
|---|---|---|
| Rooming list | Structured form (room → players by initials or roster number) or CSV upload | Player names stored in the **separate encrypted player-PII table**, not in trip/lead tables. |
| Passports | Secure upload, one file per traveler, or "team manager confirms all passports valid 6+ months" attestation | Prefer the attestation for v0 (data minimization). If files are uploaded: encrypted bucket, ops-only access, logged. |
| Medical & dietary forms | Per-traveler form, **completed by the parent/guardian** via a per-player link sent by the coach | For under-18 travelers the form requires guardian name + consent checkbox. Never visible to the coach in full — coach sees only "submitted ✓". |
| Insurance | Policy number per team or upload of group policy | |
| Flight details | Team-level arrival/departure flights | Team-level, not personal. |
| Code of conduct / waiver | E-sign by guardian for minors | |

UX rules derived from the security model:
- **Upload path is ops-only on the backend** (§3.7): the portal posts directly to the encrypted store; nothing in these forms is ever sent to an LLM, embedded, or shown in agent traces. The chat/agent can say "your rooming list is still missing" (a status), never read its contents.
- A lock banner on every checklist form: "Player information is encrypted, visible only to the IGS operations team, and deleted 90 days after your trip."
- Under-18 detection: if the team's age group is U13–U19, guardian-completed forms are mandatory and the coach cannot fill medical fields for players.
- Each item shows due date (relative to departure), status (`Not started / In progress / Submitted / Approved`), and who it's waiting on (coach / guardians / IGS).
- Deletion: after the retention window the item shows "Deleted per our data policy on {date}".

```
┌──────────────────────────────────────────────────────────────┐
│ CHECKLIST                                    3 of 7 complete │
│ 🔒 Player info is encrypted, IGS-ops only, deleted 90 days   │
│    after your trip.                                          │
├──────────────────────────────────────────────────────────────┤
│ ✓ Deposit                              Done · Jan 12         │
│ ✓ Team flight details                  Done · Jan 18         │
│ ✓ Insurance (group policy)             Approved by IGS       │
│ ◐ Medical & dietary forms   18/27 guardians submitted        │
│   [ RESEND LINKS TO 9 GUARDIANS ]      Due Feb 5             │
│ ○ Rooming list                         Due Feb 5  [ START ]  │
│ ○ Passport validity attestation        Due Feb 5  [ START ]  │
│ ○ Code of conduct (guardian e-sign)    Due Feb 20 [ SEND ]   │
└──────────────────────────────────────────────────────────────┘
```

### 5.5 Messages

One thread per trip with the ops team. The AI agent may answer FAQ-type questions (labeled "Tour planner (AI)") and hand off anything that changes the trip. Messages from ops are labeled with the person's name. Banner repeats the "don't share player personal info here — use the Checklist" rule, with a link.

## 6. Privacy, trust and honesty (cross-cutting)

- **AI disclosure**: every AI-authored bubble is labeled; the first message says it's an AI planner and a human can join anytime.
- **Coach-only audience**: chat and proposal copy address coaches/staff; there is no player sign-up. This keeps the chat outside "directed to children" (COPPA positioning in security.md — counsel to confirm).
- **No player PII in chat**: banner + input masking + agent instruction; the right place for player data is the Checklist.
- **Grounded facts only**: prices, policies, visas, opponent levels come from tools/KB; visa info always ends with "check official sources before booking flights" (from the KB policy).
- **Consent**: contact capture states "We'll email your proposal and follow up about this tour. No marketing lists." Unsubscribe link in every email.
- **Demo disclaimer** in every public footer (brand-reference rule).

## 7. Analytics events (for the ops dashboard funnel)

`chat_opened{entry}` → `slot_captured{slot}` → `kb_answer_shown{source}` → `handoff_requested{reason}` → `contact_captured` → `proposal_viewed{version}` → `proposal_section_viewed{section}` → `proposal_pdf_downloaded` → `question_asked_from_proposal` → `deposit_requested` → `portal_first_login` → `checklist_item_completed{item}` → `itinerary_change_acknowledged`.

No PII in event payloads; ids only.

## 8. Copy deck (v0 strings)

| Key | Copy |
|---|---|
| launcher | PLAN YOUR TEAM'S TOUR |
| greeting | Hi coach — I'm the IGS tour planner (AI). Tell me about your team and I'll sketch a tour in minutes. A person from our team can join anytime. |
| pii_banner | Please don't share players' personal info (birthdates, passports, medical) here. |
| handoff_cta | Talk to a person |
| proposal_ready | Your proposal is ready. |
| proposal_pending | Your proposal is being reviewed by our team — you'll get it by email within 1 business day. |
| reserve_cta | RESERVE WITH 30% DEPOSIT |
| reserve_confirm | Thanks! Our team will send the deposit invoice within 1 business day. |
| portal_lock | Player information is encrypted, visible only to the IGS operations team, and deleted 90 days after your trip. |
| error_generic | Something went wrong on our side. Try again, or leave your email and we'll follow up. |
| footer_demo | Demo built by Mauricio Villalba — not an official Infinity Global Sports product. |

## 9. Open questions

1. **Photography**: we can't reuse IGS's photos without permission. v0 uses licensed stock; is a short "photos are placeholders" note needed on the demo?
2. **Costa Rica accent**: the site defines no Costa Rica color; using warm neutral `#B2896C` for now.
3. **Deposit flow**: v0 stops at "deposit requested". Is a payments provider in scope for any later phase?
4. **Proposal edits from the coach**: change requests go to ops (approval) — confirm we never auto-apply coach edits, even small ones.
5. **Guardian forms** need their own lightweight surface (per-player link, mobile-first). Specify in a follow-up doc or fold into the portal spec?
6. **Language**: agent replies in the coach's language; is Spanish/Portuguese UI chrome needed for Latin American teams visiting the US camps?
7. **Widget embedding**: requires IGS to add a script tag — for the demo we simulate it on a static page that mimics their homepage layout (with the disclaimer), not by framing their real site.

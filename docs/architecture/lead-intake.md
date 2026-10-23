# Lead intake: the site form and the sales inbox

IGS's [Plan a Tour](https://infinityglobalsports.com/plan-a-tour) form promises *"We will respond with sample itinerary options within 1 business day."* Intake turns that promise into a clock and does the first pass for sales. Every inquiry, whether it comes from the form or from an email, ends up as:

- a **contact**, deduplicated by email and linked to its **account**;
- an **extraction** of what the coach actually said. Unknown values stay `null`;
- a **score from 0 to 100**, where every point carries a reason in Spanish;
- a drafted **first reply** with call times, sitting in Aprobaciones as an ordinary `send_email` approval that can be edited and then approved;
- a **due time** (1 business day), which Hoy sorts by;
- a **lead**, but only once every field the lead model requires is known.

The code lives in:

- `packages/py-common/src/igs_common/intake/`: the pure parts (form, email parsing, extraction, levels, travel windows, score, reply, business-day clock);
- `services/core/src/igs_core/intake.py`: the pipeline that runs in one tenant transaction;
- `services/core/src/igs_core/api/v1/intake.py`: the routes;
- migration `0005`: the `lead_intakes` table, with RLS.

## Inbound

| Route | Body | Auth |
|---|---|---|
| `POST /v1/intake/form` | The form's fields as JSON or urlencoded: `first_name`, `last_name`, `program`, `role`, `email`, `phone_country_code`, `phone`, `travel_window`, `how_heard`, `message`, `utm_*`, `gclid`, `landing_page`, `segment`, plus the `website` honeypot. These were read from the live form on 2026-10-22. | HMAC, or the public site key from an allowed `Origin` |
| `POST /v1/intake/email` | One raw RFC 822 message | HMAC only |

**HMAC**
- Headers: `X-IGS-Timestamp: <unix seconds>` and `X-IGS-Signature: sha256=<hex>`.
- Signature: `HMAC-SHA256(IGS_INTAKE_HMAC_SECRET, "<timestamp>.<raw body>")`.
- Timestamps more than 5 minutes off are rejected.

**Site key**
- Headers: `X-IGS-Site-Key` (`IGS_INTAKE_SITE_KEY`), sent from an origin listed in `IGS_INTAKE_ALLOWED_ORIGINS`.
- This is for a browser that posts the form directly. The key is public; what protects the route is the rate limit (5 per 10 minutes per address) plus the honeypot.

**Nothing configured**
- In demo mode only, unsigned posts go to the demo tenant.

**Responses**
- `202 {id, status: "received", reply_by}`. `reply_by` is the promised reply time, which the site can show to the coach.
- A bot that fills the honeypot gets the same answer. Its submission is stored as `spam`, with no contact and no reply.

**Email shapes handled**
- A coach writing directly.
- Gmail, Apple Mail and Outlook inline forwards: the coach is found in the forwarded block, and the forwarder's note is kept apart.
- A message forwarded as an attachment (`message/rfc822`).
- Form notifications from `noreply@…`: the coach is taken from `Reply-To`.
- HTML-only mail.
- Quoted history (`On … wrote:` and `>` lines) and signatures are trimmed. For a reply, the subject is ignored because it is our own words.

## Pipeline

1. **Idempotency.**
   - A form submission is keyed by a hash of email, program, window and message; an email by its `Message-ID`.
   - Resending returns the same intake.
2. **Who is it.**
   - The contact is found by email.
   - The account comes from the contact, else from a program name equal to an account name, else from a colleague on the same institutional domain (free-mail domains never match).
   - The relationship is:
     - `returning_customer` if the account has a confirmed, in-progress or completed trip;
     - `referral` if they chose "Referral / Word of Mouth";
     - `known_contact` if we know them;
     - `new` otherwise.
   - If someone picks "Returning Customer" and we can't find a trip, the score gets a reason that asks ops to verify.
3. **Follow-ups merge.**
   - A new message from a contact who already has an `open` intake (within 60 days) updates that intake.
   - New values fill gaps and never erase old ones.
   - The response clock restarts, and the reply nobody approved yet is superseded by a new one.
4. **Extraction** (`extract.py`).
   - **With a model.** The extractor model returns each value together with a verbatim quote. A value whose quote isn't in the coach's text is dropped and recorded in `extracted.rejected`.
   - **Without a model.** When no model is configured, or the model fails, regex rules run instead. They find less, but they never invent.
   - **Derived values come from code.**
     - `level_score` comes from the level label through a fixed table (`levels.py`). "Di Marco" is not Division I.
     - `age_group` is `College` for NCAA, NAIA or NJCAA.
     - `travel_start` is set only from an exact day, or from the 1st of a stated month (flagged `travel_start_precision: "month"`). "Spring break 2027" is a window used for scoring, not a date.
5. **Lead.** A lead is created (`source: webhook`, `lead.created` event) only when sport, gender, age group, level, group size, destination, start date and duration are all known. Until then the intake stays `open` and the reply asks for what's missing.
6. **Score** (`score.py`). Fixed rules that sales can argue with:
   - returning customer, referral or known contact;
   - a decision maker writing;
   - the travel window (6–18 months ahead is ideal);
   - group size (20–35 is typical);
   - a budget stated;
   - an `.edu` email;
   - how many of the 8 fields are known.
7. **Reply** (`reply.py`).
   - A template, not a model. It contains no prices, no availability and no rivals.
   - It asks at most 4 questions, only about the gaps, and offers 3 call times (ET) at least 4 working hours out. There is no calendar integration yet, so ops confirms the slot.
   - It becomes a pending `send_email` approval for `ops`. The approval details carry the intake id, score and reasons, missing fields, due time and call slots.
8. **Clock** (`sla.py`).
   - One business day is 9 working hours, Monday to Friday, 09:00–18:00 in `IGS_INTAKE_TIMEZONE` (default `America/New_York`), skipping US federal holidays.
   - The states are `on_track`, `at_risk` (≤ 3 working hours left), `breached`, `met` and `missed`.
   - Approving the reply stops the clock, including when the reply was edited before approval (`approvals.decide` → `mark_responded`).

## Ops reads

- `GET /v1/intake?status=open`: inquiries ordered by due time, each with `sla_state`, `business_hours_left`, score, missing fields and links (`lead_id`, `account_id`, `approval_id`).
- `GET /v1/intake/sla`: open, on track, at risk and breached counts, the earliest due time, and met or missed over the last 7 days. This is meant for Hoy.
- `GET /v1/intake/{id}`: the full record, including the extraction with evidence and rejections, the score reasons, the text the coach wrote and the fields as submitted.

The public demo principal can read these, but emails and phones are masked (`j***@domain`).

## Not done yet

- A web view (Hoy tile and inquiry detail). `apps/web` was out of scope.
- Actually sending the approved email. Like every `send_email` approval today, approval is recorded and emitted as an event.
- Terraform wiring of `IGS_INTAKE_HMAC_SECRET` and the site key.
- A calendar for the call slots.
- An LLM eval set for intake extraction.

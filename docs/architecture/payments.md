# Payments: schedule, risks and reminders (UC-09)

`igs_common.payments` turns IGS's published terms into daily operations work: who owes what,
how late, and a reminder that a person approves before it leaves.

## Terms (`terms.py`)

From infinityglobalsports.com/terms-and-conditions (checked 2026-10-22):

| Rule | Value |
|---|---|
| Enrollment fee | US$95 per traveler, non-refundable, due at enrollment |
| Manual plan | US$500 at +30 days, US$500 at +90 days, balance 110 days before departure |
| Installment on/after the balance date | folded into the balance |
| Enrollment on/after the balance date (late) | everything due at enrollment |
| Late fee | US$100 per missed payment (shown to ops, never charged automatically) |
| Seat at risk | 30+ days overdue (ops policy) |
| Refunds | ≥150 d: all but US$95 · 149–110 d: also US$300 · 109–45 d: also 50 % of the price · ≤44 d: none (`refund_due`) |

Assumption: the enrollment fee counts toward the program price (`fee_included_in_price`).

## One source of truth for money

The trip ledger in `trips.pricing`, written by the importer (`igs_common.importer`):

- `pricing.payments` — `{payment_ref: {kind, amount_usd, due_date, paid_at}}`. When a trip has
  invoices, **they are the schedule**: the operator's own invoices beat anything derived.
- `pricing.paid_usd` — sum of paid invoices (or the seed's deposit).

Without invoices the schedule is derived from the terms for the whole group, from
`pricing.payment_terms` (team-level facts, no traveler row carries them):
`enrollment_due` (team not enrolled yet: every seat owes US$95 by then),
`group_enrolled_on` (enrolled: each seat follows the manual plan, `paid_usd` spread across
seats), `balance_due_override` (negotiated date). Seats = imported roster size, else
`trips.travelers`. There is no per-traveler payment table.

## Stages

Each open item, for the **Buenos Aires** operations day (`ops_today`):
`t_minus_7` (2–7 days) → `t_minus_1` (0–1) → `overdue` (1–6 late) → `overdue_7` (7–29) →
`cancellation_risk` (30+). Payments apply oldest-due first.

## Reminders

1. `PaymentReminders` workflow (worker, queue `flows`), daily 09:00 Buenos Aires
   (Temporal Schedules from `payments.temporal.ensure_payment_schedules`, created by
   `demo_reset.py`): load positions → one reminder per trip at its worst stage →
   draft → approvals.
2. **Facts from code, tone from the model.** The model writes subject, opening and closing
   around a `[[DETAILS]]` placeholder; the amounts/dates table is rendered by code. Any number
   in the model's text that isn't a fact rejects the draft and the deterministic template is
   used instead (`details.draft.problems` says why). The model gets the coach's first name
   only: no emails, no traveler names.
3. Each reminder is a pending approval (`send_payment_reminder`, write-external, ops), keyed
   by `details.dedupe_key` (trip + stage + items): re-runs never duplicate, a rejection is not
   retried, the next escalation stage is a new reminder.
4. Every 10 minutes approved reminders whose payload still matches their hash become
   `payment.reminder_send_requested` outbox events (released once). Nothing is sent without a
   person approving that exact email.

Recipients are adults only: the lead's contact (the coach) with the athletic director /
decision maker / finance contact in copy. Minors can't have contact data
(`travelers.minor_no_contact`).

## Where it shows up

- **Account 360 health**: trips with a schedule use it instead of the trip-total rule —
  amber when overdue or due within 14 days, red at cancellation risk or overdue with departure
  inside 30 days.
- **Copilot / MCP**: `list_payment_risks` (read) — overdue and upcoming lines, worst first,
  with late fees; no people in it.

The seed gives Lakeshore (IGS-2711) `payment_terms.enrollment_due` a week before the anchor:
24 × US$95 = US$2,280 overdue, matching the demo story.

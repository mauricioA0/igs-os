# Morning ops digest

What the ops team reads at 07:30 before opening the panel: the same records as the **Hoy**
screen, ranked, with the next action for each and a link to act on it.

| Surface | Where |
|---|---|
| API | `GET /v1/digest/today` (`format=json` default, `html` for the email, `text`) |
| MCP / copilot | tool `daily_digest` (read) — "what needs attention today?" starts here |
| Email | Cloud Run job `python -m igs_core.digest_job`, weekdays 07:30 Buenos Aires via Cloud Scheduler (`infra/terraform/modules/digest_job`, `enable_daily_digest`, **off by default, not applied**) |

## Sections and rules (`igs_common.digest.build`)

- **Riesgos** (top 5): clients the deterministic health rules mark red/amber (same
  `compute_health` as Account 360) plus open incidents of medium severity or worse. Score: critical
  incident 130 > red client 100 (+30 when a dated commitment is ≤ 3 days away) > high incident 95 >
  amber 50 > medium incident 40. **Next action**, from records only: a pending approval about the
  client, its trips or leads → the soonest open dated commitment → a rule from the health reason.
- **Pagos**: live trips whose final balance (IGS terms: due 110 days before departure) is overdue
  or due within 14 days, and open dated commitments/risks about money (fees, balance, wire, PO…).
- **Aprobaciones**: effectively pending (same rule as the inbox badge), oldest first, with hours
  waiting and hours to expiry.
- **Salidas en 14 días**: proposed/confirmed trips leaving within 14 days and their items still
  pending/requested.
- **Leads sin respuesta**: `new`/`qualified` leads with no outbound human contact (email, call,
  WhatsApp, meeting — the web chat's own replies don't count) past **1 business day** (IGS's
  promise). Business days are Mon–Fri on Buenos Aires time; a weekend inquiry starts Monday 09:00.
  Holidays are not modeled yet.

## The model only phrases — and is checked

`phrase_summary` gives the model the facts JSON and asks for 2–3 sentences. `numbers.check_numbers`
extracts every numeric token and requires it to match a number in the facts (amounts, counts, day
offsets, date parts, numbers inside stored statements; ids, links and clock times excluded; `2,280`
and `2.280` both read as 2280; a separator before exactly three digits is always thousands, so
`3,000` never passes as `3`). On failure the model gets one retry naming the offending tokens; then
the deterministic template is used. Provider errors also fall back. The API caches the opening per
tenant until the facts change, so the public demo can't spend tokens by refreshing.

Known limit: numbers written as words ("tres") are not checked; the prompt requires digits.

## Delivery

The job prints the text version, optionally writes `--out` files, records a `digest.generated`
outbox event (flows can react: e.g. post to WhatsApp), and, when `IGS_DIGEST_WEBHOOK_URL` and
`IGS_DIGEST_TO` are set, POSTs `{to, subject, html, text, facts}` to a mail relay the deployment
owns. The job never holds SMTP credentials.

```bash
IGS_DATABASE_URL=postgresql+asyncpg://igs:igs@localhost:5433/igs IGS_DB_APP_ROLE=igs_app \
  uv run python -m igs_core.digest_job --tenant igs --no-event --out /tmp/digest
```

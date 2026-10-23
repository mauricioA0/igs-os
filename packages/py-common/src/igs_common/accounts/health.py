"""Deterministic account health (account-360.md §2). The LLM never sets health."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from igs_common.db.enums import AccountHealth, FactKind, Sentiment, StakeholderRole, TripStatus
from igs_common.money import usd_es

from .types import AccountSnapshot, HealthResult, TripView

_LIVE_TRIPS = {TripStatus.PROPOSED, TripStatus.CONFIRMED, TripStatus.IN_PROGRESS}
# Who decides at a client: explicit decision makers, and athletic directors (they sign POs).
DECIDER_ROLES = frozenset({StakeholderRole.DECISION_MAKER, StakeholderRole.ATHLETIC_DIRECTOR})
KEY_ROLES = DECIDER_ROLES | {StakeholderRole.CHAMPION}


@dataclass(frozen=True)
class HealthRules:
    departure_window_days: int = 30  # red: balance overdue and departure closer than this
    # IGS Terms & Conditions: "final balance due 110 days before departure".
    balance_due_days_before: int = 110
    balance_due_soon_days: int = 14  # amber: balance due within this many days
    stale_contact_days: int = 21  # amber: decision maker / champion not contacted


def compute_health(
    snapshot: AccountSnapshot, *, today: date, rules: HealthRules | None = None
) -> HealthResult:
    rules = rules or HealthRules()
    red: list[str] = []
    amber: list[str] = []

    # Rule reasons (Spanish, written here) lead; open risks quote the client's own words, often
    # English, so they come after them and the UI marks them "(original en inglés)".
    risk_red: list[str] = []
    risk_amber: list[str] = []
    open_risks = [f for f in snapshot.facts if f.kind is FactKind.RISK and f.is_open]
    for risk in open_risks:
        target = risk_red if risk.severity == "high" else risk_amber
        target.append(f"Riesgo abierto: {risk.statement}")

    for person in snapshot.stakeholders:
        if person.role in DECIDER_ROLES and person.sentiment is Sentiment.NEGATIVE:
            red.append(f"{person.name} (decide) tiene sentimiento negativo")

    for trip in snapshot.trips:
        if trip.status not in _LIVE_TRIPS:
            continue
        if trip.payments is not None and trip.payments.lines:
            _payment_reasons(trip, today=today, rules=rules, red=red, amber=amber)
            continue
        balance = trip.balance_usd
        if balance is None or balance <= 0:
            continue
        due = trip.start_date - timedelta(days=rules.balance_due_days_before)
        days_to_departure = (trip.start_date - today).days
        amount = usd_es(balance)
        if today > due and 0 <= days_to_departure < rules.departure_window_days:
            red.append(f"Saldo vencido de {amount} y salida en {days_to_departure} días")
        elif today > due:
            amber.append(f"Saldo vencido de {amount} (vencía el {due:%d/%m})")
        elif (due - today).days <= rules.balance_due_soon_days:
            amber.append(f"Saldo de {amount} vence el {due:%d/%m}")

    cutoff = datetime.combine(today, datetime.min.time(), tzinfo=UTC) - timedelta(
        days=rules.stale_contact_days
    )
    for person in snapshot.stakeholders:
        if person.role not in KEY_ROLES:
            continue
        if person.last_contact_at is None or person.last_contact_at < cutoff:
            amber.append(
                f"Sin contacto con {person.name} hace más de {rules.stale_contact_days} días"
            )

    red += risk_red
    amber += risk_amber
    if red:
        return HealthResult(AccountHealth.RED, tuple(red + amber))
    if amber:
        return HealthResult(AccountHealth.AMBER, tuple(amber))
    return HealthResult(AccountHealth.GREEN, ("Sin riesgos abiertos ni pagos pendientes",))


def _payment_reasons(
    trip: TripView, *, today: date, rules: HealthRules, red: list[str], amber: list[str]
) -> None:
    """Reasons from the per-traveler schedule (igs_common.payments) instead of the trip total."""
    pos = trip.payments
    assert pos is not None
    name = trip.code or trip.title
    days_to_departure = (trip.start_date - today).days
    if pos.overdue:
        amount = usd_es(pos.overdue_usd)
        if any(line.seats is None for line in pos.overdue):
            count = f"{len(pos.overdue)} pagos"
        else:
            count = f"{sum(line.seats or 0 for line in pos.overdue)} plazas"
        what = f"Pagos vencidos de {amount} en {name} ({count}, el más viejo hace "
        what += f"{pos.oldest_overdue_days} días)"
        if pos.cancellation_risk:
            red.append(f"{what}: riesgo de cancelación")
        elif 0 <= days_to_departure < rules.departure_window_days:
            red.append(f"{what} y salida en {days_to_departure} días")
        else:
            amber.append(what)
    nxt = pos.next_due
    if nxt is not None and nxt.days <= rules.balance_due_soon_days:
        due_total = sum(line.outstanding_usd for line in pos.open_lines if line.due == nxt.due)
        amber.append(f"{usd_es(due_total)} vence el {nxt.due:%d/%m} en {name}")


def next_departure(snapshot: AccountSnapshot, *, today: date) -> TripView | None:
    upcoming = [t for t in snapshot.trips if t.status in _LIVE_TRIPS and t.end_date >= today]
    return min(upcoming, key=lambda t: t.start_date, default=None)

"""Inputs → prioritized facts for the morning digest. Pure: no I/O, no model, same clock for all."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from igs_common.accounts.health import DECIDER_ROLES, HealthRules, compute_health
from igs_common.accounts.types import AccountSnapshot
from igs_common.db.enums import AccountHealth, FactKind

from .types import (
    ApprovalInput,
    ApprovalItem,
    Counts,
    Departure,
    DigestFacts,
    DigestInputs,
    DigestRules,
    IncidentInput,
    Payment,
    Risk,
    StaleLead,
    TripInput,
)

# The ops team works on Buenos Aires time; "today" and business days are in that calendar.
OPS_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

# Dated commitments/risks that are about money (IGS fees, balances, wires, POs, deposits).
_PAYMENT_WORDS = re.compile(
    r"\b(fees?|balance|payment|paid|pay|wire|invoice|deposit|installment|PO|purchase order|"
    r"pago|saldo|cuota|seña|factura|transferencia)\b|US\$|USD",
    re.IGNORECASE,
)
_INCIDENT_SCORE = {"critical": 130, "high": 95, "medium": 40}
_LIVE_TRIPS = {"proposed", "confirmed", "in_progress"}


def build_digest(
    inputs: DigestInputs, *, now: datetime, rules: DigestRules | None = None
) -> DigestFacts:
    rules = rules or DigestRules()
    today = now.astimezone(OPS_TZ).date()
    health = HealthRules()

    risks, red, amber = _account_risks(inputs, today=today)
    risks += _incident_risks(inputs.incidents)
    risks.sort(key=lambda r: (-r[0], r[1].name))
    ranked = tuple(
        Risk(
            rank=i + 1,
            kind=r.kind,
            subject_id=r.subject_id,
            name=r.name,
            level=r.level,
            reason=r.reason,
            next_action=r.next_action,
            link=r.link,
        )
        for i, (_, r) in enumerate(risks[: rules.max_risks])
    )

    payments = sorted(
        [
            *_trip_balances(inputs.trips, today=today, rules=rules, health=health),
            *_dated_commitments(inputs.accounts, today=today, rules=rules),
        ],
        key=lambda p: (p.days, p.name),
    )
    approvals = sorted(inputs.approvals, key=lambda a: a.created_at)
    departures = _departures(inputs.trips, today=today, rules=rules)
    stale = _stale_leads(inputs, now=now, rules=rules)

    return DigestFacts(
        day=today,
        generated_at=now,
        counts=Counts(
            red_accounts=red,
            amber_accounts=amber,
            risks=len(risks),
            payments_due=len(payments),
            payments_overdue=sum(1 for p in payments if p.overdue),
            approvals_pending=len(approvals),
            departures=len(departures),
            stale_leads=len(stale),
            open_incidents=len(inputs.incidents),
        ),
        risks=ranked,
        payments=tuple(payments),
        approvals=tuple(_approval(a, now) for a in approvals[: rules.max_approvals]),
        departures=tuple(departures),
        stale_leads=tuple(stale),
        rules=rules,
    )


# ── Risks ──────────────────────────────────────────────────────────────────


def _account_risks(inputs: DigestInputs, *, today: date) -> tuple[list[tuple[int, Risk]], int, int]:
    out: list[tuple[int, Risk]] = []
    red = amber = 0
    for snap in inputs.accounts:
        result = compute_health(snap, today=today)
        if result.health is AccountHealth.GREEN:
            continue
        is_red = result.health is AccountHealth.RED
        red += is_red
        amber += not is_red
        action, due = _next_action(snap, inputs.approvals, inputs.trips, today=today)
        score = (100 if is_red else 50) + (30 if due is not None and (due - today).days <= 3 else 0)
        out.append(
            (
                score,
                Risk(
                    rank=0,
                    kind="account",
                    subject_id=snap.account_id,
                    name=snap.name,
                    level=result.health.value,
                    reason=result.reasons[0],
                    next_action=action,
                    link=f"/ops/accounts/{snap.account_id}",
                ),
            )
        )
    return out, red, amber


def _next_action(
    snap: AccountSnapshot,
    approvals: tuple[ApprovalInput, ...],
    trips: tuple[TripInput, ...],
    *,
    today: date,
) -> tuple[str, date | None]:
    """What ops should do first for this client, from records (never invented).

    1. A pending approval about the client or one of its trips: deciding it unblocks the rest.
    2. The soonest open dated commitment.
    3. A rule-based step from the health reason.
    """
    subjects = {snap.account_id, *(t.id for t in snap.trips), *(lead.id for lead in snap.leads)}
    subjects |= {t.id for t in trips if t.account_id == snap.account_id}
    mine = [
        a
        for a in approvals
        if (a.subject_id is not None and a.subject_id in subjects) or snap.name in a.title
    ]
    commitments = sorted(
        (
            f
            for f in snap.facts
            if f.kind in (FactKind.COMMITMENT, FactKind.RISK) and f.is_open and f.due_date
        ),
        key=lambda f: f.due_date or today,
    )
    due = commitments[0].due_date if commitments else None
    if mine:
        first = min(mine, key=lambda a: a.created_at)
        return f"Decidir la aprobación «{first.title}»", due
    if commitments:
        c = commitments[0]
        return f"Antes del {c.due_date:%d/%m}: {c.statement.rstrip('. ')}", due
    decider = next((p.name for p in snap.stakeholders if p.role in DECIDER_ROLES), None)
    reason = compute_health(snap, today=today).reasons[0]
    if reason.startswith("Saldo"):
        return f"Llamar a {decider or 'quien decide'} por el saldo", due
    if "sentimiento negativo" in reason:
        return f"Agendar una llamada con {reason.split(' (decide)')[0]}", due
    if reason.startswith("Sin contacto con "):
        name = reason.removeprefix("Sin contacto con ").split(" hace ")[0]
        return f"Escribirle hoy a {name}", due
    return "Asignar responsable y plan para el riesgo", due


def _incident_risks(incidents: tuple[IncidentInput, ...]) -> list[tuple[int, Risk]]:
    out: list[tuple[int, Risk]] = []
    for inc in incidents:
        score = _INCIDENT_SCORE.get(inc.severity)
        if score is None:
            continue
        label = inc.trip_code or "gira"
        out.append(
            (
                score,
                Risk(
                    rank=0,
                    kind="incident",
                    subject_id=inc.id,
                    name=f"Incidente en {label}",
                    level=inc.severity,
                    reason=inc.title,
                    next_action="Confirmar con el tour leader que está contenido",
                    link=f"/ops/trips/{inc.trip_id}",
                ),
            )
        )
    return out


# ── Payments ───────────────────────────────────────────────────────────────


def _trip_balances(
    trips: tuple[TripInput, ...], *, today: date, rules: DigestRules, health: HealthRules
) -> list[Payment]:
    out = []
    for t in trips:
        balance = t.balance_usd
        if t.status not in _LIVE_TRIPS or balance is None or balance <= 0:
            continue
        due = t.start_date - timedelta(days=health.balance_due_days_before)
        days = (due - today).days
        if days > rules.payment_window_days:
            continue
        out.append(
            Payment(
                source="trip_balance",
                subject_id=t.id,
                name=t.account_name or t.title,
                label=f"Saldo final de {t.code or t.title}",
                amount_usd=balance.quantize(Decimal(1)),
                due_date=due,
                days=days,
                link=f"/ops/trips/{t.id}",
            )
        )
    return out


def _dated_commitments(
    accounts: tuple[AccountSnapshot, ...], *, today: date, rules: DigestRules
) -> list[Payment]:
    out = []
    for snap in accounts:
        for f in snap.facts:
            if f.kind not in (FactKind.COMMITMENT, FactKind.RISK) or not f.is_open:
                continue
            if f.due_date is None or not _PAYMENT_WORDS.search(f.statement):
                continue
            days = (f.due_date - today).days
            if days > rules.payment_window_days:
                continue
            out.append(
                Payment(
                    source="commitment",
                    subject_id=snap.account_id,
                    name=snap.name,
                    label=f.statement,
                    amount_usd=None,
                    due_date=f.due_date,
                    days=days,
                    link=f"/ops/accounts/{snap.account_id}",
                )
            )
    return out


# ── Approvals, departures, leads ───────────────────────────────────────────


def _approval(a: ApprovalInput, now: datetime) -> ApprovalItem:
    expires = None
    if a.expires_at is not None:
        expires = max(0, int((a.expires_at - now).total_seconds() // 3600))
    return ApprovalItem(
        id=a.id,
        title=a.title,
        waiting_hours=max(0, int((now - a.created_at).total_seconds() // 3600)),
        expires_in_hours=expires,
        link=f"/ops/approvals?id={a.id}",
    )


def _departures(
    trips: tuple[TripInput, ...], *, today: date, rules: DigestRules
) -> list[Departure]:
    out = []
    for t in trips:
        days = (t.start_date - today).days
        if (
            t.status not in ("proposed", "confirmed")
            or not 0 <= days <= rules.departure_window_days
        ):
            continue
        out.append(
            Departure(
                trip_id=t.id,
                code=t.code,
                title=t.title,
                account_name=t.account_name,
                start_date=t.start_date,
                days_to_departure=days,
                open_items=t.open_items,
                travelers=t.travelers,
                link=f"/ops/trips/{t.id}",
            )
        )
    return sorted(out, key=lambda d: (d.start_date, d.title))


def _stale_leads(inputs: DigestInputs, *, now: datetime, rules: DigestRules) -> list[StaleLead]:
    out = []
    for lead in inputs.leads:
        if lead.answered:
            continue
        deadline = add_business_days(lead.created_at, rules.lead_sla_business_days)
        if now <= deadline:
            continue
        out.append(
            StaleLead(
                lead_id=lead.id,
                organization=lead.organization or lead.contact_name or "Sin organización",
                contact_name=lead.contact_name,
                sport=lead.sport,
                group_size=lead.group_size,
                created_at=lead.created_at,
                business_days_waiting=business_days_between(lead.created_at, now),
                link=f"/ops/leads?id={lead.id}",
            )
        )
    return sorted(out, key=lambda s: s.created_at)


def add_business_days(start: datetime, days: int) -> datetime:
    """`start` + `days` business days (Mon–Fri, ops calendar; holidays not modeled).

    An inquiry that arrives on a weekend starts the clock on Monday at 09:00.
    """
    local = start.astimezone(OPS_TZ)
    if local.weekday() >= 5:
        monday = local.date() + timedelta(days=7 - local.weekday())
        local = datetime.combine(monday, time(9), tzinfo=OPS_TZ)
    added = 0
    while added < days:
        local += timedelta(days=1)
        if local.weekday() < 5:
            added += 1
    return local


def business_days_between(start: datetime, end: datetime) -> int:
    """Whole business days after `start`'s day, up to and including `end`'s day."""
    first, last = start.astimezone(OPS_TZ).date(), end.astimezone(OPS_TZ).date()
    count, day = 0, first
    while day < last:
        day += timedelta(days=1)
        count += day.weekday() < 5
    return count

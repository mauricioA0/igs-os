"""Pre-departure readiness: which travelers are missing what, and by when.

Pure and deterministic: rules + trip + roster + document statuses + today → a report. No model,
no I/O, so ops can trust it and tests pin it. The MCP tool, the flow action and the API all render
this same report.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

from igs_common.readiness.rules import SEVERITY_RANK, RequirementRule, RuleSet, load_rules

DocStatus = Literal["missing", "requested", "received", "verified", "not_applicable"]
DOC_STATUSES: tuple[DocStatus, ...] = (
    "missing",
    "requested",
    "received",
    "verified",
    "not_applicable",
)
ItemState = Literal["ok", "waived", "missing", "requested", "received", "invalid"]
SATISFIED: frozenset[str] = frozenset({"ok", "waived"})


@dataclass(frozen=True)
class TripInfo:
    id: str
    country: str
    start_date: date
    end_date: date
    code: str | None = None
    title: str | None = None


@dataclass(frozen=True)
class TravelerInfo:
    id: str
    full_name: str
    role: str = "player"
    is_minor: bool = False
    birth_year: int | None = None


@dataclass(frozen=True)
class DocumentInfo:
    requirement: str
    status: DocStatus = "missing"
    valid_from: date | None = None
    valid_until: date | None = None
    note: str | None = None


@dataclass
class Item:
    requirement: str
    label: str
    severity: str
    state: ItemState
    due_on: date
    overdue: bool
    sources: tuple[str, ...]
    reason: str | None = None
    hint: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        return self.state not in SATISFIED and self.severity != "recommended"

    def as_dict(self) -> dict[str, Any]:
        return {
            "requirement": self.requirement,
            "label": self.label,
            "severity": self.severity,
            "state": self.state,
            "due_on": self.due_on.isoformat(),
            "overdue": self.overdue,
            "blocking": self.blocking,
            "reason": self.reason,
            "hint": self.hint,
            "warnings": self.warnings,
            "sources": list(self.sources),
        }


def _add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    for day in (d.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise AssertionError("unreachable")


def _applies(rule: RequirementRule, traveler: TravelerInfo, start: date) -> bool:
    when = rule.when
    if when.minor is not None and when.minor != traveler.is_minor:
        return False
    if when.max_age is not None:
        if not traveler.is_minor:
            return False
        # Only a birth year is stored for minors: they may be one year younger than
        # `year - birth_year`. Apply the stricter rule whenever they could be young enough.
        if traveler.birth_year is not None and start.year - traveler.birth_year - 1 > when.max_age:
            return False
    return True


def _state(doc: DocumentInfo | None) -> ItemState:
    status = doc.status if doc else "missing"
    return {
        "verified": "ok",
        "not_applicable": "waived",
        "received": "received",
        "requested": "requested",
    }.get(status, "missing")  # type: ignore[return-value]


class ReadinessChecker:
    def __init__(self, rules: RuleSet | None = None) -> None:
        self.rules = rules or load_rules()

    def check(
        self,
        trip: TripInfo,
        travelers: Iterable[TravelerInfo],
        documents: Mapping[str, Iterable[DocumentInfo]],
        *,
        today: date,
    ) -> dict[str, Any]:
        destination = self.rules.destination(trip.country)
        rules = self.rules.rules_for(destination)
        active = [r for r in rules if r.in_force(trip.start_date)]
        upcoming = [
            {
                "requirement": r.key,
                "label": self.rules.requirements[r.key].label,
                "effective_from": r.effective_from.isoformat() if r.effective_from else None,
                "note": r.note,
            }
            for r in rules
            if not r.in_force(trip.start_date)
        ]
        people = []
        for t in travelers:
            docs = {d.requirement: d for d in documents.get(t.id, ())}
            items = self._items(trip, t, active, docs, today)
            blocking = [i for i in items if i.blocking]
            people.append(
                {
                    "traveler_id": t.id,
                    "full_name": t.full_name,
                    "role": t.role,
                    "is_minor": t.is_minor,
                    "ready": not blocking,
                    "missing": [i.requirement for i in blocking],
                    "overdue": [i.requirement for i in blocking if i.overdue],
                    "items": [i.as_dict() for i in items],
                }
            )

        open_items = [i for p in people for i in p["items"] if i["blocking"]]
        by_requirement: dict[str, dict[str, int]] = {}
        for p in people:
            for i in p["items"]:
                counts = by_requirement.setdefault(
                    i["requirement"], {"done": 0, "open": 0, "overdue": 0}
                )
                counts["done" if i["state"] in SATISFIED else "open"] += 1
                counts["overdue"] += int(i["overdue"] and i["blocking"])
        next_due = min((i["due_on"] for i in open_items if not i["overdue"]), default=None)
        warnings = []
        if destination is None:
            warnings.append(
                f"No entry rules for {trip.country!r}: only IGS defaults were checked. "
                "Check official sources and add the destination to the rules."
            )
        if not people:
            warnings.append("No travelers on the roster yet.")
        return {
            "trip": {
                "id": trip.id,
                "code": trip.code,
                "title": trip.title,
                "country": trip.country,
                "destination": destination.code if destination else None,
                "start_date": trip.start_date.isoformat(),
                "days_to_departure": (trip.start_date - today).days,
            },
            "ready": bool(people) and not open_items,
            "travelers": len(people),
            "travelers_ready": sum(p["ready"] for p in people),
            "open_items": len(open_items),
            "overdue_items": sum(i["overdue"] for i in open_items),
            "blockers": sum(i["severity"] == "blocker" for i in open_items),
            "next_due_on": next_due,
            "by_requirement": by_requirement,
            "not_ready": [
                {
                    "traveler_id": p["traveler_id"],
                    "full_name": p["full_name"],
                    "missing": p["missing"],
                    "overdue": p["overdue"],
                }
                for p in people
                if not p["ready"]
            ],
            "people": people,
            "upcoming_rules": upcoming,
            "warnings": warnings,
            "rules": {
                "version": self.rules.version,
                "checked_on": self.rules.checked_on.isoformat(),
                "nationality": self.rules.nationality,
                "sources": {
                    k: s.model_dump()
                    for k, s in self.rules.sources.items()
                    if any(k in r.sources for r in active)
                },
            },
        }

    def _items(
        self,
        trip: TripInfo,
        traveler: TravelerInfo,
        rules: list[RequirementRule],
        docs: Mapping[str, DocumentInfo],
        today: date,
    ) -> list[Item]:
        # One item per requirement: the strictest applicable rule wins.
        chosen: dict[str, RequirementRule] = {}
        for r in rules:
            if not _applies(r, traveler, trip.start_date):
                continue
            prev = chosen.get(r.key)
            if prev is None or SEVERITY_RANK[r.severity] > SEVERITY_RANK[prev.severity]:
                chosen[r.key] = r
        items = []
        for key, rule in chosen.items():
            spec = self.rules.requirements[key]
            doc = docs.get(key)
            due = trip.start_date - timedelta(days=spec.due_days_before)
            item = Item(
                requirement=key,
                label=spec.label,
                severity=rule.severity,
                state=_state(doc),
                due_on=due,
                overdue=False,
                sources=rule.sources,
                reason=rule.note,
                hint=spec.hint,
            )
            if spec.kind == "passport" and doc is not None and item.state != "waived":
                self._passport(item, trip, doc)
            elif doc is not None and doc.valid_until and doc.valid_until < trip.end_date:
                item.state = "invalid"
                item.warnings.append(
                    f"Expires {doc.valid_until.isoformat()}, before the trip ends."
                )
            item.overdue = item.state not in SATISFIED and today > due
            if doc is not None and doc.note:
                item.warnings.append(doc.note)
            items.append(item)
        return sorted(items, key=lambda i: (-SEVERITY_RANK[i.severity], i.due_on, i.requirement))

    def _passport(self, item: Item, trip: TripInfo, doc: DocumentInfo) -> None:
        destination = self.rules.destination(trip.country)
        rule = self.rules.passport_rule(destination)
        if doc.valid_until is not None:
            needed = _add_months(trip.end_date, rule.months_after)
            if doc.valid_until < needed:
                item.state = "invalid"
                item.warnings.append(
                    f"Expires {doc.valid_until.isoformat()}; must be valid through "
                    f"{needed.isoformat()}. Renew now."
                )
            elif rule.recommended_months_after_return is not None:
                advised = _add_months(trip.end_date, rule.recommended_months_after_return)
                if doc.valid_until < advised:
                    item.warnings.append(
                        f"Expires {doc.valid_until.isoformat()}: under "
                        f"{rule.recommended_months_after_return} months after return; "
                        "some airlines refuse boarding."
                    )
        elif item.state == "ok":
            item.warnings.append("Verified without an expiry date on file.")
        if rule.max_issued_years is not None and doc.valid_from is not None:
            oldest = _add_months(trip.start_date, -12 * rule.max_issued_years)
            if doc.valid_from < oldest:
                item.state = "invalid"
                item.warnings.append(
                    f"Issued {doc.valid_from.isoformat()}: more than {rule.max_issued_years} "
                    "years before entry. Renew now."
                )
        if rule.blank_pages:
            item.warnings.append(f"Needs {rule.blank_pages} blank visa pages.")

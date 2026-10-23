"""Diff validated records against the tenant's data, then (unless dry run) write the diff.

Rules that make re-running the same file safe:
- Rows match existing data by natural key (`EntitySpec.key`), case-insensitively.
- Only columns present and non-empty in the file are compared and written; nothing is blanked.
- Nothing is ever deleted. A second run of the same file reports every row as "unchanged".
- All or nothing: with any error in the file, nothing is written.

The session must be tenant-scoped (`session_scope`), so RLS applies to every read and write;
`tenant_id` filters are repeated as defense in depth.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.db.base import uuid7
from igs_common.db.enums import (
    AccountKind,
    AccountStatus,
    ActorType,
    InteractionChannel,
    ProviderKind,
    Sentiment,
    StakeholderRole,
    TravelerRole,
    TripStatus,
)
from igs_common.db.models import Account, AuditLog, Provider, Stakeholder, Traveler, Trip
from igs_common.importer.report import ChangeOut, Counts
from igs_common.importer.schema import APPLY_ORDER, Entity
from igs_common.importer.validate import Issue, Record, ValidatedSheet

_ENUMS: dict[tuple[Entity, str], type[StrEnum]] = {
    (Entity.ACCOUNTS, "kind"): AccountKind,
    (Entity.ACCOUNTS, "status"): AccountStatus,
    (Entity.STAKEHOLDERS, "role"): StakeholderRole,
    (Entity.STAKEHOLDERS, "sentiment"): Sentiment,
    (Entity.STAKEHOLDERS, "preferred_channel"): InteractionChannel,
    (Entity.PROVIDERS, "kind"): ProviderKind,
    (Entity.TRIPS, "status"): TripStatus,
    (Entity.TRAVELERS, "role"): TravelerRole,
}


@dataclass
class _Op:
    entity: Entity
    record: Record
    key_label: str
    model: type[Any]
    obj: Any | None  # existing row, None for a create
    values: dict[str, Any]  # create: all column values; update: only the changed ones
    before: dict[str, Any] = field(default_factory=dict)


@dataclass
class Plan:
    ops: list[_Op]
    issues: list[Issue]
    summary: dict[str, Counts]
    changes: list[ChangeOut]


def _fold(value: object) -> str:
    return str(value or "").casefold()


def _jsonable(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _typed(entity: Entity, values: dict[str, Any]) -> dict[str, Any]:
    out = {}
    for k, v in values.items():
        enum = _ENUMS.get((entity, k))
        out[k] = enum(v) if enum is not None and v is not None else v
    return out


def _diff(obj: Any, values: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    changed, before = {}, {}
    for k, v in values.items():
        current = getattr(obj, k)
        if _jsonable(current) != _jsonable(v):
            changed[k], before[k] = v, current
    return changed, before


class _Planner:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.s = session
        self.tenant_id = tenant_id
        self.ops: list[_Op] = []
        self.issues: list[Issue] = []
        self.accounts: dict[str, uuid.UUID] = {}
        self.trips: dict[str, uuid.UUID] = {}
        # Trip pricing as it will be after this import (payments + price/travelers changes).
        self.pricing: dict[uuid.UUID, dict[str, Any]] = {}
        self.pricing_before: dict[uuid.UUID, dict[str, Any]] = {}
        self.trip_ops: dict[uuid.UUID, _Op] = {}
        self.trip_objs: dict[uuid.UUID, Trip] = {}

    def _op(
        self,
        entity: Entity,
        rec: Record,
        label: str,
        model: type[Any],
        existing: Any | None,
        values: dict[str, Any],
    ) -> _Op:
        typed = _typed(entity, values)
        if existing is None:
            op = _Op(entity, rec, label, model, None, {"id": uuid7(), **typed})
        else:
            changed, before = _diff(existing, typed)
            op = _Op(entity, rec, label, model, existing, changed, before)
        self.ops.append(op)
        return op

    def _missing_ref(self, rec: Record, column: str, what: str, value: str) -> None:
        self.issues.append(
            Issue(
                "error",
                rec.sheet,
                rec.row,
                column,
                "unknown-reference",
                f"{what} '{value}' is neither in IGS OS nor in this file",
            )
        )

    async def accounts_(self, records: list[Record]) -> None:
        rows = (
            await self.s.scalars(select(Account).where(Account.tenant_id == self.tenant_id))
        ).all()
        existing = {_fold(a.name): a for a in rows}
        self.accounts = {k: a.id for k, a in existing.items()}
        for rec in records:
            key = _fold(rec.values["name"])
            op = self._op(
                Entity.ACCOUNTS, rec, rec.values["name"], Account, existing.get(key), rec.values
            )
            self.accounts[key] = op.obj.id if op.obj is not None else op.values["id"]

    async def _ensure_accounts_loaded(self) -> None:
        if not self.accounts:
            rows = (
                await self.s.execute(
                    select(Account.id, Account.name).where(Account.tenant_id == self.tenant_id)
                )
            ).all()
            self.accounts = {_fold(name): id_ for id_, name in rows}

    async def stakeholders_(self, records: list[Record]) -> None:
        await self._ensure_accounts_loaded()
        rows = (
            await self.s.scalars(select(Stakeholder).where(Stakeholder.tenant_id == self.tenant_id))
        ).all()
        by_email = {(s.account_id, _fold(s.email)): s for s in rows if s.email}
        by_name = {(s.account_id, _fold(s.name)): s for s in rows}
        for rec in records:
            v = dict(rec.values)
            account_name = v.pop("account_name")
            account_id = self.accounts.get(_fold(account_name))
            if account_id is None:
                self._missing_ref(rec, "account_name", "account", account_name)
                continue
            existing = (
                by_email.get((account_id, _fold(v.get("email")))) if v.get("email") else None
            ) or by_name.get((account_id, _fold(v["name"])))
            self._op(
                Entity.STAKEHOLDERS,
                rec,
                f"{account_name} / {v['name']}",
                Stakeholder,
                existing,
                {"account_id": account_id, **v},
            )

    async def providers_(self, records: list[Record]) -> None:
        rows = (
            await self.s.scalars(select(Provider).where(Provider.tenant_id == self.tenant_id))
        ).all()
        existing = {(_fold(p.name), p.kind.value, _fold(p.city)): p for p in rows}
        for rec in records:
            v = rec.values
            key = (_fold(v["name"]), v["kind"], _fold(v["city"]))
            self._op(
                Entity.PROVIDERS, rec, f"{v['name']} ({v['city']})", Provider, existing.get(key), v
            )

    async def _load_trips(self) -> dict[str, Trip]:
        rows = (await self.s.scalars(select(Trip).where(Trip.tenant_id == self.tenant_id))).all()
        existing = {_fold(t.code): t for t in rows if t.code}
        for code, t in existing.items():
            self.trips.setdefault(code, t.id)
            self.trip_objs.setdefault(t.id, t)
            self.pricing.setdefault(t.id, dict(t.pricing or {}))
            self.pricing_before.setdefault(t.id, dict(t.pricing or {}))
        return existing

    async def trips_(self, records: list[Record]) -> None:
        await self._ensure_accounts_loaded()
        existing = await self._load_trips()
        for rec in records:
            v = dict(rec.values)
            account_name = v.pop("account_name", None)
            if account_name is not None:
                account_id = self.accounts.get(_fold(account_name))
                if account_id is None:
                    self._missing_ref(rec, "account_name", "account", account_name)
                    continue
                v["account_id"] = account_id
            obj = existing.get(_fold(v["code"]))
            op = self._op(Entity.TRIPS, rec, v["code"], Trip, obj, v)
            trip_id = obj.id if obj is not None else op.values["id"]
            self.trips[_fold(v["code"])] = trip_id
            self.trip_ops[trip_id] = op
            pricing = self.pricing.setdefault(trip_id, {})
            self.pricing_before.setdefault(trip_id, {})
            price = v.get("price_per_person_usd", obj.price_per_person_usd if obj else None)
            travelers = v.get("travelers", obj.travelers if obj else None)
            pricing.setdefault("currency", "USD")
            pricing["price_per_person_usd"] = price
            if price is not None and travelers:
                pricing["total_usd"] = price * travelers

    async def _trip_ref(self, rec: Record) -> uuid.UUID | None:
        if not self.trip_objs:
            await self._load_trips()
        trip_id = self.trips.get(_fold(rec.values["trip_code"]))
        if trip_id is None:
            self._missing_ref(rec, "trip_code", "trip", rec.values["trip_code"])
        return trip_id

    async def travelers_(self, records: list[Record]) -> None:
        trip_ids = set()
        for rec in records:
            trip_id = await self._trip_ref(rec)
            if trip_id is not None:
                trip_ids.add(trip_id)
        rows = (
            (
                await self.s.scalars(
                    select(Traveler).where(
                        Traveler.tenant_id == self.tenant_id, Traveler.trip_id.in_(trip_ids)
                    )
                )
            ).all()
            if trip_ids
            else []
        )
        existing = {(t.trip_id, _fold(t.full_name)): t for t in rows}
        for rec in records:
            trip_id = self.trips.get(_fold(rec.values["trip_code"]))
            if trip_id is None:
                continue
            v = dict(rec.values)
            code = v.pop("trip_code")
            obj = existing.get((trip_id, _fold(v["full_name"])))
            if obj is not None and obj.is_minor and "is_minor" not in v:
                # Stored as a minor: the file can't attach contact data without saying otherwise.
                v.pop("email", None)
                v.pop("phone", None)
            self._op(
                Entity.TRAVELERS,
                rec,
                f"{code} / {v['full_name']}",
                Traveler,
                obj,
                {"trip_id": trip_id, **v},
            )

    async def payments_(self, records: list[Record]) -> list[ChangeOut]:
        """Payments live in the trip's pricing snapshot: `pricing.payments[ref]`, `paid_usd`."""
        changes: list[ChangeOut] = []
        touched: set[uuid.UUID] = set()
        for rec in records:
            trip_id = await self._trip_ref(rec)
            if trip_id is None:
                continue
            v = rec.values
            pricing = self.pricing.setdefault(trip_id, {})
            payments: dict[str, Any] = dict(pricing.get("payments") or {})
            ref = v["payment_ref"]
            entry = {
                "kind": v["kind"],
                "amount_usd": v["amount_usd"],
                "due_date": v["due_date"].isoformat(),
                "paid_at": v["paid_at"].isoformat() if v.get("paid_at") else None,
            }
            before = payments.get(ref)
            if before is not None and "paid_at" not in v:
                entry["paid_at"] = before.get("paid_at")  # empty cell never un-pays
            action = "create" if before is None else ("unchanged" if before == entry else "update")
            diff = {
                k: [None if before is None else before.get(k), entry[k]]
                for k in entry
                if before is None or before.get(k) != entry[k]
            }
            payments[ref] = entry
            pricing["payments"] = payments
            touched.add(trip_id)
            changes.append(
                ChangeOut(
                    entity=Entity.PAYMENTS.value,
                    action=action,  # type: ignore[arg-type]
                    key=f"{v['trip_code']} / {ref}",
                    sheet=rec.sheet,
                    row=rec.row,
                    id=str(trip_id),
                    changes={} if action == "unchanged" else diff,
                )
            )
        for trip_id in touched:
            pricing = self.pricing[trip_id]
            paid = sum(p["amount_usd"] for p in pricing["payments"].values() if p.get("paid_at"))
            pricing["paid_usd"] = paid
        return changes

    def pricing_ops(self) -> None:
        """Fold pricing changes into the trip ops (or a pricing-only update of an existing trip)."""
        for trip_id, pricing in self.pricing.items():
            op = self.trip_ops.get(trip_id)
            if op is not None and op.obj is None:
                op.values["pricing"] = pricing
                continue
            if pricing == self.pricing_before.get(trip_id, {}):
                continue
            obj = self.trip_objs[trip_id]
            if op is None:
                continue  # touched only by payments: reported per payment, written below
            op.values["pricing"] = pricing
            op.before["pricing"] = obj.pricing

    def pricing_only_updates(self) -> list[tuple[Trip, dict[str, Any]]]:
        out = []
        for trip_id, pricing in self.pricing.items():
            if trip_id in self.trip_ops:
                continue
            if pricing != self.pricing_before.get(trip_id, {}):
                out.append((self.trip_objs[trip_id], pricing))
        return out


@dataclass
class ImportResult:
    plan: Plan
    applied: bool


async def run_import(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    sheets: list[ValidatedSheet],
    dry_run: bool = True,
    actor: tuple[ActorType, str | None] = (ActorType.SYSTEM, "importer"),
    filename: str = "",
    request_id: str | None = None,
) -> ImportResult:
    by_entity: dict[Entity, list[Record]] = defaultdict(list)
    issues: list[Issue] = []
    for vs in sheets:
        by_entity[vs.spec.entity].extend(vs.records)
        issues.extend(vs.issues)
    planner = _Planner(session, tenant_id)
    payment_changes: list[ChangeOut] = []
    for entity in APPLY_ORDER:
        records = by_entity.get(entity)
        if not records:
            continue
        match entity:
            case Entity.ACCOUNTS:
                await planner.accounts_(records)
            case Entity.STAKEHOLDERS:
                await planner.stakeholders_(records)
            case Entity.PROVIDERS:
                await planner.providers_(records)
            case Entity.TRIPS:
                await planner.trips_(records)
            case Entity.TRAVELERS:
                await planner.travelers_(records)
            case Entity.PAYMENTS:
                payment_changes = await planner.payments_(records)
    planner.pricing_ops()
    issues.extend(planner.issues)

    changes: list[ChangeOut] = []
    summary: dict[str, Counts] = {}
    for op in planner.ops:
        if op.obj is None:
            action, diff = (
                "create",
                {
                    k: [None, _jsonable(v)]
                    for k, v in op.values.items()
                    if k not in ("id", "pricing")
                },
            )
        elif op.values:
            action = "update"
            diff = {
                k: [_jsonable(op.before[k]), _jsonable(v)]
                for k, v in op.values.items()
                if k != "pricing"
            }
            if "pricing" in op.values:
                diff["pricing"] = ["…", "updated"]
        else:
            action, diff = "unchanged", {}
        changes.append(
            ChangeOut(
                entity=op.entity.value,
                action=action,  # type: ignore[arg-type]
                key=op.key_label,
                sheet=op.record.sheet,
                row=op.record.row,
                id=str(op.obj.id if op.obj is not None else op.values["id"]),
                changes=diff,
            )
        )
    changes.extend(payment_changes)
    for ch in changes:
        counts = summary.setdefault(ch.entity, Counts())
        setattr(counts, ch.action, getattr(counts, ch.action) + 1)
    plan = Plan(ops=planner.ops, issues=issues, summary=summary, changes=changes)

    if dry_run or any(i.level == "error" for i in issues):
        return ImportResult(plan, applied=False)

    # Creates are flushed in dependency order (accounts before stakeholders before trips…).
    for op in planner.ops:
        if op.obj is None:
            session.add(op.model(tenant_id=tenant_id, **op.values))
            await session.flush()
        else:
            for k, v in op.values.items():
                setattr(op.obj, k, v)
    for trip, pricing in planner.pricing_only_updates():
        trip.pricing = pricing
    counts = {k: v.model_dump() for k, v in summary.items()}
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_type=actor[0],
            actor_id=actor[1],
            action="import.apply",
            subject_type="import",
            subject_id=None,
            after={"filename": filename, "summary": counts},
            request_id=request_id,
        )
    )
    await session.flush()
    return ImportResult(plan, applied=True)

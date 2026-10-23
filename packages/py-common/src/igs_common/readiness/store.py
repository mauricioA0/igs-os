"""Database side of readiness: load a trip's roster and document statuses, record a status change.

Runs inside the caller's tenant-scoped session (`session_scope`), so RLS applies.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.db.models import Traveler, TravelerDocument, Trip
from igs_common.readiness.checker import (
    DOC_STATUSES,
    DocumentInfo,
    ReadinessChecker,
    TravelerInfo,
    TripInfo,
)
from igs_common.readiness.rules import load_rules

# Deadlines are ops days in Buenos Aires, where the team works.
OPS_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def ops_today() -> date:
    return datetime.now(OPS_TZ).date()


async def trip_readiness(
    session: AsyncSession,
    trip_id: uuid.UUID,
    *,
    today: date | None = None,
    checker: ReadinessChecker | None = None,
) -> dict[str, Any] | None:
    trip = await session.get(Trip, trip_id)
    if trip is None:
        return None
    travelers = (
        await session.scalars(
            select(Traveler).where(Traveler.trip_id == trip_id).order_by(Traveler.full_name)
        )
    ).all()
    docs: dict[str, list[DocumentInfo]] = {}
    if travelers:
        rows = (
            await session.scalars(
                select(TravelerDocument).where(
                    TravelerDocument.traveler_id.in_([t.id for t in travelers])
                )
            )
        ).all()
        for d in rows:
            docs.setdefault(str(d.traveler_id), []).append(
                DocumentInfo(
                    requirement=d.requirement,
                    status=d.status,  # type: ignore[arg-type]
                    valid_from=d.valid_from,
                    valid_until=d.valid_until,
                    note=d.note,
                )
            )
    report = (checker or ReadinessChecker()).check(
        TripInfo(
            id=str(trip.id),
            code=trip.code,
            title=trip.title,
            country=trip.country,
            start_date=trip.start_date,
            end_date=trip.end_date,
        ),
        [
            TravelerInfo(
                id=str(t.id),
                full_name=t.full_name,
                role=t.role.value if hasattr(t.role, "value") else str(t.role),
                is_minor=t.is_minor,
                birth_year=t.birth_year,
            )
            for t in travelers
        ],
        docs,
        today=today or ops_today(),
    )
    if trip.travelers and len(travelers) < trip.travelers:
        report["warnings"].append(
            f"Roster has {len(travelers)} of {trip.travelers} travelers; "
            "the missing ones are not checked."
        )
    return report


class InvalidDocumentUpdate(ValueError):
    pass


async def set_document_status(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    traveler_id: uuid.UUID,
    requirement: str,
    *,
    status: str,
    valid_from: date | None = None,
    valid_until: date | None = None,
    note: str | None = None,
    updated_by: uuid.UUID | None = None,
) -> dict[str, Any] | None:
    """Upsert one requirement's status. Returns the stored row, or None if the traveler is unknown
    (or belongs to another tenant: RLS hides it)."""
    if status not in DOC_STATUSES:
        raise InvalidDocumentUpdate(f"status must be one of {', '.join(DOC_STATUSES)}")
    if requirement not in load_rules().requirements:
        raise InvalidDocumentUpdate(
            f"unknown requirement {requirement!r}; known: {', '.join(load_rules().requirements)}"
        )
    if valid_from and valid_until and valid_until < valid_from:
        raise InvalidDocumentUpdate("valid_until is before valid_from")
    if await session.get(Traveler, traveler_id) is None:
        return None
    values: dict[str, Any] = {
        "id": uuid.uuid4(),
        "tenant_id": tenant_id,
        "traveler_id": traveler_id,
        "requirement": requirement,
        "status": status,
        "note": note,
        "updated_by": updated_by,
    }
    # Dates are only overwritten when given: marking a passport "verified" keeps its expiry.
    if valid_from is not None:
        values["valid_from"] = valid_from
    if valid_until is not None:
        values["valid_until"] = valid_until
    stmt = pg_insert(TravelerDocument).values(values)
    update = {k: stmt.excluded[k] for k in values if k not in ("id", "tenant_id", "traveler_id")}
    stmt = stmt.on_conflict_do_update(
        constraint="uq_traveler_documents_traveler_id_requirement",
        set_=update | {"updated_at": func.now()},
    ).returning(TravelerDocument)
    row = (await session.scalars(stmt, execution_options={"populate_existing": True})).one()
    return {
        "traveler_id": str(row.traveler_id),
        "requirement": row.requirement,
        "status": row.status,
        "valid_from": row.valid_from.isoformat() if row.valid_from else None,
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "note": row.note,
    }

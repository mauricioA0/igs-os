from datetime import UTC, date, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.db.enums import ItemStatus as DbItemStatus
from igs_common.db.models import Opponent
from igs_common.db.models import TripItem as TripItemRow
from igs_common.domain.enums import ItemStatus
from igs_common.domain.transitions import can_transition
from igs_common.readiness.store import trip_readiness
from igs_core.deps import AppSettings, CurrentPrincipal, Repos
from igs_core.errors import ProblemError
from igs_core.events import audit, emit
from igs_core.runtime import RequestId, Sessions, Writer
from igs_core.schemas.common import Page, decode_cursor, encode_cursor, parse_cursor_value
from igs_core.schemas.trips import TripDetail, TripItem, TripItemPatch, TripStatus, TripSummary

router = APIRouter(prefix="/trips", tags=["trips"])


@router.get("", response_model=Page[TripSummary], summary="List trips")
async def list_trips(
    principal: CurrentPrincipal,
    repos: Repos,
    settings: AppSettings,
    status: TripStatus | None = None,
    from_: Annotated[date | None, Query(alias="from", description="Start date on/after")] = None,
    cursor: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
) -> Page[TripSummary]:
    size = min(limit or settings.page_size_default, settings.page_size_max)
    after = None
    if cursor:
        start, trip_id = decode_cursor(cursor, 2)
        after = (parse_cursor_value(date.fromisoformat, start), parse_cursor_value(UUID, trip_id))
    rows = await repos.trips.list(
        principal.tenant_id, status=status, from_date=from_, after=after, limit=size + 1
    )
    page, more = rows[:size], len(rows) > size
    next_cursor = encode_cursor(page[-1].start_date, page[-1].id) if more else None
    return Page[TripSummary](items=page, next_cursor=next_cursor)


@router.get("/{trip_id}", response_model=TripDetail, summary="Trip with its day-by-day items")
async def get_trip(trip_id: UUID, principal: CurrentPrincipal, repos: Repos) -> TripDetail:
    trip = await repos.trips.get(principal.tenant_id, trip_id)
    if trip is None:
        raise ProblemError(404, "not-found", "Trip not found.")
    return trip


@router.get(
    "/{trip_id}/readiness",
    response_model=dict[str, Any],
    summary="Pre-departure readiness: missing, overdue and invalid entry documents per traveler",
)
async def get_readiness(
    trip_id: UUID, principal: CurrentPrincipal, sessions: Sessions
) -> dict[str, Any]:
    async with sessions(principal.tenant_id) as session:
        report = await trip_readiness(session, trip_id)
    if report is None:
        raise ProblemError(404, "not-found", "Trip not found.")
    return report


@router.patch(
    "/{trip_id}/items/{item_id}",
    response_model=TripItem,
    summary="Update a trip item (status follows the domain transitions)",
)
async def update_item(
    trip_id: UUID,
    item_id: UUID,
    body: TripItemPatch,
    principal: Writer,
    sessions: Sessions,
    repos: Repos,
    rid: RequestId,
) -> TripItem:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise ProblemError(422, "empty-patch", "Nothing to update.")
    now = datetime.now(UTC)
    async with sessions(principal.tenant_id) as session:
        row = await session.scalar(
            select(TripItemRow)
            .where(
                TripItemRow.tenant_id == principal.tenant_id,
                TripItemRow.trip_id == trip_id,
                TripItemRow.id == item_id,
            )
            .with_for_update()
        )
        if row is None:
            raise ProblemError(404, "not-found", "Trip item not found.")
        before = {"status": row.status.value, "notes": row.notes}
        previous = ItemStatus(row.status.value)
        target = ItemStatus(body.status) if body.status is not None else None
        if target is not None and target != previous:
            if not can_transition("trip_item", previous, target):
                raise ProblemError(
                    409,
                    "invalid-transition",
                    f"An item can't go from {previous.value} to {target.value}.",
                )
            row.status = DbItemStatus(target.value)
            if target is ItemStatus.REQUESTED:
                row.requested_at = body.requested_at or now
            elif target is ItemStatus.CONFIRMED:
                row.confirmed_at = now
            elif target is ItemStatus.COMPLETED:
                row.completed_at = now
        elif body.requested_at is not None:
            row.requested_at = body.requested_at
        if "notes" in changes:
            row.notes = body.notes
        after = {"status": row.status.value, "notes": row.notes}
        await audit(
            session,
            principal,
            action="trip_item.update",
            subject_type="trip_item",
            subject_id=item_id,
            before=before,
            after=after,
            request_id=rid,
        )
        if target is not None and target != previous:
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="trip_item.status_changed",
                subject_type="trip_item",
                subject_id=item_id,
                # Flows read it as `trigger.item.*` (see post-match-report.json).
                payload={
                    "previousStatus": previous.value,
                    "item": {
                        "id": str(item_id),
                        "tripId": str(trip_id),
                        "kind": row.kind.value,
                        "title": row.title,
                        "day": row.day,
                        "status": target.value,
                        "previousStatus": previous.value,
                        "result": row.result,
                        "opponentId": str(row.opponent_id) if row.opponent_id else None,
                        "opponentName": await _opponent_name(session, row.opponent_id),
                    },
                },
            )
    trip = await repos.trips.get(principal.tenant_id, trip_id)
    item = next((i for i in trip.items if i.id == item_id), None) if trip else None
    if item is None:  # pragma: no cover - deleted between commit and read
        raise ProblemError(404, "not-found", "Trip item not found.")
    return item


async def _opponent_name(session: AsyncSession, opponent_id: UUID | None) -> str | None:
    if opponent_id is None:
        return None
    return await session.scalar(select(Opponent.name).where(Opponent.id == opponent_id))

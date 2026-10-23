"""Domain events: inspect the outbox and emit an event by hand.

Domain writes emit their own events in the same transaction (see ``igs_core.events``). The
POST exists for ops and for the demo ("mark the trip confirmed" → the pre-departure flow
starts); it goes through the same outbox and dispatcher as everything else.
"""

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from igs_common.db.models import OutboxEvent
from igs_core.events import audit, emit
from igs_core.runtime import RequestId, Sessions, Writer
from igs_core.schemas.workflows import EventIn, EventOut

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventOut], summary="Recent domain events (outbox)")
async def list_events(
    principal: Writer,
    sessions: Sessions,
    type: str | None = None,
    pending: bool = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[EventOut]:
    query = select(OutboxEvent).order_by(OutboxEvent.occurred_at.desc(), OutboxEvent.id.desc())
    if type:
        query = query.where(OutboxEvent.type == type)
    if pending:
        query = query.where(OutboxEvent.dispatched_at.is_(None))
    async with sessions(principal.tenant_id) as session:
        rows = (await session.scalars(query.limit(limit))).all()
        return [EventOut.model_validate(r) for r in rows]


@router.post("", response_model=EventOut, status_code=202, summary="Emit a domain event")
async def post_event(
    body: EventIn, principal: Writer, sessions: Sessions, rid: RequestId
) -> EventOut:
    async with sessions(principal.tenant_id) as session:
        event = await emit(
            session,
            tenant_id=principal.tenant_id,
            type=body.type,
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            payload=body.payload,
        )
        await audit(
            session,
            principal,
            action="event.emitted",
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            after={"type": body.type, "event_id": str(event.id)},
            request_id=rid,
        )
        await session.flush()
        await session.refresh(event)
        return EventOut.model_validate(event)

"""Write domain events and audit entries in the same transaction as the change."""

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.db.enums import ActorType
from igs_common.db.models import AuditLog, OutboxEvent
from igs_core.repositories import Principal

# Postgres NOTIFY channels. Notifications are delivered on commit, so a listener never sees an
# event whose transaction rolled back.
CHANNEL_OUTBOX = "igs_outbox"
CHANNEL_NODE_RUNS = "igs_node_runs"


async def emit(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    type: str,
    subject_type: str,
    subject_id: UUID,
    payload: dict[str, Any] | None = None,
) -> OutboxEvent:
    """Record ``type`` (e.g. ``trip.status_changed``) for the dispatcher to fan out to flows."""
    event = OutboxEvent(
        tenant_id=tenant_id,
        type=type,
        subject_type=subject_type,
        subject_id=subject_id,
        payload=payload or {},
    )
    session.add(event)
    await session.flush()
    await session.execute(
        text("select pg_notify(:channel, :id)"), {"channel": CHANNEL_OUTBOX, "id": str(event.id)}
    )
    return event


def actor_of(principal: Principal) -> tuple[ActorType, str]:
    kind = {
        "user": ActorType.USER,
        "api_key": ActorType.API_KEY,
        "demo": ActorType.USER,
    }[principal.kind]
    return kind, principal.subject


async def audit(
    session: AsyncSession,
    principal: Principal,
    *,
    action: str,
    subject_type: str,
    subject_id: UUID | None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> None:
    actor_type, actor_id = actor_of(principal)
    session.add(
        AuditLog(
            tenant_id=principal.tenant_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            subject_type=subject_type,
            subject_id=subject_id,
            before=before,
            after=after,
            request_id=request_id,
        )
    )

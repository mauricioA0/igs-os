from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.db.enums import LeadStatus as DbLeadStatus
from igs_common.db.models import Lead
from igs_common.domain.enums import LeadStatus
from igs_common.domain.transitions import can_transition
from igs_core.deps import AppSettings, CurrentPrincipal
from igs_core.errors import ProblemError
from igs_core.events import audit, emit
from igs_core.runtime import RequestId, Sessions, Writer
from igs_core.schemas.common import Page, decode_cursor, encode_cursor, parse_cursor_value
from igs_core.schemas.leads import LeadContact, LeadDetail, LeadPatch, LeadSummary
from igs_core.schemas.leads import LeadStatus as LeadStatusName

router = APIRouter(prefix="/leads", tags=["leads"])

_LEAD_SELECT = """
    select l.id, l.status::text as status, l.source::text as source, l.account_id,
           a.name as account_name, l.sport::text as sport, l.gender::text as gender,
           l.age_group, l.level_score, l.group_size, l.destination_country, l.travel_start,
           l.duration_days, l.budget_per_person_usd, l.lost_reason, l.goals, l.conversation_id,
           l.created_at, l.updated_at,
           c.id as contact_id, c.name as contact_name, c.email as contact_email,
           c.organization as contact_organization, c.role as contact_role,
           t.id as trip_id, t.code as trip_code
    from leads l
    left join accounts a on a.id = l.account_id and a.tenant_id = l.tenant_id
    left join contacts c on c.id = l.contact_id and c.tenant_id = l.tenant_id
    left join lateral (
        select id, code from trips
        where trips.tenant_id = l.tenant_id and trips.lead_id = l.id
        order by created_at desc limit 1
    ) t on true
"""


def _lead(row: Any, model: type[LeadSummary] = LeadSummary) -> LeadSummary:
    r = dict(row)
    contact_id = r.pop("contact_id")
    contact = {
        "id": contact_id,
        "name": r.pop("contact_name"),
        "email": r.pop("contact_email"),
        "organization": r.pop("contact_organization"),
        "role": r.pop("contact_role"),
    }
    if model is LeadSummary:
        r.pop("goals", None)
        r.pop("conversation_id", None)
    return model(**r, contact=LeadContact(**contact) if contact_id else None)


async def _get(session: AsyncSession, tenant_id: UUID, lead_id: UUID) -> LeadDetail | None:
    row = (
        (
            await session.execute(
                text(_LEAD_SELECT + " where l.tenant_id = :tenant_id and l.id = :lead_id"),
                {"tenant_id": tenant_id, "lead_id": lead_id},
            )
        )
        .mappings()
        .first()
    )
    return _lead(row, LeadDetail) if row else None  # type: ignore[return-value]


@router.get("", response_model=Page[LeadSummary], summary="List leads (newest first)")
async def list_leads(
    principal: CurrentPrincipal,
    sessions: Sessions,
    settings: AppSettings,
    status: LeadStatusName | None = None,
    cursor: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
) -> Page[LeadSummary]:
    size = min(limit or settings.page_size_default, settings.page_size_max)
    after_at, after_id = None, None
    if cursor:
        created, lead_id = decode_cursor(cursor, 2)
        after_at = parse_cursor_value(datetime.fromisoformat, created)
        after_id = parse_cursor_value(UUID, lead_id)
    sql = text(
        _LEAD_SELECT
        + """
        where l.tenant_id = :tenant_id
          and (cast(:status as text) is null or l.status::text = :status)
          and (cast(:after_at as timestamptz) is null
               or (l.created_at, l.id) < (cast(:after_at as timestamptz), cast(:after_id as uuid)))
        order by l.created_at desc, l.id desc
        limit :limit
        """
    )
    params = {
        "tenant_id": principal.tenant_id,
        "status": status,
        "after_at": after_at,
        "after_id": after_id,
        "limit": size + 1,
    }
    async with sessions(principal.tenant_id) as session:
        rows = (await session.execute(sql, params)).mappings().all()
    items = [_lead(r) for r in rows]
    page, more = items[:size], len(items) > size
    next_cursor = encode_cursor(page[-1].created_at.isoformat(), page[-1].id) if more else None
    return Page[LeadSummary](items=page, next_cursor=next_cursor)


@router.get("/{lead_id}", response_model=LeadDetail, summary="Lead with contact and latest trip")
async def get_lead(lead_id: UUID, principal: CurrentPrincipal, sessions: Sessions) -> LeadDetail:
    async with sessions(principal.tenant_id) as session:
        lead = await _get(session, principal.tenant_id, lead_id)
    if lead is None:
        raise ProblemError(404, "not-found", "Lead not found.")
    return lead


@router.patch(
    "/{lead_id}",
    response_model=LeadDetail,
    summary="Update a lead (status follows the domain transitions)",
)
async def update_lead(
    lead_id: UUID, body: LeadPatch, principal: Writer, sessions: Sessions, rid: RequestId
) -> LeadDetail:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        raise ProblemError(422, "empty-patch", "Nothing to update.")
    async with sessions(principal.tenant_id) as session:
        row = await session.scalar(
            select(Lead)
            .where(Lead.tenant_id == principal.tenant_id, Lead.id == lead_id)
            .with_for_update()
        )
        if row is None:
            raise ProblemError(404, "not-found", "Lead not found.")
        before = {"status": row.status.value, "lost_reason": row.lost_reason}
        previous = LeadStatus(row.status.value)
        target = LeadStatus(body.status) if body.status is not None else None
        changed = target is not None and target != previous
        if changed:
            assert target is not None
            if not can_transition("lead", previous, target):
                raise ProblemError(
                    409,
                    "invalid-transition",
                    f"A lead can't go from {previous.value} to {target.value}.",
                )
            if target is LeadStatus.LOST and not (body.lost_reason or "").strip():
                raise ProblemError(422, "lost-reason-required", "Say why the lead was lost.")
            row.status = DbLeadStatus(target.value)
            row.lost_reason = (
                (body.lost_reason or "").strip() if target is LeadStatus.LOST else None
            )
        elif "lost_reason" in changes and previous is LeadStatus.LOST:
            row.lost_reason = body.lost_reason
        if "goals" in changes:
            row.goals = body.goals
        await audit(
            session,
            principal,
            action="lead.update",
            subject_type="lead",
            subject_id=lead_id,
            before=before,
            after={"status": row.status.value, "lost_reason": row.lost_reason},
            request_id=rid,
        )
        if changed:
            assert target is not None
            await emit(
                session,
                tenant_id=principal.tenant_id,
                type="lead.status_changed",
                subject_type="lead",
                subject_id=lead_id,
                payload={
                    "previousStatus": previous.value,
                    "lead": {"id": str(lead_id), "status": target.value},
                },
            )
        await session.flush()
        lead = await _get(session, principal.tenant_id, lead_id)
    assert lead is not None
    return lead

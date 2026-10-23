"""Approvals inbox: list, read and decide.

A decision is bound to the exact action the approver saw: the request carries the
``payload_hash`` from the screen and a mismatch is a 409. Edit-and-approve never mutates the
pending approval; it creates a new, approved one and marks the old one ``superseded``. When the
approval belongs to a flow execution, the decision is signalled to the waiting workflow after
the transaction commits (the database is the source of truth; the signal is idempotent on the
workflow side: first decision wins).
"""

import hmac
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Query
from sqlalchemy import and_, func, or_, select, tuple_

from igs_common.db.enums import ApprovalStatus
from igs_common.db.models import Approval, FlowExecution
from igs_common.domain.approvals import payload_hash
from igs_core.deps import AppSettings, CurrentPrincipal
from igs_core.errors import ProblemError
from igs_core.events import audit, emit
from igs_core.intake import mark_responded
from igs_core.runtime import RequestId, Sessions, Workflows, Writer
from igs_core.schemas.common import Page, decode_cursor, encode_cursor, parse_cursor_value
from igs_core.schemas.workflows import (
    ApprovalCounts,
    ApprovalDecisionIn,
    ApprovalDecisionOut,
    ApprovalDetail,
    ApprovalSummary,
)
from igs_core.schemas.workflows import (
    ApprovalStatus as ApprovalStatusName,
)

# Scope an API key needs to decide approvals (never granted to MCP/agent keys by default).
SCOPE_APPROVE = "igs:approve"

router = APIRouter(prefix="/approvals", tags=["approvals"])
log = structlog.get_logger("igs_core.approvals")


def effective_status(a: Approval, now: datetime) -> str:
    """A pending approval past ``expires_at`` can no longer be decided: report it as expired.

    The stored row keeps ``pending`` until the waiting flow (or nobody) records the outcome, so
    every reader computes the same effective status from the same clock.
    """
    if a.status == ApprovalStatus.PENDING and a.expires_at is not None and a.expires_at <= now:
        return ApprovalStatus.EXPIRED.value
    return a.status.value


def _summary(a: Approval, now: datetime) -> ApprovalSummary:
    out = ApprovalSummary.model_validate(a)
    return out.model_copy(update={"status": effective_status(a, now)})


def _detail(a: Approval, now: datetime) -> ApprovalDetail:
    out = ApprovalDetail.model_validate(a)
    return out.model_copy(update={"status": effective_status(a, now)})


def _effectively(status: str, now: datetime):  # noqa: ANN202 - SQLAlchemy clause
    """SQL filter matching ``effective_status(row) == status``."""
    overdue = and_(Approval.expires_at.is_not(None), Approval.expires_at <= now)
    if status == ApprovalStatus.PENDING.value:
        return and_(Approval.status == ApprovalStatus.PENDING, ~overdue)
    if status == ApprovalStatus.EXPIRED.value:
        return or_(
            Approval.status == ApprovalStatus.EXPIRED,
            and_(Approval.status == ApprovalStatus.PENDING, overdue),
        )
    return Approval.status == status


@router.get("", response_model=Page[ApprovalSummary], summary="List approvals (newest first)")
async def list_approvals(
    principal: CurrentPrincipal,
    sessions: Sessions,
    settings: AppSettings,
    status: ApprovalStatusName | None = None,
    execution_id: UUID | None = None,
    cursor: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
) -> Page[ApprovalSummary]:
    now = datetime.now(UTC)
    size = min(limit or settings.page_size_default, settings.page_size_max)
    query = select(Approval).order_by(Approval.created_at.desc(), Approval.id.desc())
    if status:
        query = query.where(_effectively(status, now))
    if execution_id:
        query = query.where(Approval.execution_id == execution_id)
    if cursor:
        at, aid = decode_cursor(cursor, 2)
        query = query.where(
            tuple_(Approval.created_at, Approval.id)
            < (parse_cursor_value(datetime.fromisoformat, at), parse_cursor_value(UUID, aid))
        )
    async with sessions(principal.tenant_id) as session:
        rows = (await session.scalars(query.limit(size + 1))).all()
        items = [_summary(r, now) for r in rows[:size]]
    more = len(rows) > size
    next_cursor = encode_cursor(items[-1].created_at.isoformat(), items[-1].id) if more else None
    return Page[ApprovalSummary](items=items, next_cursor=next_cursor)


@router.get(
    "/counts",
    response_model=ApprovalCounts,
    summary="Approvals per effective status (one source for badges, KPIs and the inbox)",
)
async def count_approvals(principal: CurrentPrincipal, sessions: Sessions) -> ApprovalCounts:
    now = datetime.now(UTC)
    counts: dict[str, int] = {}
    async with sessions(principal.tenant_id) as session:
        for status in ("pending", "expired", "approved", "rejected", "superseded"):
            counts[status] = int(
                await session.scalar(
                    select(func.count()).select_from(Approval).where(_effectively(status, now))
                )
                or 0
            )
    return ApprovalCounts(**counts)


@router.get("/{approval_id}", response_model=ApprovalDetail, summary="Get an approval")
async def get_approval(
    approval_id: UUID, principal: CurrentPrincipal, sessions: Sessions
) -> ApprovalDetail:
    async with sessions(principal.tenant_id) as session:
        row = await session.get(Approval, approval_id)
        if row is None:
            raise ProblemError(404, "not-found", "Approval not found.")
        return _detail(row, datetime.now(UTC))


@router.post(
    "/{approval_id}/decision",
    response_model=ApprovalDecisionOut,
    summary="Approve or reject (optionally edit-and-approve)",
)
async def decide(
    approval_id: UUID,
    body: ApprovalDecisionIn,
    principal: Writer,
    sessions: Sessions,
    workflows: Workflows,
    rid: RequestId,
) -> ApprovalDecisionOut:
    now = datetime.now(UTC)
    decided_by = _user_id(principal.kind, principal.subject)
    superseded: UUID | None = None
    workflow_id: str | None = None

    async with sessions(principal.tenant_id) as session:
        row = await session.scalar(
            select(Approval).where(Approval.id == approval_id).with_for_update()
        )
        if row is None:
            raise ProblemError(404, "not-found", "Approval not found.")
        if row.status != ApprovalStatus.PENDING:
            raise ProblemError(409, "already-decided", f"This approval is {row.status}.")
        if body.decision == "rejected" and not (body.comment or "").strip():
            # The audit trail needs the why; the UI already requires it.
            raise ProblemError(422, "reason-required", "A rejection needs a reason.")
        if row.expires_at is not None and row.expires_at <= now:
            raise ProblemError(409, "expired", "This approval has expired.")
        if not hmac.compare_digest(body.payload_hash, row.payload_hash):
            raise ProblemError(
                409, "approval-changed", "The proposed action changed. Review it again."
            )
        if principal.role != "owner" and row.assignee_role not in (principal.role, None):
            raise ProblemError(403, "forbidden", f"Assigned to the {row.assignee_role} role.")
        if principal.kind == "api_key" and SCOPE_APPROVE not in principal.scopes:
            # Approvals exist so a person decides. A key handed to an agent (Claude Code over
            # MCP, a script) must not approve through REST unless explicitly granted.
            raise ProblemError(
                403, "human-approval-required", f"API keys need the {SCOPE_APPROVE} scope."
            )

        before = {"status": row.status.value}
        decided = row
        if body.edited_action is not None:
            if body.decision != "approved":
                raise ProblemError(422, "invalid-edit", "Only an approval can carry an edit.")
            action = body.edited_action
            decided = Approval(
                tenant_id=row.tenant_id,
                execution_id=row.execution_id,
                node_id=row.node_id,
                title=row.title,
                details={**row.details, "edited_from": str(row.id)},
                proposed_action=action.model_dump(),
                payload_hash=payload_hash(action.action, action.params),
                risk_class=row.risk_class,
                assignee_role=row.assignee_role,
                assignee_user_id=row.assignee_user_id,
                status=ApprovalStatus.APPROVED,
                decided_by=decided_by,
                decided_at=now,
                comment=body.comment,
                expires_at=row.expires_at,
            )
            session.add(decided)
            await session.flush()
            row.status = ApprovalStatus.SUPERSEDED
            row.superseded_by = decided.id
            superseded = row.id
        else:
            row.status = ApprovalStatus(body.decision)
            row.decided_by = decided_by
            row.decided_at = now
            row.comment = body.comment

        if decided.status == ApprovalStatus.APPROVED:
            # An approved first reply to an inquiry stops its 1-business-day clock.
            await mark_responded(session, decided, now)
        if decided.execution_id is not None:
            workflow_id = await session.scalar(
                select(FlowExecution.temporal_workflow_id).where(
                    FlowExecution.id == decided.execution_id
                )
            )
        await audit(
            session,
            principal,
            action=f"approval.{body.decision}" + (".edited" if superseded else ""),
            subject_type="approval",
            subject_id=decided.id,
            before=before,
            after={"status": decided.status.value, "payload_hash": decided.payload_hash},
            request_id=rid,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="approval.decided",
            subject_type="approval",
            subject_id=decided.id,
            payload={
                "approval": {
                    "id": str(decided.id),
                    "status": decided.status.value,
                    "risk_class": decided.risk_class.value,
                    "node_id": decided.node_id,
                    "execution_id": str(decided.execution_id) if decided.execution_id else None,
                },
                "supersedes": str(superseded) if superseded else None,
            },
        )
        await session.flush()
        await session.refresh(decided)
        out = _detail(decided, now)

    delivered: bool | None = None
    if workflow_id and out.node_id:
        delivered = True
        form = {"edited_action": out.proposed_action.model_dump()} if superseded else {}
        try:
            await workflows.signal_approval(
                workflow_id,
                node_id=out.node_id,
                decision=body.decision,
                by=principal.subject,
                comment=body.comment or "",
                form=form,
            )
        except Exception:  # noqa: BLE001 - recorded in the DB; ops can resend from the panel
            delivered = False
            log.warning("approval_signal_failed", workflow_id=workflow_id, exc_info=True)
    return ApprovalDecisionOut(approval=out, superseded=superseded, signal_delivered=delivered)


def _user_id(kind: str, subject: str) -> UUID | None:
    if kind != "user":
        return None
    try:
        return UUID(subject.removeprefix("user:"))
    except ValueError:
        return None

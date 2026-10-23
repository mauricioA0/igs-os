"""The one tool catalog shared by the ops copilot and the MCP server.

Each tool declares its class (read / write-internal / write-external); `policy.execute_tool`
decides per caller whether it runs, needs an approval, or is denied. Write-external tools never
execute here: they only describe the action, which becomes an approval bound to its payload hash.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from igs_common.domain.tools import ToolClass
from igs_core.agent.backend import Actor, OpsBackend


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ToolContext:
    tenant_id: UUID
    actor: Actor
    backend: OpsBackend


@dataclass(frozen=True)
class ProposedAction:
    """What a write-external call would do, shown verbatim on the approval card."""

    title: str
    params: dict[str, Any]
    subject_type: str | None = None
    subject_id: UUID | None = None
    reason: str | None = None


Handler = Callable[[ToolContext, Any], Awaitable[Any]]
Proposer = Callable[[ToolContext, Any], Awaitable[ProposedAction]]


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    tool_class: ToolClass
    input_model: type[ToolInput]
    handler: Handler | None = None  # runs when the policy allows it
    propose: Proposer | None = None  # write-external: builds the approval instead
    idempotent: bool = False
    destructive: bool = False
    open_world: bool = False  # reaches people or systems outside IGS OS


# ── Inputs ─────────────────────────────────────────────────────────────────


class SearchKnowledgeIn(ToolInput):
    query: str = Field(min_length=2, max_length=500)
    k: int = Field(default=5, ge=1, le=20)


class ListTripsIn(ToolInput):
    status: (
        Literal["draft", "proposed", "confirmed", "in_progress", "completed", "cancelled"] | None
    ) = None
    departing_from: date | None = Field(default=None, description="Only trips starting on/after.")
    limit: int = Field(default=20, ge=1, le=100)


class TripIdIn(ToolInput):
    trip_id: UUID


class UnconfirmedItemsIn(ToolInput):
    trip_id: UUID | None = None
    departing_within_days: int | None = Field(default=None, ge=0, le=365)
    limit: int = Field(default=50, ge=1, le=200)


class UpdateTripItemIn(ToolInput):
    item_id: UUID
    status: Literal["requested", "confirmed"] | None = None
    notes: str | None = Field(default=None, max_length=2000)


class UpdateTravelerDocumentIn(ToolInput):
    traveler_id: UUID
    requirement: Literal[
        "passport",
        "br_evisa",
        "birth_certificate",
        "parental_consent",
        "travel_insurance",
        "emergency_contact",
        "schengen_funds",
        "etias",
    ]
    status: Literal["missing", "requested", "received", "verified", "not_applicable"]
    valid_from: date | None = Field(default=None, description="Issue date (passports).")
    valid_until: date | None = Field(default=None, description="Expiry date, if it has one.")
    note: str | None = Field(
        default=None,
        max_length=500,
        description="Why, e.g. 'both parents travel'. Never document numbers or contents.",
    )


class FindAccountsIn(ToolInput):
    query: str | None = Field(default=None, description="Client or stakeholder name.")
    health: Literal["green", "amber", "red"] | None = None
    limit: int = Field(default=20, ge=1, le=100)


class AccountIdIn(ToolInput):
    account_id: UUID


class SearchHistoryIn(ToolInput):
    account_id: UUID
    query: str | None = Field(default=None, max_length=300)
    limit: int = Field(default=10, ge=1, le=50)


class PaymentRisksIn(ToolInput):
    account_id: UUID | None = None
    trip_id: UUID | None = None
    within_days: int = Field(
        default=14, ge=0, le=365, description="Also include payments due within N days."
    )
    limit: int = Field(default=50, ge=1, le=200)


class ListApprovalsIn(ToolInput):
    limit: int = Field(default=20, ge=1, le=100)


class RequestApprovalIn(ToolInput):
    title: str = Field(min_length=3, max_length=200)
    action: str = Field(min_length=2, max_length=100, description="What would be done.")
    params: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=3, max_length=1000)
    subject_type: Literal["trip", "trip_item", "lead", "account"] | None = None
    subject_id: UUID | None = None


class NoInput(ToolInput):
    pass


class RunFlowTestIn(ToolInput):
    flow_key: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class SendProposalIn(ToolInput):
    trip_id: UUID
    message: str | None = Field(default=None, max_length=2000)


class CancelTripItemIn(ToolInput):
    item_id: UUID
    reason: str = Field(min_length=3, max_length=1000)


class SetTripStatusIn(ToolInput):
    trip_id: UUID
    status: Literal["confirmed", "cancelled"]
    reason: str = Field(min_length=3, max_length=1000)


# ── Handlers ───────────────────────────────────────────────────────────────


async def _search_knowledge(ctx: ToolContext, a: SearchKnowledgeIn) -> Any:
    hits = await ctx.backend.search_knowledge(ctx.tenant_id, a.query, a.k)
    return {"hits": hits, "note": "Cite passages by their `citation` id." if hits else "No match."}


async def _list_trips(ctx: ToolContext, a: ListTripsIn) -> Any:
    return await ctx.backend.list_trips(
        ctx.tenant_id, status=a.status, departing_from=a.departing_from, limit=a.limit
    )


async def _get_trip(ctx: ToolContext, a: TripIdIn) -> Any:
    trip = await ctx.backend.get_trip(ctx.tenant_id, a.trip_id)
    if trip is None:
        raise LookupError(f"trip {a.trip_id} not found")
    return trip


async def _unconfirmed(ctx: ToolContext, a: UnconfirmedItemsIn) -> Any:
    return await ctx.backend.list_unconfirmed_items(
        ctx.tenant_id,
        trip_id=a.trip_id,
        departing_within_days=a.departing_within_days,
        limit=a.limit,
    )


async def _update_item(ctx: ToolContext, a: UpdateTripItemIn) -> Any:
    if a.status is None and a.notes is None:
        raise ValueError("nothing to update: pass status and/or notes")
    item = await ctx.backend.update_trip_item(
        ctx.tenant_id, a.item_id, status=a.status, notes=a.notes, actor=ctx.actor
    )
    if item is None:
        raise LookupError(f"trip item {a.item_id} not found")
    return item


async def _trip_readiness(ctx: ToolContext, a: TripIdIn) -> Any:
    report = await ctx.backend.trip_readiness(ctx.tenant_id, a.trip_id)
    if report is None:
        raise LookupError(f"trip {a.trip_id} not found")
    # The per-person detail is large; the summary + `not_ready` is what an agent acts on.
    return {k: v for k, v in report.items() if k != "people"} | {
        "people_detail": [
            {
                "traveler_id": p["traveler_id"],
                "full_name": p["full_name"],
                "items": [i for i in p["items"] if i["blocking"] or i["warnings"]],
            }
            for p in report.get("people", [])
            if not p["ready"] or any(i["warnings"] for i in p["items"])
        ]
    }


async def _update_traveler_document(ctx: ToolContext, a: UpdateTravelerDocumentIn) -> Any:
    row = await ctx.backend.update_traveler_document(
        ctx.tenant_id,
        a.traveler_id,
        a.requirement,
        status=a.status,
        valid_from=a.valid_from,
        valid_until=a.valid_until,
        note=a.note,
        actor=ctx.actor,
    )
    if row is None:
        raise LookupError(f"traveler {a.traveler_id} not found")
    return row


async def _find_accounts(ctx: ToolContext, a: FindAccountsIn) -> Any:
    return await ctx.backend.find_accounts(
        ctx.tenant_id, query=a.query, health=a.health, limit=a.limit
    )


async def _account(ctx: ToolContext, account_id: UUID) -> dict[str, Any]:
    account = await ctx.backend.get_account(ctx.tenant_id, account_id)
    if account is None:
        raise LookupError(f"account {account_id} not found")
    return account


async def _account_brief(ctx: ToolContext, a: AccountIdIn) -> Any:
    acc = await _account(ctx, a.account_id)
    # Structured brief from stored facts; the generated narrative brief (W4) can replace it.
    facts = acc.get("facts", [])
    return {
        "account": {k: acc.get(k) for k in ("id", "name", "kind", "status", "health", "city")},
        "decision_makers": [
            s for s in acc.get("stakeholders", []) if s.get("role") == "decision_maker"
        ],
        "facts": [f | {"citation": f"interaction:{f['source_interaction_id']}"} for f in facts],
        "recent_interactions": acc.get("recent_interactions", [])[:5],
    }


async def _search_history(ctx: ToolContext, a: SearchHistoryIn) -> Any:
    await _account(ctx, a.account_id)
    return await ctx.backend.search_account_history(
        ctx.tenant_id, a.account_id, query=a.query, limit=a.limit
    )


async def _stakeholders(ctx: ToolContext, a: AccountIdIn) -> Any:
    acc = await _account(ctx, a.account_id)
    return sorted(acc.get("stakeholders", []), key=lambda s: -int(s.get("influence") or 0))


async def _payment_risks(ctx: ToolContext, a: PaymentRisksIn) -> Any:
    return await ctx.backend.list_payment_risks(
        ctx.tenant_id,
        account_id=a.account_id,
        trip_id=a.trip_id,
        within_days=a.within_days,
        limit=a.limit,
    )


async def _pending_approvals(ctx: ToolContext, a: ListApprovalsIn) -> Any:
    return await ctx.backend.list_pending_approvals(ctx.tenant_id, limit=a.limit)


async def _daily_digest(ctx: ToolContext, _: NoInput) -> Any:
    return await ctx.backend.daily_digest(ctx.tenant_id)


async def _list_flows(ctx: ToolContext, _: NoInput) -> Any:
    return await ctx.backend.list_flows(ctx.tenant_id)


async def _run_flow_test(ctx: ToolContext, a: RunFlowTestIn) -> Any:
    return await ctx.backend.run_flow_test(
        ctx.tenant_id, a.flow_key, {"mode": "test"} | a.payload, ctx.actor
    )


async def _propose_request(ctx: ToolContext, a: RequestApprovalIn) -> ProposedAction:
    return ProposedAction(
        title=a.title,
        params={"action": a.action} | a.params,
        subject_type=a.subject_type,
        subject_id=a.subject_id,
        reason=a.reason,
    )


async def _propose_send_proposal(ctx: ToolContext, a: SendProposalIn) -> ProposedAction:
    trip = await ctx.backend.get_trip(ctx.tenant_id, a.trip_id)
    if trip is None:
        raise LookupError(f"trip {a.trip_id} not found")
    coach = (trip.get("team") or {}).get("coach_name") or "the coach"
    return ProposedAction(
        title=f"Send proposal for {trip.get('code') or trip['title']} to {coach}",
        params={"trip_id": str(a.trip_id), "message": a.message},
        subject_type="trip",
        subject_id=a.trip_id,
    )


async def _propose_cancel_item(ctx: ToolContext, a: CancelTripItemIn) -> ProposedAction:
    return ProposedAction(
        title=f"Cancel trip item {a.item_id}",
        params={"item_id": str(a.item_id)},
        subject_type="trip_item",
        subject_id=a.item_id,
        reason=a.reason,
    )


async def _propose_trip_status(ctx: ToolContext, a: SetTripStatusIn) -> ProposedAction:
    trip = await ctx.backend.get_trip(ctx.tenant_id, a.trip_id)
    if trip is None:
        raise LookupError(f"trip {a.trip_id} not found")
    return ProposedAction(
        title=f"Set {trip.get('code') or trip['title']} to {a.status}",
        params={"trip_id": str(a.trip_id), "status": a.status},
        subject_type="trip",
        subject_id=a.trip_id,
        reason=a.reason,
    )


R, WI, WE = ToolClass.READ, ToolClass.WRITE_INTERNAL, ToolClass.WRITE_EXTERNAL

TOOLS: tuple[ToolDef, ...] = (
    ToolDef(
        "search_knowledge",
        "Search IGS policies, provider contracts, destination guides and past trip reports. "
        "Returns cited passages; quote the `citation` id when you use one.",
        R,
        SearchKnowledgeIn,
        _search_knowledge,
    ),
    ToolDef(
        "list_trips",
        "List trips, optionally filtered by status and departure date.",
        R,
        ListTripsIn,
        _list_trips,
    ),
    ToolDef(
        "get_trip",
        "Get one trip with its day-by-day items, statuses and team.",
        R,
        TripIdIn,
        _get_trip,
    ),
    ToolDef(
        "list_unconfirmed_items",
        "Trip items still pending or requested (provider not confirmed), optionally for one trip "
        "or for trips departing within N days.",
        R,
        UnconfirmedItemsIn,
        _unconfirmed,
    ),
    ToolDef(
        "trip_readiness",
        "Pre-departure readiness of one trip: for every traveler, which entry documents "
        "(passport validity, Brazil e-Visa, parental consent for minors, insurance…) are missing, "
        "overdue or invalid, with due dates and official sources. Rules are versioned data "
        "checked against official sources; status only, never document contents.",
        R,
        TripIdIn,
        _trip_readiness,
    ),
    ToolDef(
        "find_accounts",
        "Find client accounts by client or stakeholder name and/or health (green/amber/red).",
        R,
        FindAccountsIn,
        _find_accounts,
    ),
    ToolDef(
        "get_account_brief",
        "Account 360 brief: status, health, decision makers, current facts (commitments, risks, "
        "budget) each with its source interaction, and recent interactions.",
        R,
        AccountIdIn,
        _account_brief,
    ),
    ToolDef(
        "search_account_history",
        "Search one client's interaction history (emails, calls, chats, notes). Returns excerpts "
        "with citations.",
        R,
        SearchHistoryIn,
        _search_history,
    ),
    ToolDef(
        "list_stakeholders",
        "People at a client account with role, influence (1-5), sentiment and last contact.",
        R,
        AccountIdIn,
        _stakeholders,
    ),
    ToolDef(
        "list_payment_risks",
        "Overdue and upcoming payments under IGS's terms (US$95 enrollment, US$500 installments, "
        "balance 110 days before departure), worst first: trip, client, amount, due date, days "
        "late, escalation stage and late fee. Amounts come from the payment ledger, never "
        "estimate them. Reminders are drafted daily into the approvals inbox.",
        R,
        PaymentRisksIn,
        _payment_risks,
        idempotent=True,
    ),
    ToolDef(
        "list_pending_approvals",
        "Approvals waiting for a human decision.",
        R,
        ListApprovalsIn,
        _pending_approvals,
    ),
    ToolDef(
        "daily_digest",
        "Morning ops digest: top risks with reason and next action, payments due or overdue, "
        "approvals waiting, trips departing in 14 days and leads unanswered for more than 1 "
        "business day. Deterministic facts with links; start here when asked what needs "
        "attention today.",
        R,
        NoInput,
        _daily_digest,
        idempotent=True,
    ),
    ToolDef("list_flows", "Published automation flows.", R, NoInput, _list_flows),
    ToolDef(
        "update_trip_item",
        "Mark a trip item requested or confirmed and/or set its notes. Internal change, audited.",
        WI,
        UpdateTripItemIn,
        _update_item,
        idempotent=True,
    ),
    ToolDef(
        "update_traveler_document",
        "Record the collection status of one traveler's pre-departure requirement (e.g. e-Visa "
        "verified, consent requested, not applicable because both parents travel). Internal "
        "change, audited. Status and dates only.",
        WI,
        UpdateTravelerDocumentIn,
        _update_traveler_document,
        idempotent=True,
    ),
    ToolDef(
        "run_flow_test",
        "Run a published flow in test mode (sandboxed: no messages leave IGS OS).",
        WI,
        RunFlowTestIn,
        _run_flow_test,
    ),
    ToolDef(
        "request_approval",
        "Ask a human to approve an action you cannot take yourself. Creates an approval; it does "
        "not perform the action.",
        WE,
        RequestApprovalIn,
        propose=_propose_request,
    ),
    ToolDef(
        "send_proposal",
        "Send a trip proposal to the coach. Customer-facing: always becomes an approval.",
        WE,
        SendProposalIn,
        propose=_propose_send_proposal,
        open_world=True,
    ),
    ToolDef(
        "cancel_trip_item",
        "Cancel a booked trip item. Destructive: always becomes an approval.",
        WE,
        CancelTripItemIn,
        propose=_propose_cancel_item,
        destructive=True,
        open_world=True,
    ),
    ToolDef(
        "set_trip_status",
        "Confirm or cancel a trip. Always becomes an approval.",
        WE,
        SetTripStatusIn,
        propose=_propose_trip_status,
        destructive=True,
        open_world=True,
    ),
)

TOOLS_BY_NAME = {t.name: t for t in TOOLS}

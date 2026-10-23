"""Domain actions for flow ``action`` nodes and agent tools (flow-engine.md §7.4).

One registry, two callers: an ``action`` node runs an action directly (the publish-time
validator already placed external ones behind an approval), and agent nodes expose the same
actions as tools, gated per call by ``igs_common.domain.tools.decide``.

``SqlDomainActions`` runs them against Postgres inside a tenant-scoped transaction (RLS).
External effects (proposal emails, provider requests) are never sent from here: they are
written to the outbox in the same transaction and a dispatcher delivers them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from igs_common.db.models import (
    Experience,
    Lead,
    Opponent,
    OutboxEvent,
    Provider,
    Trip,
    TripItem,
)
from igs_common.db.session import session_scope
from igs_common.domain import enums as domain_enums
from igs_common.domain.enums import Gender, ProviderKind, Sport
from igs_common.domain.planner import (
    ExperienceCandidate,
    OpponentCandidate,
    ProviderCandidate,
    TeamProfile,
    plan_itinerary,
)
from igs_common.domain.pricing import quote
from igs_common.domain.tools import ToolClass
from igs_common.domain.transitions import InvalidTransition, assert_transition
from igs_common.flows.validate import EXTERNAL_ACTIONS
from igs_common.readiness.store import trip_readiness

READ_ACTIONS = frozenset(
    {"get_trip", "list_trip_items", "find_opponents", "find_experiences", "check_trip_readiness"}
)
# Internal writes the public coach agent may trigger (security.md "propose" tools).
COACH_SAFE_ACTIONS = frozenset({"create_lead", "draft_trip"})


def action_tool_class(action: str, inputs: dict[str, Any] | None = None) -> ToolClass:
    if action in READ_ACTIONS:
        return ToolClass.READ
    if action in EXTERNAL_ACTIONS:
        return ToolClass.WRITE_EXTERNAL
    if action == "set_trip_status" and (inputs or {}).get("status") == "cancelled":
        return ToolClass.WRITE_EXTERNAL  # destructive: notifies the coach and providers
    return ToolClass.WRITE_INTERNAL


class ActionError(Exception):
    """Business-rule failure. ``cls`` maps to the flow error class (never retried)."""

    def __init__(self, cls: str, message: str) -> None:
        super().__init__(message)
        self.cls = cls


@dataclass(frozen=True)
class ActionContext:
    tenant_id: str | None
    execution_id: str
    node_id: str
    iteration: int

    @property
    def idempotency_key(self) -> str:
        return f"{self.execution_id}:{self.node_id}:{self.iteration}"


class DomainActions(Protocol):
    async def run(self, action: str, inputs: dict[str, Any], ctx: ActionContext) -> Any: ...


def _uuid(value: Any, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as e:
        raise ActionError("validation", f"{what} must be a UUID, got {value!r}") from e


def _require(inputs: dict[str, Any], *keys: str) -> None:
    missing = [k for k in keys if inputs.get(k) in (None, "")]
    if missing:
        raise ActionError("validation", f"missing inputs: {', '.join(missing)}")


def _status(enum: type, value: Any, what: str) -> Any:
    try:
        return enum(value)
    except ValueError as e:
        raise ActionError("validation", f"unknown {what} {value!r}") from e


def item_view(item: TripItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "day": item.day,
        "slot": item.slot.value,
        "kind": item.kind.value,
        "title": item.title,
        "status": item.status.value,
        "providerId": str(item.provider_id) if item.provider_id else None,
        "opponentId": str(item.opponent_id) if item.opponent_id else None,
        "notes": item.notes,
    }


def trip_view(trip: Trip, lead: Lead | None, items: list[TripItem] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": str(trip.id),
        "code": trip.code,
        "title": trip.title,
        "city": trip.city,
        "country": trip.country,
        "startDate": trip.start_date.isoformat(),
        "endDate": trip.end_date.isoformat(),
        "status": trip.status.value,
        "pricePerPersonUsd": trip.price_per_person_usd,
        "lead": None,
    }
    if lead is not None:
        out["lead"] = {
            "id": str(lead.id),
            "sport": lead.sport.value,
            "gender": lead.gender.value,
            "ageGroup": lead.age_group,
            "levelScore": lead.level_score,
            "groupSize": lead.group_size,
            "status": lead.status.value,
        }
    if items is not None:
        out["items"] = [item_view(i) for i in items]
    return out


_CITY_FOR_COUNTRY = {
    "Argentina": "Buenos Aires",
    "Brazil": "Rio de Janeiro",
    "Costa Rica": "San José",
}


@dataclass
class SqlDomainActions:
    engine: AsyncEngine | None = None

    async def run(self, action: str, inputs: dict[str, Any], ctx: ActionContext) -> Any:
        if ctx.tenant_id is None:
            raise ActionError("validation", "domain actions need a tenant")
        handler = getattr(self, f"_a_{action}", None)
        if handler is None:
            raise ActionError("validation", f"unknown action {action!r}")
        try:
            async with session_scope(ctx.tenant_id, engine=self.engine) as session:
                return await handler(session, inputs, ctx)
        except InvalidTransition as e:
            raise ActionError("validation", str(e)) from e

    # ── reads ───────────────────────────────────────────────────────────────

    async def _trip(self, session: AsyncSession, trip_id: Any) -> Trip:
        trip = await session.get(Trip, _uuid(trip_id, "tripId"))
        if trip is None:
            raise ActionError("not_found", f"trip {trip_id} not found")
        return trip

    async def _items(self, session: AsyncSession, trip_id: uuid.UUID) -> list[TripItem]:
        rows = await session.scalars(
            select(TripItem)
            .where(TripItem.trip_id == trip_id)
            .order_by(TripItem.day, TripItem.slot)
        )
        return list(rows)

    async def _a_get_trip(
        self, session: AsyncSession, inputs: dict[str, Any], ctx: ActionContext
    ) -> Any:
        _require(inputs, "tripId")
        trip = await self._trip(session, inputs["tripId"])
        lead = await session.get(Lead, trip.lead_id) if trip.lead_id else None
        return trip_view(trip, lead, await self._items(session, trip.id))

    async def _a_list_trip_items(
        self, session: AsyncSession, inputs: dict[str, Any], ctx: ActionContext
    ) -> Any:
        _require(inputs, "tripId")
        trip = await self._trip(session, inputs["tripId"])
        items = await self._items(session, trip.id)
        statuses = set(inputs.get("statuses") or [])
        if statuses:
            items = [i for i in items if i.status.value in statuses]
        if inputs.get("withProvider"):
            items = [i for i in items if i.provider_id is not None]
        return {"tripId": str(trip.id), "items": [item_view(i) for i in items]}

    async def _a_check_trip_readiness(
        self, session: AsyncSession, inputs: dict[str, Any], ctx: ActionContext
    ) -> Any:
        _require(inputs, "tripId")
        trip = await self._trip(session, inputs["tripId"])
        report = await trip_readiness(session, trip.id)
        assert report is not None  # the trip exists: _trip checked it
        not_ready = [
            {"name": p["full_name"], "missing": p["missing"], "overdue": p["overdue"]}
            for p in report["not_ready"]
        ]
        overdue = report["overdue_items"]
        summary = (
            f"{report['travelers_ready']}/{report['travelers']} travelers ready; "
            f"{report['open_items']} open items ({overdue} overdue, {report['blockers']} blockers)"
        )
        if report["warnings"]:
            summary += ". " + " ".join(report["warnings"])
        return {
            "tripId": str(trip.id),
            "ready": report["ready"],
            "travelers": report["travelers"],
            "travelersReady": report["travelers_ready"],
            "openItems": report["open_items"],
            "overdueItems": overdue,
            "blockers": report["blockers"],
            "nextDueOn": report["next_due_on"],
            "notReady": not_ready,
            "summary": summary,
            "rulesVersion": report["rules"]["version"],
        }

    async def _a_find_opponents(
        self, session: AsyncSession, inputs: dict[str, Any], ctx: ActionContext
    ) -> Any:
        _require(inputs, "sport", "gender")
        stmt = select(Opponent).where(
            Opponent.sport == inputs["sport"], Opponent.gender == inputs["gender"]
        )
        if inputs.get("country"):
            stmt = stmt.where(Opponent.country == inputs["country"])
        rows = list(await session.scalars(stmt))
        if inputs.get("ageGroup"):
            rows = [o for o in rows if inputs["ageGroup"] in o.age_groups]
        level = inputs.get("levelScore")
        if level is not None:
            rows.sort(key=lambda o: (abs(o.level_score - int(level)), o.name))
        return {
            "opponents": [
                {
                    "id": str(o.id),
                    "name": o.name,
                    "city": o.city,
                    "country": o.country,
                    "levelScore": o.level_score,
                    "ageGroups": list(o.age_groups),
                    "description": o.description,
                }
                for o in rows[: int(inputs.get("limit") or 5)]
            ]
        }

    async def _a_find_experiences(
        self, session: AsyncSession, inputs: dict[str, Any], ctx: ActionContext
    ) -> Any:
        _require(inputs, "country")
        rows = list(
            await session.scalars(select(Experience).where(Experience.country == inputs["country"]))
        )
        sport = inputs.get("sport")
        if sport:
            rows = [e for e in rows if not e.sports or sport in e.sports]
        return {
            "experiences": [
                {
                    "id": str(e.id),
                    "title": e.title,
                    "city": e.city,
                    "priceUsd": e.price_usd,
                    "durationHours": e.duration_hours,
                    "description": e.description,
                }
                for e in rows[: int(inputs.get("limit") or 8)]
            ]
        }

    # ── internal writes ─────────────────────────────────────────────────────

    async def _a_update_trip_item(
        self, session: AsyncSession, inputs: dict[str, Any], ctx: ActionContext
    ) -> Any:
        _require(inputs, "itemId")
        item = await session.get(TripItem, _uuid(inputs["itemId"], "itemId"))
        if item is None:
            raise ActionError("not_found", f"trip item {inputs['itemId']} not found")
        if "status" in inputs and inputs["status"] != item.status.value:
            target = _status(domain_enums.ItemStatus, inputs["status"], "item status")
            current = _status(domain_enums.ItemStatus, item.status.value, "item status")
            assert_transition("trip_item", current, target)
            item.status = type(item.status)(target.value)
            now = datetime.now(UTC)
            if target is domain_enums.ItemStatus.REQUESTED:
                item.requested_at = now
            elif target is domain_enums.ItemStatus.CONFIRMED:
                item.confirmed_at = now
        if "notes" in inputs:
            item.notes = inputs["notes"]
        await session.flush()
        return item_view(item)

    async def _a_swap_opponent(
        self, session: AsyncSession, inputs: dict[str, Any], ctx: ActionContext
    ) -> Any:
        _require(inputs, "itemId", "opponentId")
        item = await session.get(TripItem, _uuid(inputs["itemId"], "itemId"))
        opponent = await session.get(Opponent, _uuid(inputs["opponentId"], "opponentId"))
        if item is None or opponent is None:
            raise ActionError("not_found", "trip item or opponent not found")
        if item.kind.value != "match":
            raise ActionError("validation", "only match items have an opponent")
        item.opponent_id, item.title = opponent.id, f"vs {opponent.name}"
        item.status = type(item.status)("pending")
        await session.flush()
        return item_view(item)

    async def _a_set_trip_status(
        self, session: AsyncSession, inputs: dict[str, Any], ctx: ActionContext
    ) -> Any:
        _require(inputs, "tripId", "status")
        trip = await self._trip(session, inputs["tripId"])
        target = _status(domain_enums.TripStatus, inputs["status"], "trip status")
        assert_transition("trip", domain_enums.TripStatus(trip.status.value), target)
        trip.status = type(trip.status)(target.value)
        self._event(session, "trip.status_changed", "trip", trip.id, {"status": target.value}, ctx)
        await session.flush()
        return {"tripId": str(trip.id), "status": target.value}

    async def _a_update_lead_status(
        self, session: AsyncSession, inputs: dict[str, Any], ctx: ActionContext
    ) -> Any:
        _require(inputs, "leadId", "status")
        lead = await session.get(Lead, _uuid(inputs["leadId"], "leadId"))
        if lead is None:
            raise ActionError("not_found", f"lead {inputs['leadId']} not found")
        target = _status(domain_enums.LeadStatus, inputs["status"], "lead status")
        assert_transition("lead", domain_enums.LeadStatus(lead.status.value), target)
        lead.status = type(lead.status)(target.value)
        await session.flush()
        return {"leadId": str(lead.id), "status": target.value}

    async def _a_create_lead(
        self, session: AsyncSession, inputs: dict[str, Any], ctx: ActionContext
    ) -> Any:
        _require(inputs, "lead")
        data = inputs["lead"]
        if not isinstance(data, dict):
            raise ActionError("validation", "lead must be an object")
        # Idempotent per node run: a retried activity finds the lead it already created.
        lead_id = uuid.uuid5(uuid.NAMESPACE_URL, f"igs:lead:{ctx.idempotency_key}")
        existing = await session.get(Lead, lead_id)
        if existing is not None:
            return {"id": str(existing.id), "status": existing.status.value, "created": False}
        try:
            lead = Lead(
                id=lead_id,
                tenant_id=uuid.UUID(str(ctx.tenant_id)),
                sport=data["sport"],
                gender=data["gender"],
                age_group=str(data["ageGroup"]),
                level_score=int(data["levelScore"]),
                group_size=int(data["groupSize"]),
                destination_country=str(data["destinationCountry"]),
                travel_start=date.fromisoformat(str(data["travelStart"])[:10]),
                duration_days=int(data["durationDays"]),
                budget_per_person_usd=data.get("budgetPerPersonUsd"),
                goals=data.get("goals"),
                status="qualified",
                source="flow",
            )
        except (KeyError, ValueError, TypeError) as e:
            raise ActionError("validation", f"invalid lead: {e}") from e
        if inputs.get("conversationId"):
            lead.conversation_id = _uuid(inputs["conversationId"], "conversationId")
        session.add(lead)
        await session.flush()
        self._event(session, "lead.created", "lead", lead.id, {"source": "flow"}, ctx)
        return {"id": str(lead.id), "status": "qualified", "created": True}

    async def _a_draft_trip(
        self, session: AsyncSession, inputs: dict[str, Any], ctx: ActionContext
    ) -> Any:
        _require(inputs, "leadId")
        lead = await session.get(Lead, _uuid(inputs["leadId"], "leadId"))
        if lead is None:
            raise ActionError("not_found", f"lead {inputs['leadId']} not found")
        trip_id = uuid.uuid5(uuid.NAMESPACE_URL, f"igs:trip:{ctx.idempotency_key}")
        if (existing := await session.get(Trip, trip_id)) is not None:
            return trip_view(existing, lead, await self._items(session, existing.id))

        city = _CITY_FOR_COUNTRY.get(lead.destination_country, lead.destination_country)
        team = TeamProfile(
            sport=Sport(lead.sport.value),
            gender=Gender(lead.gender.value),
            age_group=lead.age_group,
            level_score=lead.level_score,
            city=city,
            duration_days=lead.duration_days,
        )
        opponents = [
            OpponentCandidate(
                id=o.id,
                name=o.name,
                city=o.city,
                sport=Sport(o.sport.value),
                gender=Gender(o.gender.value),
                age_groups=tuple(o.age_groups),
                level_score=o.level_score,
            )
            for o in await session.scalars(select(Opponent).where(Opponent.city == city))
        ]
        experiences = [
            ExperienceCandidate(
                id=e.id,
                title=e.title,
                city=e.city,
                sports=tuple(Sport(x) for x in e.sports),
                price_usd=e.price_usd,
            )
            for e in await session.scalars(select(Experience).where(Experience.city == city))
        ]
        providers = [
            ProviderCandidate(
                id=p.id,
                name=p.name,
                kind=ProviderKind(p.kind.value),
                city=p.city,
                unit_price_usd=p.unit_price_usd,
                unit=p.unit,
            )
            for p in await session.scalars(select(Provider).where(Provider.city == city))
        ]
        itinerary = plan_itinerary(team, opponents, experiences, providers)
        q = quote(itinerary, providers, experiences, lead.group_size)
        start = lead.travel_start
        trip = Trip(
            id=trip_id,
            tenant_id=lead.tenant_id,
            lead_id=lead.id,
            account_id=lead.account_id,
            title=f"{lead.sport.value.replace('_', ' ').title()} tour · {city}",
            city=city,
            country=lead.destination_country,
            start_date=start,
            end_date=start + timedelta(days=lead.duration_days - 1),
            status="proposed",
            price_per_person_usd=q.price_per_person_usd,
            summary="; ".join(itinerary.warnings),
            pricing=q.model_dump(mode="json"),
            travelers=lead.group_size,
        )
        session.add(trip)
        await session.flush()
        items = [
            TripItem(
                tenant_id=lead.tenant_id,
                trip_id=trip.id,
                day=pi.day,
                slot=pi.slot.value,
                kind=pi.kind.value,
                title=pi.title,
                opponent_id=pi.opponent_id,
                experience_id=pi.experience_id,
                provider_id=pi.provider_id,
            )
            for pi in itinerary.items
        ]
        session.add_all(items)
        if lead.status.value == "qualified":
            lead.status = type(lead.status)("proposal_sent")
        await session.flush()
        self._event(session, "trip.drafted", "trip", trip.id, {"leadId": str(lead.id)}, ctx)
        out = trip_view(trip, lead, items)
        out["warnings"] = list(itinerary.warnings)
        return out

    async def _a_create_ops_task(
        self, session: AsyncSession, inputs: dict[str, Any], ctx: ActionContext
    ) -> Any:
        _require(inputs, "title")
        subject = _uuid(inputs.get("tripId") or ctx_subject(ctx), "subject")
        self._event(
            session,
            "ops.task_created",
            "trip" if "tripId" in inputs else "execution",
            subject,
            dict(inputs),
            ctx,
        )
        return {"title": inputs["title"], "queued": True}

    # ── external effects (outbox only) ──────────────────────────────────────

    async def _a_request_provider_confirmations(
        self, session: AsyncSession, inputs: dict[str, Any], ctx: ActionContext
    ) -> Any:
        _require(inputs, "tripId", "replyBy")
        trip = await self._trip(session, inputs["tripId"])
        only = set(inputs.get("onlyStatuses") or ["pending"])
        now = datetime.now(UTC)
        requested = []
        for item in await self._items(session, trip.id):
            if item.provider_id is None or item.status.value not in only:
                continue
            item.status = type(item.status)("requested")
            item.requested_at = now
            requested.append(item)
        self._event(
            session,
            "provider.confirmations_requested",
            "trip",
            trip.id,
            {"items": [str(i.id) for i in requested], "replyBy": str(inputs["replyBy"])},
            ctx,
        )
        await session.flush()
        return {"tripId": str(trip.id), "requested": len(requested)}

    async def _a_send_proposal(
        self, session: AsyncSession, inputs: dict[str, Any], ctx: ActionContext
    ) -> Any:
        _require(inputs, "tripId", "to")
        trip = await self._trip(session, inputs["tripId"])
        self._event(
            session,
            "proposal.send_requested",
            "trip",
            trip.id,
            {"to": inputs["to"], "note": inputs.get("note")},
            ctx,
        )
        return {"tripId": str(trip.id), "queued": True}

    def _event(
        self,
        session: AsyncSession,
        type_: str,
        subject_type: str,
        subject_id: uuid.UUID,
        payload: dict[str, Any],
        ctx: ActionContext,
    ) -> None:
        session.add(
            OutboxEvent(
                id=uuid.uuid5(uuid.NAMESPACE_URL, f"igs:event:{type_}:{ctx.idempotency_key}"),
                tenant_id=uuid.UUID(str(ctx.tenant_id)),
                type=type_,
                subject_type=subject_type,
                subject_id=subject_id,
                payload={**payload, "idempotencyKey": ctx.idempotency_key},
            )
        )


def ctx_subject(ctx: ActionContext) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"igs:execution:{ctx.execution_id}")

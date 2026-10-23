"""Public, unauthenticated surfaces for coaches: the inquiry chat and the tour proposal.

Only the public demo tenant is reachable here (``demo_mode`` + ``demo_tenant_slug``); the
tenant never comes from the request. Every route is rate-limited per client address.

Chat
    ``POST /public/chat/conversations`` starts a conversation: a ``conversations`` row plus a
    run of the published ``inbound-inquiry`` flow (trigger ``chat``, ``conversationId`` in the
    trigger). ``POST …/messages`` stores the coach's message and signals ``user_message`` to the
    workflow. ``GET …/stream`` is Server-Sent Events over the replies the worker writes to the
    outbox (``conversation.reply``), so a reconnect resumes from the last event id.

Proposal
    ``GET /public/proposals/{ref}`` renders a trip as a coach-facing proposal: one package price
    per person (never cost lines or margin), with IGS's published payment terms. ``POST …/reserve``
    asks to enroll the team: it creates a pending approval for ops (external action) — nothing is
    charged or sent automatically.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sse_starlette.sse import EventSourceResponse

from igs_common.db.base import uuid7
from igs_common.db.enums import (
    ApprovalStatus,
    Channel,
    ExecutionStatus,
    MessageRole,
    ToolClass,
    TriggerKind,
    UserRole,
)
from igs_common.db.models import (
    Approval,
    Conversation,
    Experience,
    Flow,
    FlowExecution,
    FlowVersion,
    Message,
    Opponent,
    Trip,
    TripItem,
)
from igs_common.domain.approvals import payload_hash
from igs_core.deps import AppSettings
from igs_core.errors import ProblemError
from igs_core.events import audit, emit
from igs_core.ratelimit import RateLimiter, rate_limit  # noqa: F401 - RateLimiter re-exported
from igs_core.repositories import Principal
from igs_core.runtime import RequestId, Sessions, Workflows
from igs_core.temporal import execution_input

router = APIRouter(prefix="/public", tags=["public"])
log = structlog.get_logger("igs_core.public_chat")

INQUIRY_FLOW_KEY = "inbound-inquiry"
SIGNAL_USER_MESSAGE = "user_message"
REPLY_EVENT = "conversation.reply"
TERMINAL = {ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}
POLL_SECONDS = 1.0
MAX_MESSAGE_CHARS = 2000
# IGS Terms & Conditions (infinityglobalsports.com/terms-and-conditions, checked 2026-10-22):
# "a non-refundable $95 enrollment fee"; manual plan "first payment of $500 due 30 days after
# enrollment; second payment of $500 due 90 days after enrollment; final balance due 110 days
# before departure". There is no percentage deposit.
ENROLLMENT_FEE_USD = 95
INSTALLMENT_USD = 500
BALANCE_DUE_DAYS = 110
PROPOSAL_VALID_DAYS = 14

INCLUDED = [
    "Hotel in a safe neighborhood (twin/triple rooms), breakfast daily",
    "Private bus for the whole stay, airport transfers included",
    "Every match with certified referees, matched to your level",
    "Professional training sessions and venue fees",
    "The experiences listed in your itinerary",
    "Bilingual tour leader with the team 24/7",
    "Pre-match scouting reports on every opponent",
]
NOT_INCLUDED = [  # wording follows the "Not Included" list of IGS's terms
    "International flights (we can quote group airfare)",
    "Travel insurance, unless purchased through IGS",
    "Meals outside the standard meal plan, optional excursions and personal expenses",
    "Gratuities for tour directors and drivers; passport and visa fees",
]


# ── Demo tenant ───────────────────────────────────────────────────────────────


async def public_tenant(request: Request, settings: AppSettings) -> UUID:
    """The public demo tenant. Public surfaces don't exist outside demo mode."""
    if not settings.demo_mode:
        raise ProblemError(404, "not-found", "Not found.")
    cached: UUID | None = getattr(request.app.state, "demo_tenant_id", None)
    if cached is not None:
        return cached
    tenant_id = await request.app.state.repos.directory.tenant_id_by_slug(settings.demo_tenant_slug)
    if tenant_id is None:
        raise ProblemError(503, "demo-unavailable", "The demo tenant is not seeded.")
    request.app.state.demo_tenant_id = tenant_id
    return tenant_id


PublicTenant = Annotated[UUID, Depends(public_tenant)]


def _coach(tenant_id: UUID, subject: str) -> Principal:
    """Audit identity for anonymous coach actions (no privileges anywhere else)."""
    return Principal(kind="demo", tenant_id=tenant_id, role="viewer", subject=subject)


# ── Temporal: the user_message signal ─────────────────────────────────────────


async def signal_user_message(gateway: Any, workflow_id: str, message: dict[str, Any]) -> None:
    """Send ``user_message`` through whatever gateway the app runs with.

    The gateway protocol (``igs_core.temporal``) exposes approval and cancel signals; until it
    grows ``signal_user_message``, fall back to the recording gateway's log or the Temporal
    client the real gateway holds.
    """
    method: Callable[[str, dict[str, Any]], Awaitable[None]] | None = getattr(
        gateway, "signal_user_message", None
    )
    if method is not None:
        await method(workflow_id, message)
        return
    if getattr(gateway, "fail", False):
        raise ConnectionError("temporal unavailable")
    signals = getattr(gateway, "signals", None)
    if isinstance(signals, list):  # RecordingGateway
        signals.append((workflow_id, SIGNAL_USER_MESSAGE, message))
        return
    client = await gateway._get()  # noqa: SLF001 - TemporalGateway's lazily connected client
    await client.get_workflow_handle(workflow_id).signal(SIGNAL_USER_MESSAGE, message)


# ── Schemas ───────────────────────────────────────────────────────────────────


class ConversationStartIn(BaseModel):
    message: str | None = Field(
        default=None,
        max_length=MAX_MESSAGE_CHARS,
        description="Optional first message from the coach (e.g. from a quick start chip).",
    )
    source: str = Field(default="web", max_length=40, description="Where the widget runs.")


class ConversationOut(BaseModel):
    conversation_id: UUID
    execution_id: UUID
    status: str
    ai_disclosure: str = (
        "You're chatting with the IGS AI concierge. A person from our team reviews every "
        "proposal before it's sent, and you can ask for a person at any time."
    )


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class MessageAccepted(BaseModel):
    message_id: UUID
    delivered: bool


class ChatMessage(BaseModel):
    id: str
    role: str  # "user" | "assistant"
    text: str
    at: datetime
    options: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class Transcript(BaseModel):
    conversation_id: UUID
    status: str
    messages: list[ChatMessage]


class ProposalOpponent(BaseModel):
    name: str
    city: str
    level_score: int
    description: str


class ProposalItem(BaseModel):
    slot: str
    kind: str
    title: str
    time: str | None = None
    opponent: ProposalOpponent | None = None
    experience: str | None = None


class ProposalDay(BaseModel):
    day: int
    date: date
    items: list[ProposalItem]


class ProposalOut(BaseModel):
    id: UUID
    ref: str
    title: str
    team: str
    program: str | None
    coach_name: str | None
    sport: str | None
    gender: str | None
    level_score: int | None
    city: str
    country: str
    start_date: date
    end_date: date
    days: int
    travelers: int | None
    price_per_person_usd: int
    enrollment_fee_usd: int  # per traveler, non-refundable
    installment_usd: int  # each payment-plan installment, per traveler
    first_installment_due_days: int  # after enrollment
    second_installment_due_days: int  # after enrollment
    balance_due: date  # 110 days before departure
    valid_until: date
    status: str
    summary: str
    itinerary: list[ProposalDay]
    opponents: list[ProposalOpponent]
    experiences: list[str]
    included: list[str]
    not_included: list[str]
    enrollment_requested: bool


class ReserveIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    # Plain pattern check (no email-validator dependency); ops confirms by replying anyway.
    email: str = Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    note: str | None = Field(default=None, max_length=1000)


class ReserveOut(BaseModel):
    approval_id: UUID
    status: str
    enrollment_fees_usd: int
    message: str = (
        "Thanks! Our team will confirm availability and send the enrollment invoice (US$95 per "
        "traveler) within one business day. Nothing has been charged."
    )


# ── Chat ──────────────────────────────────────────────────────────────────────


def chat_workflow_id(execution_id: UUID) -> str:
    return f"chat-{execution_id}"


@router.post(
    "/chat/conversations",
    response_model=ConversationOut,
    status_code=201,
    summary="Start a coach conversation on the inbound-inquiry flow",
    dependencies=[Depends(rate_limit("chat-start", limit=5, window_s=60))],
)
async def start_conversation(
    body: ConversationStartIn,
    tenant_id: PublicTenant,
    sessions: Sessions,
    workflows: Workflows,
    rid: RequestId,
) -> ConversationOut:
    conversation_id, execution_id = uuid7(), uuid7()
    workflow_id = chat_workflow_id(execution_id)
    trigger = {"conversationId": str(conversation_id), "channel": "web", "source": body.source}
    first: dict[str, Any] | None = None
    async with sessions(tenant_id) as session:
        flow = await session.scalar(select(Flow).where(Flow.key == INQUIRY_FLOW_KEY))
        if flow is None or flow.published_version_id is None:
            raise ProblemError(503, "chat-unavailable", "The inquiry chat is not published yet.")
        version = await session.get(FlowVersion, flow.published_version_id)
        if version is None:
            raise ProblemError(503, "chat-unavailable", "The inquiry chat is not published yet.")
        session.add(
            FlowExecution(
                id=execution_id,
                tenant_id=tenant_id,
                flow_version_id=version.id,
                trigger_kind=TriggerKind.CHAT,
                trigger_payload=trigger,
                vars={},
                status=ExecutionStatus.RUNNING,
                temporal_workflow_id=workflow_id,
            )
        )
        await session.flush()
        session.add(
            Conversation(
                id=conversation_id,
                tenant_id=tenant_id,
                channel=Channel.WEB,
                flow_execution_id=execution_id,
            )
        )
        if body.message:
            first = await _store_user_message(session, tenant_id, conversation_id, body.message)
        await audit(
            session,
            _coach(tenant_id, f"coach:{conversation_id}"),
            action="conversation.started",
            subject_type="conversation",
            subject_id=conversation_id,
            after={"flow": flow.key, "version": version.version, "source": body.source},
            request_id=rid,
        )
        payload = execution_input(
            execution_id=str(execution_id),
            tenant_id=str(tenant_id),
            graph=version.graph,
            version=version.version,
            trigger=trigger,
        )

    try:
        result = await workflows.start_execution(workflow_id, payload)
        if first is not None:
            await signal_user_message(workflows, workflow_id, first)
    except Exception as exc:  # noqa: BLE001 - a failed start must not leave a live-looking chat
        log.warning("chat_start_failed", workflow_id=workflow_id, exc_info=True)
        async with sessions(tenant_id) as session:
            row = await session.get(FlowExecution, execution_id)
            if row is not None:
                row.status = ExecutionStatus.FAILED
                row.finished_at = datetime.now(UTC)
                row.error = {"class": "start", "message": f"{type(exc).__name__}: {exc}"}
        raise ProblemError(502, "chat-unavailable", "The concierge is unavailable.") from exc

    if result.run_id:
        async with sessions(tenant_id) as session:
            row = await session.get(FlowExecution, execution_id)
            if row is not None:
                row.temporal_run_id = result.run_id
    return ConversationOut(
        conversation_id=conversation_id, execution_id=execution_id, status="running"
    )


async def _store_user_message(
    session: Any, tenant_id: UUID, conversation_id: UUID, text_: str
) -> dict[str, Any]:
    message_id = uuid7()
    received = datetime.now(UTC)
    session.add(
        Message(
            id=message_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=[{"type": "text", "text": text_}],
        )
    )
    await session.flush()
    # Shape of igs_worker.activities.types.UserMessage.
    return {"text": text_, "message_id": str(message_id), "received_at": received.isoformat()}


async def _conversation(session: Any, conversation_id: UUID) -> tuple[Conversation, FlowExecution]:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None or conversation.flow_execution_id is None:
        raise ProblemError(404, "not-found", "Conversation not found.")
    execution = await session.get(FlowExecution, conversation.flow_execution_id)
    if execution is None:
        raise ProblemError(404, "not-found", "Conversation not found.")
    return conversation, execution


@router.post(
    "/chat/conversations/{conversation_id}/messages",
    response_model=MessageAccepted,
    status_code=202,
    summary="Send the coach's message to the running conversation",
    dependencies=[Depends(rate_limit("chat-message", limit=30, window_s=60))],
)
async def post_message(
    conversation_id: UUID,
    body: MessageIn,
    tenant_id: PublicTenant,
    sessions: Sessions,
    workflows: Workflows,
) -> MessageAccepted:
    async with sessions(tenant_id) as session:
        _, execution = await _conversation(session, conversation_id)
        if execution.status in TERMINAL:
            raise ProblemError(409, "conversation-closed", "This conversation has ended.")
        message = await _store_user_message(session, tenant_id, conversation_id, body.text)
        workflow_id = execution.temporal_workflow_id
    delivered = True
    try:
        await signal_user_message(workflows, workflow_id, message)
    except Exception:  # noqa: BLE001 - the message is stored; ops can still read it
        log.warning("chat_signal_failed", workflow_id=workflow_id, exc_info=True)
        delivered = False
    return MessageAccepted(message_id=UUID(message["message_id"]), delivered=delivered)


_REPLIES = text(
    """
    SELECT id, created_at, payload FROM outbox_events
    WHERE tenant_id = :tenant AND type = :type AND payload->>'executionId' = :execution
      AND (created_at, id) > (:after_at, :after_id)
    ORDER BY created_at, id
    LIMIT 200
    """
)
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_NIL = UUID(int=0)


async def _replies(
    session: Any, tenant_id: UUID, execution_id: UUID, after: tuple[datetime, UUID]
) -> list[ChatMessage]:
    rows = (
        await session.execute(
            _REPLIES,
            {
                "tenant": tenant_id,
                "type": REPLY_EVENT,
                "execution": str(execution_id),
                "after_at": after[0],
                "after_id": after[1],
            },
        )
    ).all()
    return [
        ChatMessage(
            id=str(row.id),
            role="assistant",
            text=str(row.payload.get("text") or ""),
            at=row.created_at,
            options=list(row.payload.get("options") or []),
            attachments=list(row.payload.get("attachments") or []),
        )
        for row in rows
    ]


@router.get(
    "/chat/conversations/{conversation_id}/messages",
    response_model=Transcript,
    summary="Transcript of a conversation (coach messages and concierge replies)",
    dependencies=[Depends(rate_limit("chat-read", limit=60, window_s=60))],
)
async def get_transcript(
    conversation_id: UUID, tenant_id: PublicTenant, sessions: Sessions
) -> Transcript:
    async with sessions(tenant_id) as session:
        _, execution = await _conversation(session, conversation_id)
        user_rows = (
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at, Message.id)
            )
        ).all()
        replies = await _replies(session, tenant_id, execution.id, (_EPOCH, _NIL))
    messages = [
        ChatMessage(id=str(m.id), role=m.role.value, text=_text_of(m.content), at=m.created_at)
        for m in user_rows
    ]
    messages.extend(replies)
    messages.sort(key=lambda m: m.at)
    return Transcript(
        conversation_id=conversation_id, status=execution.status.value, messages=messages
    )


def _text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(b.get("text", "")) for b in content if isinstance(b, dict))
    return ""


@router.get(
    "/chat/conversations/{conversation_id}/stream",
    summary="Server-Sent Events: concierge replies as the flow sends them",
    dependencies=[Depends(rate_limit("chat-stream", limit=20, window_s=60))],
)
async def stream_replies(
    conversation_id: UUID,
    request: Request,
    tenant_id: PublicTenant,
    sessions: Sessions,
) -> EventSourceResponse:
    async with sessions(tenant_id) as session:
        _, execution = await _conversation(session, conversation_id)
        execution_id = execution.id
    after = _parse_last_event_id(request.headers.get("last-event-id"))

    async def events() -> AsyncIterator[dict[str, str]]:
        cursor = after
        while True:
            if await request.is_disconnected():
                return
            async with sessions(tenant_id) as session:
                replies = await _replies(session, tenant_id, execution_id, cursor)
                row = await session.get(FlowExecution, execution_id)
                status = row.status if row is not None else ExecutionStatus.FAILED
            for reply in replies:
                cursor = (reply.at, UUID(reply.id))
                yield {
                    "event": "message",
                    "id": f"{reply.at.isoformat()}|{reply.id}",
                    "data": reply.model_dump_json(),
                }
            if status in TERMINAL:
                yield {"event": "end", "data": json.dumps({"status": status.value})}
                return
            await asyncio.sleep(POLL_SECONDS)

    # `no-transform` keeps compressing proxies (Next's rewrite, gzip middlewares) from
    # buffering the stream; `X-Accel-Buffering` does the same for nginx-style proxies.
    return EventSourceResponse(
        events(),
        ping=15,
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


def _parse_last_event_id(value: str | None) -> tuple[datetime, UUID]:
    if not value or "|" not in value:
        return (_EPOCH, _NIL)
    at, _, raw_id = value.partition("|")
    try:
        return (datetime.fromisoformat(at), UUID(raw_id))
    except ValueError:
        return (_EPOCH, _NIL)


# ── Proposal ──────────────────────────────────────────────────────────────────


async def _trip_by_ref(session: Any, ref: str) -> Trip:
    """``ref`` is the trip id, its code (``IGS-2711``) or the short form (``t-2711``)."""
    try:
        return_ = await session.get(Trip, UUID(ref))
    except ValueError:
        code = ref.upper()
        if code.startswith("T-"):
            code = f"IGS-{code[2:]}"
        return_ = await session.scalar(select(Trip).where(Trip.code == code))
    if return_ is None:
        raise ProblemError(404, "not-found", "Proposal not found.")
    return return_


def _short_ref(trip: Trip) -> str:
    if trip.code and trip.code.upper().startswith("IGS-"):
        return f"t-{trip.code[4:]}"
    return str(trip.id)


def _enrollment_action(trip: Trip, body: ReserveIn) -> tuple[dict[str, Any], int]:
    travelers = trip.travelers or 1
    fees = ENROLLMENT_FEE_USD * travelers
    params = {
        "tripId": str(trip.id),
        "travelers": travelers,
        "enrollmentFeeUsd": ENROLLMENT_FEE_USD,
        "amountUsd": fees,
        "contact": {"name": body.name, "email": body.email.lower()},
        "note": body.note or "",
    }
    return params, fees


@router.get(
    "/proposals/{ref}",
    response_model=ProposalOut,
    summary="Coach-facing proposal for a trip (package price, no cost lines)",
    dependencies=[Depends(rate_limit("proposal-read", limit=60, window_s=60))],
)
async def get_proposal(ref: str, tenant_id: PublicTenant, sessions: Sessions) -> ProposalOut:
    async with sessions(tenant_id) as session:
        trip = await _trip_by_ref(session, ref)
        items = (
            await session.scalars(
                select(TripItem).where(TripItem.trip_id == trip.id).order_by(TripItem.day)
            )
        ).all()
        opponent_ids = {i.opponent_id for i in items if i.opponent_id}
        experience_ids = {i.experience_id for i in items if i.experience_id}
        opponents = {
            o.id: o
            for o in (
                await session.scalars(select(Opponent).where(Opponent.id.in_(opponent_ids)))
            ).all()
        }
        experiences = {
            e.id: e
            for e in (
                await session.scalars(select(Experience).where(Experience.id.in_(experience_ids)))
            ).all()
        }
        requested = await session.scalar(
            select(Approval.id).where(
                Approval.subject_type == "trip",
                Approval.subject_id == trip.id,
                Approval.status == ApprovalStatus.PENDING,
                Approval.proposed_action["action"].astext == "request_enrollment",
            )
        )
    team = dict((trip.pricing or {}).get("team") or {})
    slot_order = {"morning": 0, "afternoon": 1, "evening": 2}
    by_day: dict[int, list[ProposalItem]] = defaultdict(list)
    for item in sorted(items, key=lambda i: (i.day, slot_order.get(i.slot.value, 9))):
        opponent = opponents.get(item.opponent_id) if item.opponent_id else None
        experience = experiences.get(item.experience_id) if item.experience_id else None
        by_day[item.day].append(
            ProposalItem(
                slot=item.slot.value,
                kind=item.kind.value,
                title=_coach_title(item.kind.value, item.title, opponent, experience),
                time=item.time.strftime("%H:%M") if item.time else None,
                opponent=_opponent(opponent) if opponent else None,
                experience=experience.title if experience else None,
            )
        )
    days = (trip.end_date - trip.start_date).days + 1
    valid_until = min(
        trip.created_at.date() + timedelta(days=PROPOSAL_VALID_DAYS),
        trip.start_date - timedelta(days=BALANCE_DUE_DAYS),
    )
    return ProposalOut(
        id=trip.id,
        ref=_short_ref(trip),
        title=trip.title,
        team=str(team.get("name") or trip.title.split(" · ")[0]),
        program=team.get("program"),
        coach_name=team.get("coach"),
        sport=team.get("sport"),
        gender=team.get("gender"),
        level_score=team.get("level_score"),
        city=trip.city,
        country=trip.country,
        start_date=trip.start_date,
        end_date=trip.end_date,
        days=days,
        travelers=trip.travelers,
        price_per_person_usd=trip.price_per_person_usd,
        enrollment_fee_usd=ENROLLMENT_FEE_USD,
        installment_usd=INSTALLMENT_USD,
        first_installment_due_days=30,
        second_installment_due_days=90,
        balance_due=trip.start_date - timedelta(days=BALANCE_DUE_DAYS),
        valid_until=valid_until,
        status=trip.status.value,
        summary=trip.summary,
        itinerary=[
            ProposalDay(day=d, date=trip.start_date + timedelta(days=d - 1), items=by_day[d])
            for d in range(1, days + 1)
        ],
        opponents=[_opponent(o) for o in opponents.values()],
        experiences=sorted({e.title for e in experiences.values()}),
        included=INCLUDED,
        not_included=NOT_INCLUDED,
        enrollment_requested=requested is not None,
    )


def _opponent(o: Opponent) -> ProposalOpponent:
    return ProposalOpponent(
        name=o.name, city=o.city, level_score=o.level_score, description=o.description
    )


@router.post(
    "/proposals/{ref}/reserve",
    response_model=ReserveOut,
    status_code=201,
    summary="Ask to enroll: creates an enrollment approval for ops (nothing is charged)",
    dependencies=[Depends(rate_limit("proposal-reserve", limit=5, window_s=300))],
)
async def reserve(
    ref: str,
    body: ReserveIn,
    tenant_id: PublicTenant,
    sessions: Sessions,
    rid: RequestId,
) -> ReserveOut:
    async with sessions(tenant_id) as session:
        trip = await _trip_by_ref(session, ref)
        params, fees = _enrollment_action(trip, body)
        digest = payload_hash("request_enrollment", params)
        existing = await session.scalar(
            select(Approval).where(
                Approval.subject_type == "trip",
                Approval.subject_id == trip.id,
                Approval.payload_hash == digest,
                Approval.status == ApprovalStatus.PENDING,
            )
        )
        if existing is not None:  # same coach clicking twice: one approval
            return ReserveOut(approval_id=existing.id, status="pending", enrollment_fees_usd=fees)
        approval = Approval(
            id=uuid7(),
            tenant_id=tenant_id,
            subject_type="trip",
            subject_id=trip.id,
            title=f"Enroll the team (US${ENROLLMENT_FEE_USD} per traveler) · {trip.title}",
            details={
                "summary": (
                    f"{body.name} ({body.email}) wants to reserve {trip.title}. Confirm "
                    f"availability and send the enrollment invoice for US${fees:,} "
                    f"({params['travelers']} × US${ENROLLMENT_FEE_USD})."
                ),
                "source": "proposal",
            },
            proposed_action={"action": "request_enrollment", "params": params},
            payload_hash=digest,
            risk_class=ToolClass.EXTERNAL,
            assignee_role=UserRole.OPS,
            expires_at=datetime.now(UTC) + timedelta(hours=48),
        )
        session.add(approval)
        await session.flush()
        await audit(
            session,
            _coach(tenant_id, f"coach:{body.email}"),
            action="proposal.reserve_requested",
            subject_type="trip",
            subject_id=trip.id,
            after={"approval_id": str(approval.id), "enrollment_fees_usd": fees},
            request_id=rid,
        )
        await emit(
            session,
            tenant_id=tenant_id,
            type="proposal.enrollment_requested",
            subject_type="trip",
            subject_id=trip.id,
            payload={"approvalId": str(approval.id), "amountUsd": fees},
        )
        return ReserveOut(approval_id=approval.id, status="pending", enrollment_fees_usd=fees)


# Ops names items in Spanish for the team; the coach-facing proposal speaks English, built from
# the catalog (experience titles are English, opponents are proper names) or the item kind.
_COACH_TITLES = {
    "arrival": "Arrival at Ezeiza and transfer to the hotel",
    "departure": "Transfer to Ezeiza for your flight home",
    "training": "Training session with AFA-certified coaches",
    "free": "Free time and recovery",
}


def _coach_title(kind: str, ops_title: str, opponent: object, experience: object) -> str:
    if experience is not None:
        return str(getattr(experience, "title", ops_title))
    if kind == "match":
        if opponent is not None:
            return f"Match vs {getattr(opponent, 'name', '')}".strip()
        # Opponent not in the catalog yet (tentative): keep the name, say it's pending.
        return f"Match vs {ops_title.removeprefix('vs ').strip()} (to be confirmed)"
    return _COACH_TITLES.get(kind, ops_title)

"""Lead intake: the site's Plan a Tour form and forwarded emails in; the ops view of them out.

Inbound (no user, no API key)
    ``POST /v1/intake/form`` takes the form's exact fields as JSON or urlencoded. ``POST
    /v1/intake/email`` takes one raw RFC 822 message (``message/rfc822``), e.g. from a mail
    forwarder. Both are signed: ``X-IGS-Timestamp`` + ``X-IGS-Signature: sha256=<hex>`` with
    HMAC-SHA256 over ``"<timestamp>.<raw body>"`` (5-minute skew). The form may instead carry
    the public ``X-IGS-Site-Key`` from an allowed ``Origin``. With nothing configured, only the
    demo tenant accepts unsigned requests, in demo mode. Every call is rate-limited by address.
    The reply never says whether the email matched a client, or whether it looked like spam.

Ops
    ``GET /v1/intake`` lists open inquiries by response due time; ``GET /v1/intake/sla`` is the
    1-business-day clock for Hoy; ``GET /v1/intake/{id}`` shows the extraction, score and reply.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from urllib.parse import parse_qs
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from igs_common.db.models import Contact, LeadIntake
from igs_common.intake import BusinessCalendar, PlanATourForm, parse_email
from igs_common.llm import LLMClient, LLMSettings, create_llm
from igs_core.config import Settings
from igs_core.deps import AppSettings, CurrentPrincipal
from igs_core.errors import ProblemError
from igs_core.intake import Inquiry, receive
from igs_core.ratelimit import rate_limit
from igs_core.runtime import RequestId, Sessions

router = APIRouter(prefix="/intake", tags=["intake"])

MAX_SKEW_S = 300
MAX_FORM_BYTES = 64 * 1024
MAX_EMAIL_BYTES = 2 * 1024 * 1024

SlaStateName = Literal["on_track", "at_risk", "breached", "met", "missed"]


class Accepted(BaseModel):
    id: UUID
    status: Literal["received"] = "received"
    reply_by: datetime = Field(description="When IGS promised to reply (1 business day).")


class ScoreReason(BaseModel):
    points: int
    reason: str


class IntakeSummary(BaseModel):
    id: UUID
    channel: str
    status: str
    relationship: str
    contact_name: str | None
    contact_email: str | None
    program: str | None
    score: int
    missing: list[str]
    received_at: datetime
    sla_due_at: datetime
    sla_state: SlaStateName
    business_hours_left: float
    first_response_at: datetime | None
    lead_id: UUID | None
    account_id: UUID | None
    approval_id: UUID | None


class IntakeDetail(IntakeSummary):
    score_reasons: list[ScoreReason]
    extracted: dict[str, Any]
    body_text: str
    submitted: dict[str, Any]


class IntakeSla(BaseModel):
    """The 1-business-day promise, for the Hoy queue."""

    open: int
    on_track: int
    at_risk: int
    breached: int
    next_due_at: datetime | None = Field(description="Earliest unanswered due time (may be past).")
    met_last_7_days: int
    missed_last_7_days: int


# ── Wiring ────────────────────────────────────────────────────────────────────


def calendar_for(settings: Settings) -> BusinessCalendar:
    return BusinessCalendar(tz=settings.intake_timezone)


def intake_llm(request: Request) -> LLMClient | None:
    """The extractor model, or None (rules only) when no provider key is configured."""
    state = request.app.state
    if hasattr(state, "intake_llm"):
        return state.intake_llm  # type: ignore[no-any-return]
    llm = getattr(state, "llm", None)
    if llm is None:
        try:
            settings = LLMSettings()
            llm = create_llm(settings) if settings.openai_api_key is not None else None
        except Exception:  # noqa: BLE001 - a model misconfiguration must not stop intake
            llm = None
    state.intake_llm = llm
    return llm


async def _tenant(request: Request, settings: Settings) -> UUID:
    slug = settings.intake_tenant_slug or settings.demo_tenant_slug
    tenant_id = await request.app.state.repos.directory.tenant_id_by_slug(slug)
    if tenant_id is None:
        raise ProblemError(503, "intake-unavailable", "Intake is not configured.")
    return tenant_id  # type: ignore[no-any-return]


def _verify(request: Request, raw: bytes, settings: Settings, *, allow_site_key: bool) -> None:
    secret = settings.intake_hmac_secret
    signature = request.headers.get("x-igs-signature")
    if signature is not None and secret is not None:
        timestamp = request.headers.get("x-igs-timestamp", "")
        try:
            skew = abs(time.time() - int(timestamp))
        except ValueError:
            skew = MAX_SKEW_S + 1
        expected = hmac.new(
            secret.get_secret_value().encode(), timestamp.encode() + b"." + raw, hashlib.sha256
        ).hexdigest()
        if skew <= MAX_SKEW_S and hmac.compare_digest(signature, f"sha256={expected}"):
            return
        raise ProblemError(401, "bad-signature", "The request signature is not valid.")
    site_key = request.headers.get("x-igs-site-key")
    if allow_site_key and settings.intake_site_key and site_key is not None:
        origin = request.headers.get("origin", "")
        if hmac.compare_digest(site_key, settings.intake_site_key) and (
            not settings.intake_allowed_origins or origin in settings.intake_allowed_origins
        ):
            return
        raise ProblemError(401, "bad-site-key", "This site may not post inquiries.")
    configured = secret is not None or (allow_site_key and settings.intake_site_key)
    if not configured and settings.demo_mode and not settings.intake_tenant_slug:
        return  # the public demo: unsigned posts land in the demo tenant only
    raise ProblemError(401, "unsigned", "Sign the request (X-IGS-Signature).")


async def _body(request: Request, limit: int) -> bytes:
    raw = await request.body()
    if len(raw) > limit:
        raise ProblemError(413, "too-large", "The request body is too large.")
    return raw


# ── Inbound ───────────────────────────────────────────────────────────────────


@router.post(
    "/form",
    response_model=Accepted,
    status_code=202,
    summary="The site's Plan a Tour form (JSON or urlencoded, signed or with the site key)",
    dependencies=[Depends(rate_limit("intake-form", limit=5, window_s=600))],
)
async def submit_form(
    request: Request, settings: AppSettings, sessions: Sessions, rid: RequestId
) -> Accepted:
    raw = await _body(request, MAX_FORM_BYTES)
    _verify(request, raw, settings, allow_site_key=True)
    form = _parse_form(raw, request.headers.get("content-type", ""))
    now = datetime.now(UTC)
    inquiry = Inquiry(
        channel="form",
        dedupe_key=form.dedupe_key(),
        first_name=form.first_name,
        full_name=form.full_name,
        email=form.email,
        program=form.program,
        source_text=form.source_text(),
        submitted=form.model_dump(exclude={"website"}),
        received_at=now,
        role=form.role,
        how_heard=form.how_heard,
        phone=f"{form.phone_country_code} {form.phone}".strip() if form.phone else None,
        travel_window=form.travel_window,
        spam=form.is_spam,
    )
    return await _receive(request, settings, sessions, inquiry, rid)


@router.post(
    "/email",
    response_model=Accepted,
    status_code=202,
    summary="One raw RFC 822 email (direct or forwarded inquiry), signed",
    dependencies=[Depends(rate_limit("intake-email", limit=120, window_s=60))],
)
async def submit_email(
    request: Request, settings: AppSettings, sessions: Sessions, rid: RequestId
) -> Accepted:
    raw = await _body(request, MAX_EMAIL_BYTES)
    _verify(request, raw, settings, allow_site_key=False)
    try:
        mail = parse_email(raw)
    except Exception as exc:  # noqa: BLE001 - any parser failure is the sender's problem
        raise ProblemError(422, "invalid-email", "Not a readable email message.") from exc
    if not mail.sender_email or "@" not in mail.sender_email:
        raise ProblemError(422, "no-sender", "The email has no sender address.")
    first, _, _ = mail.sender_name.partition(" ")
    submitted: dict[str, Any] = {
        "from": mail.sender_email,
        "name": mail.sender_name,
        "subject": mail.subject,
        "message_id": mail.message_id,
        "in_reply_to": mail.in_reply_to,
        "forwarded": mail.forwarded,
        "forwarded_by": mail.forwarded_by,
        "forwarder_note": mail.forwarder_note,
    }
    inquiry = Inquiry(
        channel="email",
        dedupe_key=mail.dedupe_key(),
        first_name=first or mail.sender_name,
        full_name=mail.sender_name,
        email=mail.sender_email,
        program="",
        source_text=mail.source_text(),
        submitted=submitted,
        received_at=min(mail.received_at or datetime.now(UTC), datetime.now(UTC)),
        subject=mail.subject or None,
    )
    return await _receive(request, settings, sessions, inquiry, rid)


async def _receive(
    request: Request, settings: Settings, sessions: Any, inquiry: Inquiry, rid: str | None
) -> Accepted:
    tenant_id = await _tenant(request, settings)
    async with sessions(tenant_id) as session:
        result = await receive(
            session,
            tenant_id,
            inquiry,
            llm=intake_llm(request),
            calendar=calendar_for(settings),
            request_id=rid,
        )
    return Accepted(id=result.intake.id, reply_by=result.intake.sla_due_at)


def _parse_form(raw: bytes, content_type: str) -> PlanATourForm:
    try:
        if content_type.startswith("application/x-www-form-urlencoded"):
            fields = {k: v[0] for k, v in parse_qs(raw.decode(), keep_blank_values=True).items()}
            return PlanATourForm.model_validate(fields)
        return PlanATourForm.model_validate(json.loads(raw or b"{}"))
    except (ValidationError, ValueError) as exc:
        detail = (
            "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
            if isinstance(exc, ValidationError)
            else "The body is not valid JSON."
        )
        raise ProblemError(422, "invalid-form", detail) from exc


# ── Ops ───────────────────────────────────────────────────────────────────────


def _mask(email: str | None) -> str | None:
    """The public demo shows who wrote, not how to reach them."""
    if not email or "@" not in email:
        return email
    local, domain = email.split("@", 1)
    return f"{local[:1]}***@{domain}"


def _summary_fields(
    row: LeadIntake, contact: Contact | None, cal: BusinessCalendar, now: datetime, *, demo: bool
) -> dict[str, Any]:
    submitted = row.submitted or {}
    email = contact.email if contact else submitted.get("email") or submitted.get("from")
    return {
        "id": row.id,
        "channel": row.channel,
        "status": row.status,
        "relationship": row.relationship,
        "contact_name": contact.name if contact else submitted.get("name"),
        "contact_email": _mask(email) if demo else email,
        "program": (contact.organization if contact else None) or submitted.get("program"),
        "score": row.score,
        "missing": list(row.missing or []),
        "received_at": row.received_at,
        "sla_due_at": row.sla_due_at,
        "sla_state": cal.state(row.sla_due_at, now, row.first_response_at),
        "business_hours_left": round(cal.business_hours_between(now, row.sla_due_at), 1),
        "first_response_at": row.first_response_at,
        "lead_id": row.lead_id,
        "account_id": row.account_id,
        "approval_id": row.approval_id,
    }


@router.get("", response_model=list[IntakeSummary], summary="Inquiries, soonest reply due first")
async def list_intake(
    principal: CurrentPrincipal,
    sessions: Sessions,
    settings: AppSettings,
    status: Literal["open", "lead_created", "spam"] | None = "open",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[IntakeSummary]:
    cal, now = calendar_for(settings), datetime.now(UTC)
    async with sessions(principal.tenant_id) as session:
        query = (
            select(LeadIntake, Contact)
            .outerjoin(Contact, Contact.id == LeadIntake.contact_id)
            .order_by(LeadIntake.sla_due_at, LeadIntake.id)
            .limit(limit)
        )
        if status is not None:
            query = query.where(LeadIntake.status == status)
        rows = (await session.execute(query)).all()
    return [
        IntakeSummary(**_summary_fields(r, c, cal, now, demo=principal.kind == "demo"))
        for r, c in rows
    ]


@router.get("/sla", response_model=IntakeSla, summary="The 1-business-day response clock")
async def intake_sla(
    principal: CurrentPrincipal, sessions: Sessions, settings: AppSettings
) -> IntakeSla:
    cal, now = calendar_for(settings), datetime.now(UTC)
    week_ago = now - timedelta(days=7)
    async with sessions(principal.tenant_id) as session:
        waiting = (
            (
                await session.execute(
                    select(LeadIntake.sla_due_at).where(
                        LeadIntake.status != "spam", LeadIntake.first_response_at.is_(None)
                    )
                )
            )
            .scalars()
            .all()
        )
        answered = (
            await session.execute(
                select(LeadIntake.sla_due_at, LeadIntake.first_response_at).where(
                    LeadIntake.status != "spam", LeadIntake.first_response_at >= week_ago
                )
            )
        ).all()
    states = [cal.state(due, now) for due in waiting]
    return IntakeSla(
        open=len(waiting),
        on_track=states.count("on_track"),
        at_risk=states.count("at_risk"),
        breached=states.count("breached"),
        next_due_at=min(waiting, default=None),
        met_last_7_days=sum(1 for due, done in answered if done is not None and done <= due),
        missed_last_7_days=sum(1 for due, done in answered if done is not None and done > due),
    )


@router.get("/{intake_id}", response_model=IntakeDetail, summary="One inquiry in full")
async def get_intake(
    intake_id: UUID, principal: CurrentPrincipal, sessions: Sessions, settings: AppSettings
) -> IntakeDetail:
    cal, now = calendar_for(settings), datetime.now(UTC)
    async with sessions(principal.tenant_id) as session:
        row = await session.get(LeadIntake, intake_id)
        if row is None:
            raise ProblemError(404, "not-found", "Inquiry not found.")
        contact = await session.get(Contact, row.contact_id) if row.contact_id else None
    demo = principal.kind == "demo"
    submitted = dict(row.submitted or {})
    if demo:
        for key in ("email", "from", "phone", "forwarded_by"):
            if submitted.get(key):
                submitted[key] = _mask(submitted[key]) if "@" in str(submitted[key]) else "***"
    return IntakeDetail(
        **_summary_fields(row, contact, cal, now, demo=demo),
        score_reasons=[ScoreReason(**r) for r in row.score_reasons or []],
        extracted=row.extracted or {},
        body_text=row.body_text,
        submitted=submitted,
    )

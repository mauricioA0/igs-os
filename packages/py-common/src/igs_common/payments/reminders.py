"""Payment reminder drafts: facts from code, tone from the LLM, checked before ops sees them.

* ``group_reminders`` turns positions into one reminder per trip and escalation stage, with a
  stable ``dedupe_key`` so a daily run never queues the same reminder twice.
* ``draft_reminder`` asks the model for the subject, opening and closing only. The amounts and
  dates table (``[[DETAILS]]``) is rendered by code, and traveler names never reach the model.
* ``check_draft`` rejects any number in the model's text that isn't one of the facts. A draft
  that fails falls back to the deterministic template, so a bad generation can't change what a
  coach is told they owe.

Nothing is sent from here: the result becomes an approval (``inbox.enqueue_reminders``).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from igs_common.llm import GenerateOptions, LLMClient, LLMError, Message, Role

from .position import PaymentLine, TripPosition
from .schedule import ItemKind, Stage

DETAILS = "[[DETAILS]]"
ACTION = "send_payment_reminder"

# Worst first: a trip with overdue and upcoming items gets one firm reminder covering both.
_SEVERITY = [
    Stage.CANCELLATION_RISK,
    Stage.OVERDUE_7,
    Stage.OVERDUE,
    Stage.T_MINUS_1,
    Stage.T_MINUS_7,
]
_KIND_LABEL = {
    ItemKind.ENROLLMENT: "Enrollment fee",
    ItemKind.INSTALLMENT_1: "First installment",
    ItemKind.INSTALLMENT_2: "Second installment",
    ItemKind.INSTALLMENT_3: "Third installment",
    ItemKind.INSTALLMENT: "Installment",
    ItemKind.BALANCE: "Final balance",
    ItemKind.FULL: "Program payment",
    ItemKind.OTHER: "Payment",
}
_STAGE_ES = {
    Stage.T_MINUS_7: "vence en 7 días",
    Stage.T_MINUS_1: "vence mañana",
    Stage.OVERDUE: "vencido",
    Stage.OVERDUE_7: "vencido hace más de una semana",
    Stage.CANCELLATION_RISK: "riesgo de cancelación",
}


@dataclass(frozen=True)
class ReminderGroup:
    position: TripPosition
    stage: Stage  # worst stage among the lines
    lines: tuple[PaymentLine, ...]
    today: date

    @property
    def total_usd(self) -> int:
        return sum(line.outstanding_usd for line in self.lines)

    @property
    def seats(self) -> int | None:
        """Seats covered, or None when any line is an invoice (the sheet doesn't say)."""
        if any(line.seats is None for line in self.lines):
            return None
        return sum(line.seats or 0 for line in self.lines)

    @property
    def dedupe_key(self) -> str:
        """Same trip, stage and items → same key, whatever day the scan runs."""
        items = ",".join(
            sorted(
                f"{line.kind.value}@{line.due.isoformat()}#{line.ref or 'group'}"
                for line in self.lines
            )
        )
        digest = hashlib.sha256(items.encode()).hexdigest()[:16]
        return f"payrem:{self.position.plan.trip_id}:{self.stage.value}:{digest}"

    @property
    def expires_on(self) -> date:
        """After this the reminder is stale (the next stage supersedes it)."""
        if self.stage.is_overdue:
            return self.today + timedelta(days=7)
        return min(line.due for line in self.lines)


def group_reminders(positions: Iterable[TripPosition], *, today: date) -> list[ReminderGroup]:
    groups: list[ReminderGroup] = []
    for pos in positions:
        lines = tuple(line for line in pos.lines if line.stage.needs_reminder)
        if not lines:
            continue
        stage = next(s for s in _SEVERITY if any(line.stage is s for line in lines))
        groups.append(ReminderGroup(pos, stage, lines, today))
    order = {s: i for i, s in enumerate(_SEVERITY)}
    return sorted(groups, key=lambda g: (order[g.stage], -g.total_usd))


# ── Facts ──────────────────────────────────────────────────────────────────


def usd(amount: int) -> str:
    return f"US${amount:,}"


def long_date(d: date) -> str:
    return f"{d:%B} {d.day}, {d.year}"


def _who(line: PaymentLine) -> str:
    if line.seats is None:
        return f"invoice {line.ref}" if line.ref else usd(line.amount_usd)
    return f"{line.seats} traveler{'s' if line.seats != 1 else ''} × {usd(line.amount_usd)}"


def _when(line: PaymentLine) -> str:
    if line.days < 0:
        late = -line.days
        return f"was due {long_date(line.due)} ({late} day{'s' if late != 1 else ''} late)"
    if line.days == 0:
        return f"due today, {long_date(line.due)}"
    return f"due {long_date(line.due)}"


def render_details(group: ReminderGroup) -> str:
    code = group.position.plan.code or group.position.plan.title
    rows = [
        f"- {code} · {_KIND_LABEL[line.kind]} · {_who(line)} · {_when(line)} · "
        f"{usd(line.outstanding_usd)} outstanding"
        for line in group.lines
    ]
    rows.append(f"Total outstanding: {usd(group.total_usd)}")
    return "\n".join(rows)


def allowed_numbers(group: ReminderGroup) -> frozenset[str]:
    """Every number the model may write: amounts, seat counts, days late, dates, the trip code."""
    nums: set[int] = {group.total_usd, 110, 30, 90}
    for line in group.lines:
        nums |= {line.outstanding_usd, line.amount_usd, line.seats or 0, abs(line.days)}
        nums |= {line.due.day, line.due.month, line.due.year}
    start = group.position.plan.start_date
    nums |= {start.day, start.month, start.year}
    out = {str(n) for n in nums}
    for text in (group.position.plan.code or "", *(line.ref or "" for line in group.lines)):
        out |= set(re.findall(r"\d+", text))
    return frozenset(out)


_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def check_draft(text: str, allowed: frozenset[str]) -> list[str]:
    """Problems with a model draft; empty means it's safe to show ops."""
    problems: list[str] = []
    if text.count(DETAILS) != 1:
        problems.append(f"the draft must contain {DETAILS} exactly once")
    body = text.replace(DETAILS, "")
    for raw in _NUMBER.findall(body):
        value = raw.replace(",", "")
        if value.endswith(".00"):
            value = value[:-3]
        if value not in allowed:
            problems.append(f"number not in the facts: {raw}")
    return problems


# ── Drafting ───────────────────────────────────────────────────────────────


class ReminderDraft(BaseModel):
    subject: str = Field(max_length=160)
    body: str = Field(max_length=4000, description=f"Must contain {DETAILS} exactly once.")


@dataclass(frozen=True)
class Draft:
    subject: str
    body: str  # with the details rendered in
    source: Literal["llm", "template"]
    problems: tuple[str, ...] = ()


_TONE = {
    Stage.T_MINUS_7: "a friendly heads-up a week ahead",
    Stage.T_MINUS_1: "a short, friendly reminder that it's due tomorrow or today",
    Stage.OVERDUE: "polite but clear: the payment is late",
    Stage.OVERDUE_7: "firm and helpful: more than a week late; offer a call to sort it out",
    Stage.CANCELLATION_RISK: (
        "serious and respectful: 30+ days late puts the seats at risk under the terms; "
        "ask for payment or a call this week"
    ),
}

INSTRUCTIONS = f"""You write payment reminder emails for Infinity Global Sports (IGS), a sports
tour operator, to a US coach or athletic director. Write in English, warm and professional,
like the IGS site: short sentences, no hype, no emojis.

Return a subject and a body. The body is the opening paragraph, then the line {DETAILS} on its
own (the system inserts the exact amounts and due dates there), then one closing paragraph and
the signature "— Martín, Infinity Global Sports".

Rules:
- Never write an amount, date or count yourself except the ones given in FACTS; prefer
  referring to "the details below".
- Don't invent fees, discounts, deadlines or consequences beyond what FACTS says.
- Don't mention individual travelers or invoice numbers.
"""


def _facts_prompt(group: ReminderGroup) -> str:
    plan = group.position.plan
    first_name = plan.to.name.split()[0] if plan.to and plan.to.name else "Coach"
    return "\n".join(
        [
            "FACTS",
            f"- recipient first name: {first_name}",
            f"- client: {plan.account_name or plan.title}",
            f"- trip: {plan.code or ''} {plan.title}, departs {long_date(plan.start_date)}",
            f"- tone: {_TONE[group.stage]}",
            f"- total outstanding: {usd(group.total_usd)}"
            + (f" across {group.seats} traveler(s)" if group.seats else ""),
            f"- items: {', '.join(sorted({_KIND_LABEL[line.kind] for line in group.lines}))}",
        ]
    )


def template_draft(group: ReminderGroup) -> Draft:
    plan = group.position.plan
    first_name = plan.to.name.split()[0] if plan.to and plan.to.name else "Coach"
    trip = plan.code or plan.title
    intro = {
        Stage.T_MINUS_7: f"Hi {first_name}, a quick heads-up: payments for {trip} are due "
        "next week.",
        Stage.T_MINUS_1: f"Hi {first_name}, a friendly reminder that payments for {trip} are "
        "due now.",
        Stage.OVERDUE: f"Hi {first_name}, we haven't received the payments below for {trip} yet.",
        Stage.OVERDUE_7: f"Hi {first_name}, the payments below for {trip} are more than a week "
        "late. If something is holding them up, we're happy to help.",
        Stage.CANCELLATION_RISK: f"Hi {first_name}, the payments below for {trip} are over 30 "
        "days late, which under our terms puts the seats at risk. Please let us know this week "
        "how you'd like to proceed.",
    }[group.stage]
    subject = {
        Stage.T_MINUS_7: f"{trip}: payments due next week",
        Stage.T_MINUS_1: f"{trip}: payments due now",
        Stage.OVERDUE: f"{trip}: payment reminder",
        Stage.OVERDUE_7: f"{trip}: payments overdue",
        Stage.CANCELLATION_RISK: f"{trip}: overdue payments, seats at risk",
    }[group.stage]
    body = (
        f"{intro}\n\n{render_details(group)}\n\nYou can reply to this email with any question."
        "\n\n— Martín, Infinity Global Sports"
    )
    return Draft(subject, body, "template")


async def draft_reminder(llm: LLMClient | None, group: ReminderGroup) -> Draft:
    """Model draft when it passes ``check_draft``; otherwise the template (with the reasons)."""
    if llm is None:
        return template_draft(group)
    try:
        result = await llm.generate(
            Role.FAST,
            [Message("user", _facts_prompt(group))],
            output_model=ReminderDraft,
            options=GenerateOptions(
                instructions=INSTRUCTIONS,
                reasoning_effort="minimal",
                max_output_tokens=600,
                cache_key="payments.reminder",
                metadata={"feature": "payments.reminder", "stage": group.stage.value},
            ),
        )
    except LLMError as e:
        return _fallback(group, (f"model error: {e}",))
    draft = result.parsed
    if draft is None:
        return _fallback(group, ("no structured output",))
    allowed = allowed_numbers(group)
    problems = check_draft(draft.body, allowed) + [
        f"subject: {p}" for p in check_draft(draft.subject + DETAILS, allowed)
    ]
    if problems:
        return _fallback(group, tuple(problems))
    return Draft(draft.subject, draft.body.replace(DETAILS, render_details(group)), "llm")


def _fallback(group: ReminderGroup, problems: Sequence[str]) -> Draft:
    t = template_draft(group)
    return Draft(t.subject, t.body, "template", tuple(problems))


def approval_title(group: ReminderGroup) -> str:
    plan = group.position.plan
    who = plan.to.name if plan.to else "el coach (sin email)"
    total = f"US${group.total_usd:,}".replace(",", ".")
    return (
        f"Recordatorio de pago a {who} · {plan.code or plan.title} · {total} "
        f"({_STAGE_ES[group.stage]})"
    )

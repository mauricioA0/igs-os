"""The first reply to the coach, drafted for a person to approve (never sent on its own).

A template, not a model: it only asks for what is missing and offers call times. It quotes no
price, no availability and no rival, so there is nothing in it that could be wrong about IGS.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

# One question per gap, in the order a coach would answer them; related fields share a question.
_QUESTIONS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("sport", "gender"), "Which team would travel (sport, and men's, women's or co-ed)?"),
    (
        ("age_group", "level_score"),
        "The team's age group and competitive level (for example NCAA D3, ECNL U17, varsity), "
        "so we match opponents to your level",
    ),
    (("group_size",), "Roughly how many travelers, including coaches and staff"),
    (
        ("destination_country",),
        "Which destination interests you most: Argentina, Brazil, Costa Rica or Spain",
    ),
    (("travel_start", "duration_days"), "Preferred travel dates and how many days you'd like"),
)
MAX_QUESTIONS = 4


@dataclass(frozen=True)
class DraftReply:
    to: str
    subject: str
    body: str
    questions: tuple[str, ...]
    call_slots: tuple[datetime, ...]

    def action_params(self) -> dict[str, Any]:
        """The ``send_email`` params the approval shows and hashes (edit-and-approve friendly)."""
        return {"to": self.to, "subject": self.subject, "body": self.body}


def draft_reply(
    *,
    first_name: str,
    email: str,
    program: str,
    values: dict[str, Any],
    missing: list[str],
    relationship: str,
    call_slots: list[datetime],
    slot_tz: str,
    in_reply_to_subject: str | None = None,
) -> DraftReply:
    questions = [q for fields, q in _QUESTIONS if any(f in missing for f in fields)][:MAX_QUESTIONS]
    team = _team_phrase(values)
    greeting = f"Hi {first_name.strip() or 'Coach'},"
    if relationship == "returning_customer":
        opening = (
            f"Great to hear from you again, and thanks for thinking of us for {program}'s "
            f"next tour{team}."
        )
    elif relationship == "referral":
        opening = (
            f"Thanks for reaching out about a tour for {program}{team}, and for the referral "
            "that brought you to us."
        )
    else:
        opening = f"Thanks for reaching out about a tour for {program}{team}."

    parts = [greeting, "", opening, ""]
    if questions:
        parts += [
            "So we can send you sample itinerary options that fit your team, could you tell us:",
            *[f"- {q}" for q in questions],
            "",
        ]
    else:
        parts += [
            "We have what we need to put together sample itinerary options for your team, "
            "and we'll send them shortly.",
            "",
        ]
    zone = ZoneInfo(slot_tz)
    label = _tz_label(slot_tz)
    if call_slots:
        parts += [
            "If it's easier to talk it through, we can do a 20-minute call at any of these "
            f"times ({label}):",
            *[
                f"- {s.astimezone(zone):%a %b} {s.astimezone(zone).day}, {_clock(s, zone)}"
                for s in call_slots
            ],
            "Or just reply with a time that works for you.",
            "",
        ]
    parts += ["Best,", "The Infinity Global Sports team"]
    subject = (
        f"Re: {in_reply_to_subject}"
        if in_reply_to_subject
        else f"Your {program} tour with Infinity Global Sports"
    )
    return DraftReply(
        to=email,
        subject=subject,
        body="\n".join(parts),
        questions=tuple(questions),
        call_slots=tuple(call_slots),
    )


def _team_phrase(values: dict[str, Any]) -> str:
    gender = {"men": "men's", "women": "women's", "mixed": "co-ed"}.get(values.get("gender") or "")
    sport = (values.get("sport") or "").replace("_", " ")
    if not sport:
        return ""
    words = " ".join(w for w in (gender, sport) if w)
    destination = values.get("destination_country")
    return f" ({words}" + (f", {destination})" if destination else ")")


def _clock(moment: datetime, zone: ZoneInfo) -> str:
    local = moment.astimezone(zone)
    hour = local.hour % 12 or 12
    return f"{hour}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"


def _tz_label(tz: str) -> str:
    return {
        "America/New_York": "Eastern Time",
        "America/Denver": "Mountain Time",
        "America/Chicago": "Central Time",
        "America/Los_Angeles": "Pacific Time",
        "America/Argentina/Buenos_Aires": "Buenos Aires time",
    }.get(tz, tz)

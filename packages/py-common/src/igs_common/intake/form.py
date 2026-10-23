"""The "Plan Your Team's Tour" form of infinityglobalsports.com/plan-a-tour, field for field.

Read from the live form on 2026-10-22: first/last name, School / Club / Program, Role, email,
phone (country code + number), Target Travel Window ("e.g. Summer 2026, Spring break 2027"),
How did you hear about us?, the message, and hidden attribution fields (UTM, gclid, landing page,
segment). ``website`` is the site's own honeypot: people never see it, bots fill it in.
"""

from __future__ import annotations

import hashlib
import re
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, field_validator

Role = Literal[
    "Head Coach",
    "Assistant Coach",
    "Director of Coaching",
    "Executive Director",
    "Athletic Director",
    "Head of School",
    "Other",
]
HowHeard = Literal[
    "Google Search",
    "Social Media (Instagram/Facebook)",
    "Referral / Word of Mouth",
    "Email",
    "AI Assistant (ChatGPT, Gemini, etc.)",
    "Returning Customer",
    "Other",
]

# Deliberately loose (one @, a dot in the domain): the browser already validated it, and a
# real coach must never be rejected by a stricter regex than the site's own.
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

DECISION_MAKERS = frozenset(
    {"Athletic Director", "Head of School", "Director of Coaching", "Executive Director"}
)


class PlanATourForm(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(default="", max_length=80)
    program: str = Field(min_length=1, max_length=200, description="School / Club / Program")
    # Free text, not the Literal: a renamed option on the site must never reject a real coach.
    role: str | None = Field(default=None, max_length=100)
    email: str = Field(max_length=254)
    phone_country_code: str = Field(default="+1", max_length=6)
    phone: str = Field(default="", max_length=40)
    travel_window: str = Field(default="", max_length=200, description="Target Travel Window")
    how_heard: str | None = Field(default=None, max_length=100)
    message: str = Field(default="", max_length=5000)
    utm_source: str | None = Field(default=None, max_length=200)
    utm_medium: str | None = Field(default=None, max_length=200)
    utm_campaign: str | None = Field(default=None, max_length=200)
    utm_term: str | None = Field(default=None, max_length=200)
    utm_content: str | None = Field(default=None, max_length=200)
    gclid: str | None = Field(default=None, max_length=300)
    landing_page: str | None = Field(default=None, max_length=500)
    segment: str | None = Field(default=None, max_length=100)
    website: str = Field(default="", max_length=500, description="Honeypot: must stay empty.")

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        value = value.strip()
        if not EMAIL.match(value):
            raise ValueError("not an email address")
        return value.lower()

    @property
    def known_role(self) -> Role | None:
        return next((r for r in get_args(Role) if r == self.role), None)

    @property
    def known_how_heard(self) -> HowHeard | None:
        return next((h for h in get_args(HowHeard) if h == self.how_heard), None)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_spam(self) -> bool:
        return bool(self.website)

    def source_text(self) -> str:
        """What the coach wrote, labeled, for extraction (and for evidence checks)."""
        lines = [
            f"Program: {self.program}",
            f"Role: {self.role or '—'}",
            f"Target travel window: {self.travel_window or '—'}",
            f"How did you hear about us: {self.how_heard or '—'}",
            "",
            self.message or "(no message)",
        ]
        return "\n".join(lines)

    def dedupe_key(self) -> str:
        """Same person, same words → same intake (a double click or a browser retry)."""
        basis = "\x1f".join([self.email, self.program.casefold(), self.travel_window, self.message])
        return "form:" + hashlib.sha256(basis.encode()).hexdigest()[:32]

"""The "we respond within 1 business day" promise of IGS's Plan a Tour form, as a clock.

One business day is one full working day of time (``BUSINESS_HOURS`` hours) counted only inside
working hours, Monday to Friday, skipping holidays, in the sales team's timezone:

- Monday 15:00 → due Tuesday 15:00 (3 h on Monday + 6 h on Tuesday).
- Friday 20:00 or Saturday → the clock starts Monday 09:00 → due Monday 18:00.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

SlaState = Literal["on_track", "at_risk", "breached", "met", "missed"]

# US federal holidays IGS's US offices (New York, Denver) close for, 2026–2027.
US_HOLIDAYS = frozenset(
    {
        date(2026, 1, 1),
        date(2026, 1, 19),
        date(2026, 2, 16),
        date(2026, 5, 25),
        date(2026, 6, 19),
        date(2026, 7, 3),
        date(2026, 9, 7),
        date(2026, 10, 12),
        date(2026, 11, 11),
        date(2026, 11, 26),
        date(2026, 12, 25),
        date(2027, 1, 1),
        date(2027, 1, 18),
        date(2027, 2, 15),
        date(2027, 5, 31),
        date(2027, 6, 18),
        date(2027, 7, 5),
        date(2027, 9, 6),
        date(2027, 10, 11),
        date(2027, 11, 11),
        date(2027, 11, 25),
        date(2027, 12, 24),
    }
)


@dataclass(frozen=True)
class BusinessCalendar:
    tz: str = "America/New_York"
    opens: time = time(9, 0)
    closes: time = time(18, 0)
    holidays: frozenset[date] = field(default_factory=lambda: US_HOLIDAYS)
    # Left on the clock below which an open inquiry shows as at risk.
    at_risk_hours: float = 3.0

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    @property
    def day_hours(self) -> float:
        start = datetime.combine(date.min, self.opens)
        return (datetime.combine(date.min, self.closes) - start).total_seconds() / 3600

    def is_business_day(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays

    def _next_open(self, local: datetime) -> datetime:
        """``local`` itself when inside working hours, else the next opening."""
        d = local.date()
        if self.is_business_day(d) and self.opens <= local.time() < self.closes:
            return local
        if self.is_business_day(d) and local.time() < self.opens:
            return datetime.combine(d, self.opens, local.tzinfo)
        d += timedelta(days=1)
        while not self.is_business_day(d):
            d += timedelta(days=1)
        return datetime.combine(d, self.opens, local.tzinfo)

    def add_business_hours(self, start: datetime, hours: float) -> datetime:
        local = self._next_open(start.astimezone(self.zone))
        left = timedelta(hours=hours)
        while True:
            close = datetime.combine(local.date(), self.closes, local.tzinfo)
            if local + left <= close:
                return (local + left).astimezone(UTC)
            left -= close - local
            local = self._next_open(close)

    def business_hours_between(self, start: datetime, end: datetime) -> float:
        """Working hours from ``start`` to ``end`` (negative when ``end`` is earlier)."""
        if end < start:
            return -self.business_hours_between(end, start)
        local = self._next_open(start.astimezone(self.zone))
        stop = end.astimezone(self.zone)
        total = timedelta()
        while local < stop:
            close = datetime.combine(local.date(), self.closes, local.tzinfo)
            total += min(close, stop) - local
            local = self._next_open(close)
        return total.total_seconds() / 3600

    def due(self, received_at: datetime) -> datetime:
        return self.add_business_hours(received_at, self.day_hours)

    def state(
        self, due_at: datetime, now: datetime, responded_at: datetime | None = None
    ) -> SlaState:
        if responded_at is not None:
            return "met" if responded_at <= due_at else "missed"
        if now >= due_at:
            return "breached"
        if self.business_hours_between(now, due_at) <= self.at_risk_hours:
            return "at_risk"
        return "on_track"

    def call_slots(
        self, now: datetime, *, count: int = 3, hours: Iterable[int] = (10, 14, 16)
    ) -> list[datetime]:
        """Next free-looking call times for sales (no calendar yet: ops confirms the slot).

        Starts at least 4 working hours out so whoever approves the reply has time to send it.
        """
        earliest = self.add_business_hours(now, 4).astimezone(self.zone)
        slots: list[datetime] = []
        d = earliest.date()
        wanted = sorted(set(hours))
        while len(slots) < count:
            if self.is_business_day(d):
                for h in wanted:
                    slot = datetime.combine(d, time(h), self.zone)
                    if slot >= earliest and len(slots) < count:
                        slots.append(slot)
            d += timedelta(days=1)
        return [s.astimezone(UTC) for s in slots]

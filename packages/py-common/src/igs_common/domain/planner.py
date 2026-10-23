"""Deterministic itinerary planner.

Pure function: candidates come in already fetched (from SQL / vector search); the planner only
decides. Same input (in any order) always yields the same itinerary.

Rules (from the knowledge base "How we match opponents" / "Typical itinerary length"):
- Day 1 is arrival, the last day is departure.
- Matches are in the afternoon, never on consecutive days, never on day 2 (travel recovery).
- Opponents match sport, gender and age group, are in the destination city and within
  ``max_level_gap`` (default 1) of the team's level. Each opponent plays at most once.
- Other inner days: training in the morning, an experience (or free time) in the afternoon.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .enums import SLOT_ORDER, Gender, ItemKind, ProviderKind, Slot, Sport

MIN_DAYS = 3
MAX_DAYS = 21
MAX_MATCHES = 4


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TeamProfile(_Frozen):
    sport: Sport
    gender: Gender
    age_group: str
    level_score: Annotated[int, Field(ge=1, le=10)]
    city: str
    duration_days: Annotated[int, Field(ge=MIN_DAYS, le=MAX_DAYS)]
    # None = let the planner pick from duration; otherwise an upper bound.
    max_matches: Annotated[int, Field(ge=0, le=MAX_MATCHES)] | None = None
    max_level_gap: Annotated[int, Field(ge=0, le=3)] = 1


class OpponentCandidate(_Frozen):
    id: UUID
    name: str
    city: str
    sport: Sport
    gender: Gender
    age_groups: tuple[str, ...]
    level_score: Annotated[int, Field(ge=1, le=10)]
    # Optional relevance from retrieval (higher = better). Ties broken by id.
    relevance: float = 0.0


class ExperienceCandidate(_Frozen):
    id: UUID
    title: str
    city: str
    sports: tuple[Sport, ...] = ()  # empty = suitable for any sport
    price_usd: Annotated[int, Field(ge=0)]
    relevance: float = 0.0


class ProviderCandidate(_Frozen):
    id: UUID
    name: str
    kind: ProviderKind
    city: str
    unit_price_usd: Annotated[int, Field(ge=0)]
    unit: str


class PlannedItem(_Frozen):
    day: int
    slot: Slot
    kind: ItemKind
    title: str
    opponent_id: UUID | None = None
    experience_id: UUID | None = None
    provider_id: UUID | None = None


class Itinerary(_Frozen):
    days: int
    items: tuple[PlannedItem, ...]
    warnings: tuple[str, ...] = ()

    @property
    def match_days(self) -> tuple[int, ...]:
        return tuple(i.day for i in self.items if i.kind is ItemKind.MATCH)

    def items_on(self, day: int) -> tuple[PlannedItem, ...]:
        return tuple(i for i in self.items if i.day == day)


def target_match_count(duration_days: int) -> int:
    """~40% of the inner days, between 1 and 4 (8-12 day tours get 3-4 matches)."""
    inner = duration_days - 2
    return max(1, min(MAX_MATCHES, round(inner * 0.4)))


def candidate_match_days(duration_days: int) -> list[int]:
    """Days that may host a match: day 3 onwards, last inner day included, every other day."""
    return list(range(3, duration_days, 2))


def eligible_opponents(
    team: TeamProfile, candidates: list[OpponentCandidate]
) -> list[OpponentCandidate]:
    city = team.city.casefold()
    eligible = [
        o
        for o in candidates
        if o.sport is team.sport
        and o.gender is team.gender
        and team.age_group in o.age_groups
        and o.city.casefold() == city
        and abs(o.level_score - team.level_score) <= team.max_level_gap
    ]
    return sorted(
        eligible,
        key=lambda o: (abs(o.level_score - team.level_score), -o.relevance, str(o.id)),
    )


def _pick_provider(
    providers: list[ProviderCandidate], kind: ProviderKind, city: str
) -> ProviderCandidate | None:
    matches = [p for p in providers if p.kind is kind and p.city.casefold() == city.casefold()]
    return min(matches, key=lambda p: (p.unit_price_usd, str(p.id)), default=None)


def plan_itinerary(
    team: TeamProfile,
    opponents: list[OpponentCandidate],
    experiences: list[ExperienceCandidate],
    providers: list[ProviderCandidate],
) -> Itinerary:
    n = team.duration_days
    warnings: list[str] = []

    hotel = _pick_provider(providers, ProviderKind.HOTEL, team.city)
    transport = _pick_provider(providers, ProviderKind.TRANSPORT, team.city)
    referee = _pick_provider(providers, ProviderKind.REFEREE, team.city)
    venue = _pick_provider(providers, ProviderKind.VENUE, team.city)
    if hotel is None:
        warnings.append(f"No hotel provider in {team.city}.")
    if transport is None:
        warnings.append(f"No transport provider in {team.city}.")

    target = target_match_count(n)
    if team.max_matches is not None:
        target = min(target, team.max_matches)
    pool = eligible_opponents(team, opponents)
    slots = candidate_match_days(n)
    match_count = min(target, len(pool), len(slots))
    if match_count < target:
        warnings.append(
            f"Planned {match_count} of {target} matches: "
            f"{len(pool)} eligible opponents, {len(slots)} possible match days."
        )
    match_days = _spread(slots, match_count)

    city = team.city.casefold()
    exp_pool = sorted(
        (
            e
            for e in experiences
            if e.city.casefold() == city and (not e.sports or team.sport in e.sports)
        ),
        key=lambda e: (-e.relevance, e.price_usd, str(e.id)),
    )

    items: list[PlannedItem] = [
        PlannedItem(
            day=1,
            slot=Slot.AFTERNOON,
            kind=ItemKind.ARRIVAL,
            title=f"Arrival in {team.city} · airport transfer & hotel check-in",
            provider_id=hotel.id if hotel else None,
        ),
        PlannedItem(
            day=1, slot=Slot.EVENING, kind=ItemKind.FREE, title="Welcome dinner & team meeting"
        ),
    ]

    opponents_iter = iter(pool[:match_count])
    exp_iter = iter(exp_pool)
    for day in range(2, n):
        if day in match_days:
            opp = next(opponents_iter)
            items.append(
                PlannedItem(
                    day=day,
                    slot=Slot.MORNING,
                    kind=ItemKind.FREE,
                    title="Light activation & match prep",
                )
            )
            items.append(
                PlannedItem(
                    day=day,
                    slot=Slot.AFTERNOON,
                    kind=ItemKind.MATCH,
                    title=f"Match vs {opp.name}",
                    opponent_id=opp.id,
                    provider_id=referee.id if referee else None,
                )
            )
            continue
        items.append(
            PlannedItem(
                day=day,
                slot=Slot.MORNING,
                kind=ItemKind.TRAINING,
                title="Training session",
                provider_id=venue.id if venue else None,
            )
        )
        exp = next(exp_iter, None)
        if exp is None:
            items.append(
                PlannedItem(day=day, slot=Slot.AFTERNOON, kind=ItemKind.FREE, title="Free time")
            )
        else:
            items.append(
                PlannedItem(
                    day=day,
                    slot=Slot.AFTERNOON,
                    kind=ItemKind.EXPERIENCE,
                    title=exp.title,
                    experience_id=exp.id,
                    provider_id=transport.id if transport else None,
                )
            )

    items.append(
        PlannedItem(
            day=n,
            slot=Slot.MORNING,
            kind=ItemKind.DEPARTURE,
            title="Check-out & airport transfer",
            provider_id=transport.id if transport else None,
        )
    )
    items.sort(key=lambda i: (i.day, SLOT_ORDER[i.slot]))
    return Itinerary(days=n, items=tuple(items), warnings=tuple(warnings))


def _spread(slots: list[int], count: int) -> set[int]:
    """Pick ``count`` slots spread evenly across the trip (slots are already 2 apart)."""
    if count <= 0:
        return set()
    if count >= len(slots):
        return set(slots)
    if count == 1:
        return {slots[len(slots) // 2]}
    step = (len(slots) - 1) / (count - 1)
    return {slots[round(i * step)] for i in range(count)}

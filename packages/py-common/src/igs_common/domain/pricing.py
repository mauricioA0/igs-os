"""Per-person quote for a planned itinerary.

Cost lines are per person: provider unit price × how many units the itinerary uses, plus each
experience's price. Margin is applied on the subtotal and the final price is rounded up to the
nearest ``round_to`` dollars. Integer/Decimal math only — money never touches floats.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from .enums import ItemKind, ProviderKind
from .planner import ExperienceCandidate, Itinerary, ProviderCandidate

DEFAULT_MARGIN = Decimal("0.22")


class QuoteLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    unit_price_usd: Decimal
    quantity: int
    usd: Decimal


class Quote(BaseModel):
    model_config = ConfigDict(frozen=True)

    lines: tuple[QuoteLine, ...]
    subtotal_usd: Decimal
    margin_rate: Decimal
    margin_usd: Decimal
    price_per_person_usd: int
    group_size: int
    total_usd: int


def _units_for(kind: ProviderKind, itinerary: Itinerary) -> tuple[int, str]:
    """How many units of a provider kind one person consumes, and the line label."""
    items = itinerary.items
    match kind:
        case ProviderKind.HOTEL:
            return itinerary.days - 1, "Hotel nights"
        case ProviderKind.TRANSPORT | ProviderKind.GUIDE:
            return (
                itinerary.days,
                "Private transport" if kind is ProviderKind.TRANSPORT else "Guide",
            )
        case ProviderKind.REFEREE:
            return sum(i.kind is ItemKind.MATCH for i in items), "Certified referees"
        case ProviderKind.VENUE:
            return sum(i.kind is ItemKind.TRAINING for i in items), "Training venue sessions"
        case ProviderKind.CLUB:
            return 0, "Club fees"


def quote(
    itinerary: Itinerary,
    providers: list[ProviderCandidate],
    experiences: list[ExperienceCandidate],
    group_size: int,
    *,
    margin: Decimal = DEFAULT_MARGIN,
    round_to: int = 10,
) -> Quote:
    if not 1 <= group_size <= 80:
        raise ValueError("group_size must be between 1 and 80")
    if margin < 0 or round_to < 1:
        raise ValueError("margin must be >= 0 and round_to >= 1")

    by_id: dict[UUID, ProviderCandidate] = {p.id: p for p in providers}
    exp_by_id: dict[UUID, ExperienceCandidate] = {e.id: e for e in experiences}

    used_ids = {i.provider_id for i in itinerary.items if i.provider_id is not None}
    used_providers = sorted(
        (by_id[pid] for pid in used_ids if pid in by_id),
        key=lambda p: (p.kind.value, str(p.id)),
    )
    lines: list[QuoteLine] = []
    for p in used_providers:
        qty, label = _units_for(p.kind, itinerary)
        if qty <= 0:
            continue
        unit = Decimal(p.unit_price_usd)
        lines.append(
            QuoteLine(
                label=f"{label} · {p.name}", unit_price_usd=unit, quantity=qty, usd=unit * qty
            )
        )

    for item in itinerary.items:
        e = exp_by_id.get(item.experience_id) if item.experience_id is not None else None
        if item.kind is ItemKind.EXPERIENCE and e is not None:
            unit = Decimal(e.price_usd)
            lines.append(QuoteLine(label=e.title, unit_price_usd=unit, quantity=1, usd=unit))

    subtotal = sum((line.usd for line in lines), Decimal(0))
    margin_usd = (subtotal * margin).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    raw = subtotal + margin_usd
    step = Decimal(round_to)
    price = int((raw / step).to_integral_value(rounding=ROUND_CEILING) * step)
    return Quote(
        lines=tuple(lines),
        subtotal_usd=subtotal,
        margin_rate=margin,
        margin_usd=margin_usd,
        price_per_person_usd=price,
        group_size=group_size,
        total_usd=price * group_size,
    )

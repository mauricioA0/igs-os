from decimal import Decimal

import pytest

from igs_common.domain.enums import ItemKind
from igs_common.domain.planner import plan_itinerary
from igs_common.domain.pricing import quote

from .test_planner import EXPERIENCES, OPPONENTS, PROVIDERS, team


@pytest.fixture
def itinerary():
    return plan_itinerary(team(), OPPONENTS, EXPERIENCES, PROVIDERS)


def test_lines_follow_itinerary_usage(itinerary):
    q = quote(itinerary, PROVIDERS, EXPERIENCES, group_size=22)
    by_label = {line.label.split(" · ")[0]: line for line in q.lines}
    assert by_label["Hotel nights"].quantity == 9  # 10 days → 9 nights
    assert by_label["Private transport"].quantity == 10
    assert by_label["Certified referees"].quantity == len(itinerary.match_days)
    trainings = sum(i.kind is ItemKind.TRAINING for i in itinerary.items)
    assert by_label["Training venue sessions"].quantity == trainings
    exps = [i for i in itinerary.items if i.kind is ItemKind.EXPERIENCE]
    assert sum(
        line.quantity == 1 and line.label in {e.title for e in exps} for line in q.lines
    ) == len(exps)


def test_subtotal_margin_and_rounding(itinerary):
    q = quote(itinerary, PROVIDERS, EXPERIENCES, group_size=22)
    assert q.subtotal_usd == sum(line.usd for line in q.lines)
    assert q.margin_usd == (q.subtotal_usd * Decimal("0.22")).quantize(Decimal("0.01"))
    assert q.price_per_person_usd % 10 == 0
    assert q.price_per_person_usd >= q.subtotal_usd + q.margin_usd
    assert q.price_per_person_usd - (q.subtotal_usd + q.margin_usd) < 10
    assert q.total_usd == q.price_per_person_usd * 22


def test_known_value():
    it = plan_itinerary(team(duration_days=3), [], [], PROVIDERS)
    # 2 nights × 85 + 3 days × 30 + 0 matches + 1 training × 12 = 272; × 1.22 = 331.84 → 340
    q = quote(it, PROVIDERS, [], group_size=10)
    assert q.subtotal_usd == 272
    assert q.price_per_person_usd == 340


def test_zero_margin_and_custom_rounding(itinerary):
    q = quote(itinerary, PROVIDERS, EXPERIENCES, group_size=1, margin=Decimal(0), round_to=1)
    assert q.price_per_person_usd == q.subtotal_usd


@pytest.mark.parametrize("size", [0, 81])
def test_group_size_bounds(itinerary, size):
    with pytest.raises(ValueError):
        quote(itinerary, PROVIDERS, EXPERIENCES, group_size=size)


def test_unknown_providers_are_ignored(itinerary):
    q = quote(itinerary, [], [], group_size=5)
    assert q.lines == () and q.price_per_person_usd == 0

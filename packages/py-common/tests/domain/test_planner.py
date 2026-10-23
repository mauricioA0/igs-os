import random
from uuid import UUID, uuid5

import pytest
from pydantic import ValidationError

from igs_common.domain.enums import Gender, ItemKind, ProviderKind, Slot, Sport
from igs_common.domain.planner import (
    ExperienceCandidate,
    OpponentCandidate,
    ProviderCandidate,
    TeamProfile,
    candidate_match_days,
    eligible_opponents,
    plan_itinerary,
    target_match_count,
)

NS = UUID("00000000-0000-0000-0000-000000000000")


def uid(name: str) -> UUID:
    return uuid5(NS, name)


def team(**kw) -> TeamProfile:
    base: dict[str, object] = dict(
        sport=Sport.SOCCER,
        gender=Gender.WOMEN,
        age_group="college",
        level_score=7,
        city="Buenos Aires",
        duration_days=10,
    )
    return TeamProfile.model_validate(base | kw)


def opponent(name: str, level: int, **kw) -> OpponentCandidate:
    base: dict[str, object] = dict(
        id=uid(name),
        name=name,
        city="Buenos Aires",
        sport=Sport.SOCCER,
        gender=Gender.WOMEN,
        age_groups=("U19", "college"),
        level_score=level,
    )
    return OpponentCandidate.model_validate(base | kw)


def experience(title: str, price: int = 40, **kw) -> ExperienceCandidate:
    return ExperienceCandidate(
        **({"id": uid(title), "title": title, "city": "Buenos Aires", "price_usd": price} | kw)
    )


PROVIDERS = [
    ProviderCandidate(
        id=uid("hotel"),
        name="Palermo Hotel",
        kind=ProviderKind.HOTEL,
        city="Buenos Aires",
        unit_price_usd=85,
        unit="person/night",
    ),
    ProviderCandidate(
        id=uid("hotel2"),
        name="Pricier Hotel",
        kind=ProviderKind.HOTEL,
        city="Buenos Aires",
        unit_price_usd=140,
        unit="person/night",
    ),
    ProviderCandidate(
        id=uid("bus"),
        name="Bus Co",
        kind=ProviderKind.TRANSPORT,
        city="Buenos Aires",
        unit_price_usd=30,
        unit="person/day",
    ),
    ProviderCandidate(
        id=uid("ref"),
        name="Refs",
        kind=ProviderKind.REFEREE,
        city="Buenos Aires",
        unit_price_usd=6,
        unit="person/match",
    ),
    ProviderCandidate(
        id=uid("venue"),
        name="Venue",
        kind=ProviderKind.VENUE,
        city="Buenos Aires",
        unit_price_usd=12,
        unit="person/session",
    ),
    ProviderCandidate(
        id=uid("rio-hotel"),
        name="Rio Hotel",
        kind=ProviderKind.HOTEL,
        city="Rio de Janeiro",
        unit_price_usd=50,
        unit="person/night",
    ),
]

OPPONENTS = [
    opponent("Belgrano", 7),
    opponent("Sur", 6),
    opponent("Palermo Elite", 8),
    opponent("Too Strong", 9),
    opponent("Too Weak", 5),
    opponent("Men Team", 7, gender=Gender.MEN),
    opponent("Rugby", 7, sport=Sport.RUGBY),
    opponent("U15 only", 7, age_groups=("U15",)),
    opponent("Rio Club", 7, city="Rio de Janeiro"),
]

EXPERIENCES = [
    experience("Bombonera tour", 35),
    experience("Tango night", 55),
    experience("Delta trip", 45),
    experience("Rugby clinic", 20, sports=(Sport.RUGBY,)),
    experience("Maracanã", 40, city="Rio de Janeiro"),
]


def test_arrival_first_departure_last():
    it = plan_itinerary(team(), OPPONENTS, EXPERIENCES, PROVIDERS)
    assert it.items[0].kind is ItemKind.ARRIVAL and it.items[0].day == 1
    assert it.items[-1].kind is ItemKind.DEPARTURE and it.items[-1].day == 10
    assert sum(i.kind is ItemKind.ARRIVAL for i in it.items) == 1
    assert sum(i.kind is ItemKind.DEPARTURE for i in it.items) == 1


def test_eligible_opponents_filters_and_orders_by_level_gap():
    names = [o.name for o in eligible_opponents(team(), OPPONENTS)]
    assert names[0] == "Belgrano"  # exact level first
    assert set(names) == {"Belgrano", "Sur", "Palermo Elite"}


def test_level_gap_is_configurable():
    names = {o.name for o in eligible_opponents(team(max_level_gap=2), OPPONENTS)}
    assert {"Too Strong", "Too Weak"} <= names
    assert {o.name for o in eligible_opponents(team(max_level_gap=0), OPPONENTS)} == {"Belgrano"}


def test_matches_use_each_opponent_once_and_have_referee():
    it = plan_itinerary(team(), OPPONENTS, EXPERIENCES, PROVIDERS)
    matches = [i for i in it.items if i.kind is ItemKind.MATCH]
    assert len(matches) == 3
    assert len({m.opponent_id for m in matches}) == len(matches)
    assert all(m.provider_id == uid("ref") and m.slot is Slot.AFTERNOON for m in matches)


def test_cheapest_hotel_in_city_is_used():
    it = plan_itinerary(team(), OPPONENTS, EXPERIENCES, PROVIDERS)
    assert it.items[0].provider_id == uid("hotel")


def test_experiences_respect_city_and_sport():
    it = plan_itinerary(team(), OPPONENTS, EXPERIENCES, PROVIDERS)
    titles = {i.title for i in it.items if i.kind is ItemKind.EXPERIENCE}
    assert "Rugby clinic" not in titles and "Maracanã" not in titles
    assert titles <= {"Bombonera tour", "Tango night", "Delta trip"}
    exp_ids = [i.experience_id for i in it.items if i.kind is ItemKind.EXPERIENCE]
    assert len(exp_ids) == len(set(exp_ids))


def test_runs_out_of_experiences_gracefully():
    it = plan_itinerary(team(duration_days=14), OPPONENTS, EXPERIENCES[:1], PROVIDERS)
    assert any(i.kind is ItemKind.FREE and i.title == "Free time" for i in it.items)


def test_fewer_opponents_than_target_reduces_matches_with_warning():
    it = plan_itinerary(team(), OPPONENTS[:1], EXPERIENCES, PROVIDERS)
    assert len(it.match_days) == 1
    assert any("1 of 3 matches" in w for w in it.warnings)


def test_no_opponents_still_plans_trip():
    it = plan_itinerary(team(), [], EXPERIENCES, PROVIDERS)
    assert it.match_days == ()
    assert it.items[0].kind is ItemKind.ARRIVAL


def test_missing_providers_warn():
    it = plan_itinerary(team(city="Montevideo"), OPPONENTS, EXPERIENCES, PROVIDERS)
    assert any("hotel" in w for w in it.warnings)
    assert it.items[0].provider_id is None


def test_max_matches_caps_count():
    it = plan_itinerary(team(max_matches=1), OPPONENTS, EXPERIENCES, PROVIDERS)
    assert len(it.match_days) == 1


def test_profile_validation():
    with pytest.raises(ValidationError):
        team(duration_days=2)
    with pytest.raises(ValidationError):
        team(level_score=11)


@pytest.mark.parametrize("days", range(3, 22))
def test_match_count_bounds(days):
    assert 1 <= target_match_count(days) <= 4
    assert all(3 <= d <= days - 1 for d in candidate_match_days(days))


# ── property-style checks over many random inputs ─────────────────────────


def _random_case(rng: random.Random):
    lvl = rng.randint(1, 10)
    t = team(duration_days=rng.randint(3, 21), level_score=lvl)
    opps = [
        opponent(
            f"opp{i}",
            rng.randint(1, 10),
            age_groups=tuple(rng.sample(["U15", "U17", "U19", "college"], 2)),
        )
        for i in range(rng.randint(0, 12))
    ]
    exps = [experience(f"exp{i}", rng.randint(0, 120)) for i in range(rng.randint(0, 8))]
    return t, opps, exps


@pytest.mark.parametrize("seed", range(300))
def test_invariants_hold_for_random_inputs(seed):
    rng = random.Random(seed)  # noqa: S311 - seeded test data
    t, opps, exps = _random_case(rng)
    it = plan_itinerary(t, opps, exps, PROVIDERS)

    days = sorted(it.match_days)
    assert all(b - a >= 2 for a, b in zip(days, days[1:], strict=False)), "consecutive match days"
    assert all(2 < d < t.duration_days for d in days)
    assert len(days) <= 4

    by_id = {o.id: o for o in opps}
    for item in it.items:
        assert 1 <= item.day <= t.duration_days
        if item.kind is ItemKind.MATCH:
            assert item.opponent_id is not None
            o = by_id[item.opponent_id]
            assert abs(o.level_score - t.level_score) <= 1
            assert t.age_group in o.age_groups
    # one item per (day, slot)
    keys = [(i.day, i.slot) for i in it.items]
    assert len(keys) == len(set(keys))
    # every inner day is filled morning + afternoon
    for d in range(2, t.duration_days):
        assert {i.slot for i in it.items_on(d)} == {Slot.MORNING, Slot.AFTERNOON}


@pytest.mark.parametrize("seed", range(100))
def test_deterministic_regardless_of_input_order(seed):
    rng = random.Random(seed)  # noqa: S311 - seeded test data
    t, opps, exps = _random_case(rng)
    a = plan_itinerary(t, opps, exps, PROVIDERS)
    rng.shuffle(opps)
    rng.shuffle(exps)
    providers = PROVIDERS[:]
    rng.shuffle(providers)
    b = plan_itinerary(t, opps, exps, providers)
    assert a == b

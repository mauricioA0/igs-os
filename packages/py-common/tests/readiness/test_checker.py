"""The readiness checker against the shipped rules (2026-10): one test per rule that matters."""

from datetime import date

import pytest

from igs_common.readiness import (
    DocumentInfo,
    ReadinessChecker,
    TravelerInfo,
    TripInfo,
    load_rules,
    parse_rules,
)

TODAY = date(2026, 10, 23)
RIO = TripInfo(
    id="t-rio", country="Brazil", start_date=date(2026, 12, 5), end_date=date(2026, 12, 14)
)
MADRID = TripInfo(
    id="t-mad", country="Spain", start_date=date(2027, 6, 1), end_date=date(2027, 6, 10)
)
BA = TripInfo(
    id="t-ba", country="Argentina", start_date=date(2027, 3, 6), end_date=date(2027, 3, 15)
)

PLAYER = TravelerInfo(id="p1", full_name="Kid One", is_minor=True, birth_year=2010)
COACH = TravelerInfo(id="c1", full_name="Coach", role="staff")


def verified(
    *keys: str, valid_from: date | None = None, valid_until: date | None = None
) -> list[DocumentInfo]:
    """Verified documents; the dates go on the passport only."""
    return [
        DocumentInfo(k, "verified", valid_from, valid_until)
        if k == "passport"
        else DocumentInfo(k, "verified")
        for k in keys
    ]


def person(report: dict, traveler_id: str) -> dict:
    return next(p for p in report["people"] if p["traveler_id"] == traveler_id)


def item(report: dict, traveler_id: str, key: str) -> dict:
    return next(i for i in person(report, traveler_id)["items"] if i["requirement"] == key)


@pytest.fixture
def checker() -> ReadinessChecker:
    return ReadinessChecker(load_rules())


def test_latest_rules_load_and_reference_known_sources() -> None:
    rules = load_rules()
    assert rules.version == "2026-10"
    assert {d.code for d in rules.destinations} == {"AR", "BR", "CR", "ES"}
    assert rules.destination("brasil") is rules.destination("BR")


def test_brazil_minor_needs_evisa_birth_certificate_and_consent(checker: ReadinessChecker) -> None:
    report = checker.check(RIO, [PLAYER, COACH], {}, today=TODAY)
    kid = {i["requirement"]: i for i in person(report, "p1")["items"]}
    adult = {i["requirement"]: i for i in person(report, "c1")["items"]}
    assert {"br_evisa", "birth_certificate", "parental_consent", "passport"} <= set(kid)
    assert kid["br_evisa"]["severity"] == "blocker"
    assert kid["parental_consent"]["severity"] == "blocker"
    assert "birth_certificate" not in adult and "parental_consent" not in adult
    assert adult["br_evisa"]["due_on"] == "2026-10-06"  # T-60
    assert report["ready"] is False


def test_due_dates_turn_overdue(checker: ReadinessChecker) -> None:
    report = checker.check(RIO, [COACH], {}, today=TODAY)
    evisa = item(report, "c1", "br_evisa")
    insurance = item(report, "c1", "travel_insurance")
    assert evisa["overdue"] is True  # due 2026-10-06
    assert insurance["overdue"] is False  # due 2026-11-21
    assert report["next_due_on"] == "2026-11-14"  # emergency contact, T-21
    assert report["overdue_items"] == 2  # e-Visa and passport (T-75)


def test_all_verified_is_ready(checker: ReadinessChecker) -> None:
    docs = {
        "c1": verified(
            "passport", "br_evisa", "travel_insurance", "emergency_contact",
            valid_until=date(2030, 1, 1),
        )
    }  # fmt: skip
    report = checker.check(RIO, [COACH], docs, today=TODAY)
    assert report["ready"] is True
    assert report["travelers_ready"] == 1
    assert report["not_ready"] == []


def test_received_still_needs_review(checker: ReadinessChecker) -> None:
    docs = {"c1": [DocumentInfo("br_evisa", "received")]}
    report = checker.check(RIO, [COACH], docs, today=TODAY)
    assert item(report, "c1", "br_evisa")["state"] == "received"
    assert "br_evisa" in person(report, "c1")["missing"]


def test_passport_expiring_during_trip_is_invalid(checker: ReadinessChecker) -> None:
    docs = {"c1": verified("passport", valid_until=date(2026, 12, 10))}
    passport = item(checker.check(RIO, [COACH], docs, today=TODAY), "c1", "passport")
    assert passport["state"] == "invalid"
    assert "Renew" in passport["warnings"][0]


def test_passport_under_six_months_after_return_only_warns(checker: ReadinessChecker) -> None:
    docs = {"c1": verified("passport", valid_until=date(2027, 3, 1))}
    passport = item(checker.check(RIO, [COACH], docs, today=TODAY), "c1", "passport")
    assert passport["state"] == "ok"
    assert any("6 months" in w for w in passport["warnings"])


def test_spain_passport_three_months_after_and_ten_year_issue(checker: ReadinessChecker) -> None:
    short = {"c1": verified("passport", valid_until=date(2027, 8, 1))}
    assert item(checker.check(MADRID, [COACH], short, today=TODAY), "c1", "passport")["state"] == (
        "invalid"
    )
    old = {"c1": verified("passport", valid_from=date(2017, 5, 1), valid_until=date(2028, 1, 1))}
    passport = item(checker.check(MADRID, [COACH], old, today=TODAY), "c1", "passport")
    assert passport["state"] == "invalid"
    assert any("10 years" in w for w in passport["warnings"])
    ok = {"c1": verified("passport", valid_from=date(2020, 1, 1), valid_until=date(2030, 1, 1))}
    assert item(checker.check(MADRID, [COACH], ok, today=TODAY), "c1", "passport")["state"] == "ok"


def test_etias_is_listed_as_upcoming_not_required(checker: ReadinessChecker) -> None:
    report = checker.check(MADRID, [COACH], {}, today=TODAY)
    keys = [i["requirement"] for i in person(report, "c1")["items"]]
    assert "etias" not in keys
    assert "schengen_funds" in keys
    assert [u["requirement"] for u in report["upcoming_rules"]] == ["etias"]


def test_argentina_under_13_consent_is_a_blocker(checker: ReadinessChecker) -> None:
    young = TravelerInfo(id="y", full_name="Young", is_minor=True, birth_year=2014)  # 12 or 13
    teen = TravelerInfo(id="t", full_name="Teen", is_minor=True, birth_year=2010)  # 16 or 17
    report = checker.check(BA, [young, teen], {}, today=TODAY)
    assert item(report, "y", "parental_consent")["severity"] == "blocker"
    assert item(report, "t", "parental_consent")["severity"] == "required"


def test_both_parents_travelling_waives_consent(checker: ReadinessChecker) -> None:
    docs = {"p1": [DocumentInfo("parental_consent", "not_applicable", note="Both parents travel")]}
    consent = item(checker.check(RIO, [PLAYER], docs, today=TODAY), "p1", "parental_consent")
    assert consent["state"] == "waived"
    assert consent["blocking"] is False


def test_expired_evisa_is_invalid(checker: ReadinessChecker) -> None:
    docs = {"c1": [DocumentInfo("br_evisa", "verified", valid_until=date(2026, 12, 1))]}
    assert item(checker.check(RIO, [COACH], docs, today=TODAY), "c1", "br_evisa")["state"] == (
        "invalid"
    )


def test_unknown_destination_checks_defaults_and_warns(checker: ReadinessChecker) -> None:
    trip = TripInfo(
        id="x", country="Uruguay", start_date=date(2027, 1, 5), end_date=date(2027, 1, 9)
    )
    report = checker.check(trip, [COACH], {}, today=TODAY)
    assert report["trip"]["destination"] is None
    assert "Uruguay" in report["warnings"][0]
    assert {i["requirement"] for i in person(report, "c1")["items"]} == {
        "passport",
        "travel_insurance",
        "emergency_contact",
    }


def test_empty_roster_is_not_ready(checker: ReadinessChecker) -> None:
    report = checker.check(RIO, [], {}, today=TODAY)
    assert report["ready"] is False
    assert "No travelers" in report["warnings"][0]


def test_rules_reject_unknown_requirement_and_source() -> None:
    base = """
version: x
checked_on: 2026-10-23
nationality: US
sources: {s: {title: t, url: u, official: true}}
requirements: {passport: {label: P, kind: passport, due_days_before: 10}}
destinations:
  - code: BR
    names: [Brazil]
    requirements: [{key: %s, severity: blocker, sources: [%s]}]
"""
    parse_rules(base % ("passport", "s"))
    with pytest.raises(ValueError, match="unknown requirement"):
        parse_rules(base % ("visa", "s"))
    with pytest.raises(ValueError, match="unknown source"):
        parse_rules(base % ("passport", "nope"))

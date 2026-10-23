"""Demo dates replay relative to the anchor: structured values and dates written in prose."""

from datetime import date, datetime, timedelta

import pytest

from igs_common.seed.anchor import FIXTURE_ANCHOR, shift_days, shift_text, shift_tree
from igs_common.seed.load import FIXTURES_DIR, _Fixtures, _read


@pytest.mark.parametrize(
    ("text", "shifted"),
    [
        ("enrolls by October 15 — 24 travelers", "enrolls by November 4 — 24 travelers"),
        ("March 6–15, 2027 hotel", "March 26–April 4, 2027 hotel"),
        ("on October 31st.", "on November 20th."),
        ("the Oct 28 budget meeting", "the Nov 17 budget meeting"),
        ("vencían el 15/10, reunión del 28/10", "vencían el 4/11, reunión del 17/11"),
        ("Buenos Aires 6–15/3/2027,", "Buenos Aires 26/3–4/4/2027,"),
        ("6–15 mar 2027 · 24 viajeros", "26 mar–4 abr 2027 · 24 viajeros"),
        ("el 15 de octubre de 2026", "el 4 de noviembre de 2026"),
        ("the July 2026 tour", "the August 2026 tour"),
        ("bloqueo de marzo (31/10)", "bloqueo de abril (20/11)"),
    ],
)
def test_dates_in_text_move_with_the_anchor(text: str, shifted: str) -> None:
    assert shift_text(text, 20) == shifted


@pytest.mark.parametrize(
    "text", ["Rated 9/10, survey 4.7/5", "24/7 bilingual leader", "a 2027 trip"]
)
def test_non_dates_are_left_alone(text: str) -> None:
    assert shift_text(text, 20) == text


def test_structured_dates_shift_and_zero_is_identity() -> None:
    tree = {"d": "2026-10-31", "t": "2026-10-22T07:40:00-03:00", "o": date(2026, 10, 1), "n": 3}
    out = shift_tree(tree, 10)
    assert out["d"] == "2026-11-10" and out["o"] == date(2026, 10, 11) and out["n"] == 3
    assert datetime.fromisoformat(out["t"]).date() == date(2026, 11, 1)
    assert shift_tree(tree, 0) is tree


def test_anchor_comes_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_ANCHOR", "2026-11-01")
    assert shift_days() == 10
    monkeypatch.setenv("DEMO_ANCHOR", FIXTURE_ANCHOR.isoformat())
    assert shift_days() == 0


def test_lakeshore_story_keeps_its_relative_deadlines() -> None:
    """Whatever day the demo is reset, the approval expiry and hotel release stay N days out."""
    raw = _read(FIXTURES_DIR / "sales.yaml")
    later = _Fixtures(FIXTURES_DIR, FIXTURES_DIR, days=45)

    def approval(sales: dict, key: str) -> dict:
        return next(a for a in sales["approvals"] if a["key"] == key)

    before, after = approval(raw, "a-9003"), approval(later.sales, "a-9003")
    delta = datetime.fromisoformat(str(after["expires_at"])) - datetime.fromisoformat(
        str(before["expires_at"])
    )
    assert delta.days == 45
    trip = next(t for t in later.sales["trips"] if t["key"] == "t-2711")
    assert date.fromisoformat(str(trip["start_date"])) == date(2027, 3, 6) + timedelta(days=45)
    # The catalog (seasons, policies) never moves.
    assert later.catalog == _read(FIXTURES_DIR / "catalog.yaml")

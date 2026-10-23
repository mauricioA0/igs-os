from decimal import Decimal

from igs_common.digest import allowed_numbers, build_digest, check_numbers, template_summary

from .helpers import NOW, inputs


def test_numbers_in_facts_including_inside_statements() -> None:
    allowed = allowed_numbers({"amount": 2280, "reason": "24 × US$95", "day": "2026-10-31"})
    assert {Decimal(2280), Decimal(24), Decimal(95), Decimal(2026), Decimal(10), Decimal(31)} <= (
        allowed
    )


def test_both_separator_conventions_are_accepted() -> None:
    allowed = allowed_numbers({"amount": 2280, "price": 2750})
    for text in ("US$2,280", "US$ 2.280", "USD 2750", "2.750 por persona"):
        assert check_numbers(text, allowed).ok, text


def test_invented_numbers_are_rejected() -> None:
    allowed = allowed_numbers({"amount": 2280, "travelers": 24})
    check = check_numbers("Faltan US$2,500 de 24 viajeros, vence en 3 días.", allowed)
    assert not check.ok and check.unknown == ("2,500", "3") and check.checked == 3


def test_ids_links_and_clock_times_do_not_count_as_facts() -> None:
    allowed = allowed_numbers(
        {
            "id": "0199a3f2-7713-7c1e-9d41-2b4a5c6d7e8f",
            "lead_id": "00000000-0000-0000-0000-000000000500",
            "link": "/ops/approvals?id=9003",
            "created_at": "2026-10-19T17:45:00+00:00",
            "generated_at": "2026-10-22T12:00:00+00:00",
        }
    )
    assert check_numbers("7713", allowed).unknown == ("7713",)
    assert check_numbers("9003", allowed).unknown == ("9003",)
    assert check_numbers("500", allowed).unknown == ("500",)
    assert check_numbers("17:45", allowed).unknown == ("17", "45")
    assert check_numbers("19/10", allowed).ok  # the day of a timestamp is a fact


def test_negative_day_offsets_match_their_absolute_value() -> None:
    assert check_numbers("vencido hace 10 días", allowed_numbers({"days": -10})).ok


def test_text_without_numbers_passes() -> None:
    assert check_numbers("Lo primero: llamar a Haines.", frozenset()).ok


def test_the_template_summary_always_passes_its_own_check() -> None:
    facts = build_digest(inputs(), now=NOW)
    summary = template_summary(facts)
    assert check_numbers(summary, allowed_numbers(facts.to_json())).ok, summary


def test_thousands_group_is_never_read_as_a_decimal() -> None:
    # "3,000" must not pass just because 3 is in the facts.
    allowed = allowed_numbers({"open_items": 3})
    assert check_numbers("US$3,000", allowed).unknown == ("3,000",)
    assert check_numbers("3.000", allowed).unknown == ("3.000",)
    assert check_numbers("2,5", allowed_numbers({"x": 2.5})).ok

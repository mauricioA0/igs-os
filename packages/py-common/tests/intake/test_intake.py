"""Lead intake building blocks: form, email parsing, extraction, levels, score, reply, clock."""

from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from igs_common.intake import (
    BusinessCalendar,
    PlanATourForm,
    draft_reply,
    extract,
    extract_with_llm,
    extract_with_rules,
    level_score,
    parse_email,
    parse_window,
    score_inquiry,
)
from igs_common.llm import FakeLLM, Scripted

FIXTURES = Path(__file__).parent / "fixtures"
NY = ZoneInfo("America/New_York")
CAL = BusinessCalendar()


def ny(*args: int) -> datetime:
    return datetime(*args, tzinfo=NY)  # type: ignore[misc]


def mail(name: str):  # noqa: ANN201
    return parse_email((FIXTURES / name).read_bytes())


# ── Form ──────────────────────────────────────────────────────────────────────

FORM = {
    "first_name": "Dana",
    "last_name": "Whitfield",
    "program": "Lakeshore University",
    "role": "Head Coach",
    "email": "DWhitfield@Lakeshore.example ",
    "phone_country_code": "+1",
    "phone": "312 555 0142",
    "travel_window": "Spring break 2027",
    "how_heard": "Returning Customer",
    "message": "Women's soccer, NCAA D3, about 24 players. Thinking Buenos Aires again.",
    "utm_source": "google",
    "landing_page": "/college-soccer-tours",
    "website": "",
}


def test_form_takes_the_site_fields_and_normalizes_email() -> None:
    form = PlanATourForm.model_validate(FORM)
    assert form.email == "dwhitfield@lakeshore.example"
    assert form.full_name == "Dana Whitfield"
    assert form.known_role == "Head Coach"
    assert form.known_how_heard == "Returning Customer"
    assert not form.is_spam
    assert "Target travel window: Spring break 2027" in form.source_text()


def test_form_honeypot_and_unknown_options() -> None:
    bot = PlanATourForm.model_validate({**FORM, "website": "http://spam.example"})
    assert bot.is_spam
    renamed = PlanATourForm.model_validate({**FORM, "role": "Head Coach (Women)"})
    assert renamed.known_role is None and renamed.role == "Head Coach (Women)"


def test_form_rejects_a_missing_email() -> None:
    with pytest.raises(ValidationError):
        PlanATourForm.model_validate({**FORM, "email": "not-an-email"})


def test_form_dedupe_key_is_stable_and_content_bound() -> None:
    a = PlanATourForm.model_validate(FORM)
    b = PlanATourForm.model_validate({**FORM, "email": "dwhitfield@lakeshore.example"})
    c = PlanATourForm.model_validate({**FORM, "message": "Different words"})
    assert a.dedupe_key() == b.dedupe_key() != c.dedupe_key()


# ── Email ─────────────────────────────────────────────────────────────────────


def test_gmail_inline_forward_finds_the_coach_and_keeps_the_note_apart() -> None:
    m = mail("gmail_forward.eml")
    assert (m.sender_name, m.sender_email) == (
        "Priya Natarajan",
        "pnatarajan@harborstate.example.edu",
    )
    assert m.forwarded and m.forwarded_by == "sortega@infinityglobalsports.example"
    assert m.subject == "Spring 2027 tour inquiry - Harbor State WSOC"
    assert "showcase. Can someone" in m.forwarder_note
    assert "Can someone pick this up" not in m.text
    assert "Head Coach, Women's Soccer" not in m.text  # signature trimmed
    assert m.received_at == datetime(2026, 10, 22, 14, 12, 3, tzinfo=ZoneInfo("America/New_York"))


def test_apple_mail_forward() -> None:
    m = mail("apple_forward.eml")
    assert m.sender_email == "aruiz@lakeshore.example"
    assert m.forwarded_by == "rhaines@lakeshore.example"
    assert m.text.startswith("Robert, could IGS do something")


def test_forward_as_attachment() -> None:
    m = mail("outlook_attached.eml")
    assert (m.sender_name, m.sender_email) == ("Tom Becker", "tbecker@pinevalley.example")
    assert m.forwarded and m.subject == "Rugby tour"
    assert m.forwarder_note.startswith("See attached")
    assert (
        m.dedupe_key()
        != parse_email(b"Message-ID: <inner-0003@pinevalley.example>\n\n").dedupe_key()
    )


def test_reply_drops_quoted_history_and_our_own_subject() -> None:
    m = mail("direct_reply.eml")
    assert m.is_reply and m.in_reply_to == "<draft-0001@infinityglobalsports.example>"
    assert ">" not in m.text and "wrote:" not in m.text
    assert "Lakeshore University tour" not in m.source_text()


def test_html_only_and_encoded_subject() -> None:
    m = mail("html_only.eml")
    assert m.subject == "Basketball gira — 2027"
    assert "<b>" not in m.text and "men's basketball" in m.text


def test_form_notification_uses_reply_to() -> None:
    m = mail("form_notification.eml")
    assert (m.sender_name, m.sender_email) == ("Marcus Hale", "mhale@riversidefc.example")


def test_message_without_id_gets_a_content_hash() -> None:
    raw = b"From: a@b.example\nSubject: hi\n\nhello"
    assert parse_email(raw).dedupe_key() == parse_email(raw).dedupe_key()


# ── Extraction ────────────────────────────────────────────────────────────────


def test_rules_extract_a_complete_inquiry() -> None:
    e = extract_with_rules(mail("gmail_forward.eml").source_text())
    v = e.values
    assert (v["sport"], v["gender"], v["destination_country"]) == ("soccer", "women", "Argentina")
    assert (v["level_label"], v["level_score"], v["age_group"]) == ("NCAA D2", 7, "College")
    assert (v["group_size"], v["duration_days"], v["budget_per_person_usd"]) == (26, 10, 3200)
    assert (v["travel_start"], v["travel_start_precision"]) == (date(2027, 3, 14), "day")
    assert e.missing == []
    assert e.evidence["group_size"] == "about 26 players"


def test_rules_leave_unknowns_null() -> None:
    e = extract_with_rules("Hi, we'd love to hear more about your tours. Spring break 2027?")
    assert all(e.values[name] is None for name in e.missing)
    assert e.values["travel_start"] is None  # a season is not a date
    assert set(e.missing) == {
        "sport",
        "gender",
        "age_group",
        "level_score",
        "group_size",
        "destination_country",
        "travel_start",
        "duration_days",
    }


def test_rules_month_is_flagged_and_nights_count_as_days() -> None:
    e = extract_with_rules("Men's rugby, June 2027, 8 nights, 30 players to Argentina")
    assert (e.values["travel_start"], e.values["travel_start_precision"]) == (
        date(2027, 6, 1),
        "month",
    )
    assert e.values["duration_days"] == 9


def test_rules_do_not_mistake_a_surname_for_division_one() -> None:
    e = extract_with_rules("Diego Di Marco recommended you to our soccer club")
    assert e.values["level_score"] is None


SOURCE = "Program: Brookfield University\n\nWomen's soccer, D1. Around 28 travelers to Rio."


async def test_llm_values_need_verbatim_evidence() -> None:
    llm = FakeLLM(
        [
            Scripted(
                json={
                    "sport": "soccer",
                    "gender": "women",
                    "age_group": "college",
                    "level_label": "D1",
                    "group_size": 28,
                    "destination_country": "Brazil",
                    "travel_date": "2027-03-10",  # invented: nothing in the text
                    "travel_month": None,
                    "duration_days": 10,  # quoted, but the quote isn't in the text
                    "budget_per_person_usd": None,
                    "goals": None,
                    "evidence": [
                        {"field": "sport", "quote": "Women's soccer"},
                        {"field": "gender", "quote": "Women’s soccer"},  # curly quote is fine
                        {"field": "age_group", "quote": "Brookfield University"},
                        {"field": "level_label", "quote": "D1"},
                        {"field": "group_size", "quote": "Around 28 travelers"},
                        {"field": "destination_country", "quote": "to Rio"},
                        {"field": "duration_days", "quote": "for ten days"},
                    ],
                }
            )
        ]
    )
    e = await extract_with_llm(llm, SOURCE)
    assert e.method == "llm"
    assert e.values["sport"] == "soccer" and e.values["gender"] == "women"
    assert e.values["level_score"] == 8 and e.values["age_group"] == "College"
    assert e.values["group_size"] == 28 and e.values["destination_country"] == "Brazil"
    assert e.values["travel_start"] is None and e.values["duration_days"] is None
    assert e.rejected == {
        "travel_date": "no evidence quote",
        "duration_days": "evidence is not a verbatim span of the inquiry",
    }
    assert sorted(e.missing) == ["duration_days", "travel_start"]


async def test_extract_falls_back_to_rules_when_the_model_fails() -> None:
    llm = FakeLLM([Scripted(text="not json at all")])
    e = await extract(llm, SOURCE)
    assert e.method == "rules"
    assert e.values["destination_country"] == "Brazil"


def test_merge_fills_gaps_and_never_erases() -> None:
    first = extract_with_rules("Women's soccer, 24 players")
    second = extract_with_rules("Argentina works best, 9 days")
    merged = second.merged_over(first.values)
    assert merged["sport"] == "soccer" and merged["group_size"] == 24
    assert merged["destination_country"] == "Argentina" and merged["duration_days"] == 9


# ── Levels and windows ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("label", "score"),
    [
        ("NCAA D1", 8),
        ("Division I", 8),
        ("MLS Next", 8),
        ("ECNL", 7),
        ("Div. 2", 7),
        ("DIII", 6),
        ("NAIA", 6),
        ("NJCAA", 5),
        ("varsity", 5),
        ("JV", 4),
        ("Di Marco", None),
        ("", None),
    ],
)
def test_level_score(label: str, score: int | None) -> None:
    assert level_score(label) == score


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Spring break 2027", (date(2027, 3, 1), date(2027, 4, 15))),
        ("Summer 2026", (date(2026, 6, 1), date(2026, 8, 31))),
        ("Winter break '27", (date(2027, 12, 15), date(2028, 1, 15))),
        ("March 2027", (date(2027, 3, 1), date(2027, 3, 31))),
        ("2027", (date(2027, 1, 1), date(2027, 12, 31))),
        ("as soon as possible", None),
    ],
)
def test_parse_window(text: str, expected: tuple[date, date] | None) -> None:
    assert parse_window(text) == expected


# ── Business-day clock ────────────────────────────────────────────────────────


def test_due_inside_working_hours_is_same_time_next_business_day() -> None:
    assert CAL.due(ny(2026, 10, 19, 15, 0)) == ny(2026, 10, 20, 15, 0).astimezone(UTC)


def test_due_after_hours_and_weekends_starts_at_next_opening() -> None:
    friday_night = ny(2026, 10, 23, 20, 0)
    assert CAL.due(friday_night) == ny(2026, 10, 26, 18, 0).astimezone(UTC)
    early_monday = ny(2026, 10, 26, 7, 30)
    assert CAL.due(early_monday) == ny(2026, 10, 26, 18, 0).astimezone(UTC)


def test_due_skips_holidays() -> None:
    # Wednesday before Thanksgiving (Nov 26, 2026), 17:00 → 1 h Wed + 8 h Friday.
    assert CAL.due(ny(2026, 11, 25, 17, 0)) == ny(2026, 11, 27, 17, 0).astimezone(UTC)


def test_sla_states() -> None:
    due = ny(2026, 10, 20, 15, 0)
    assert CAL.state(due, ny(2026, 10, 20, 9, 0)) == "on_track"
    assert CAL.state(due, ny(2026, 10, 20, 13, 0)) == "at_risk"
    assert CAL.state(due, ny(2026, 10, 20, 15, 1)) == "breached"
    assert CAL.state(due, ny(2026, 10, 21, 9, 0), ny(2026, 10, 20, 11, 0)) == "met"
    assert CAL.state(due, ny(2026, 10, 21, 9, 0), ny(2026, 10, 21, 8, 0)) == "missed"
    # Overnight doesn't count: Monday 17:30 with Tuesday 10:00 due is 1.5 working hours left.
    assert CAL.business_hours_between(ny(2026, 10, 19, 17, 30), ny(2026, 10, 20, 10, 0)) == 1.5


def test_call_slots_are_business_hours_and_leave_time_to_approve() -> None:
    slots = CAL.call_slots(ny(2026, 10, 23, 15, 0))  # Friday 15:00 + 4 working h = Monday 10:00
    local = [s.astimezone(NY) for s in slots]
    assert [(s.weekday(), s.hour) for s in local] == [(0, 10), (0, 14), (0, 16)]


# ── Score and reply ───────────────────────────────────────────────────────────


def test_score_explains_every_point() -> None:
    e = extract_with_rules(mail("gmail_forward.eml").source_text())
    score = score_inquiry(
        values=e.values,
        relationship="new",
        role="Head Coach",
        email="pnatarajan@harborstate.example.edu",
        travel_window=None,
        today=date(2026, 10, 22),
        missing=e.missing,
    )
    reasons = {r.reason: r.points for r in score.reasons}
    assert reasons["Escribe el head coach"] == 10
    assert reasons["Viaja en 5 meses: ajustado pero posible"] == 5
    assert reasons["26 viajeros: tamaño típico de gira"] == 10
    assert reasons["Mail institucional (.edu)"] == 5
    assert reasons["Ya sabemos 8 de 8 datos para cotizar"] == 8
    assert score.value == 30 + sum(reasons.values())


def test_score_rewards_returning_customers_and_is_bounded() -> None:
    low = score_inquiry(
        values={"travel_start": date(2026, 11, 1), "group_size": 6},
        relationship="new",
        role="Other",
        email="x@gmail.com",
        travel_window=None,
        today=date(2026, 10, 22),
        missing=["a"] * 8,
    )
    high = score_inquiry(
        values={},
        relationship="returning_customer",
        role="Athletic Director",
        email="ad@school.example.edu",
        travel_window=(date(2027, 12, 15), date(2028, 1, 15)),
        today=date(2026, 10, 22),
        missing=[],
    )
    assert 0 <= low.value < 30 < high.value <= 100
    assert any("ya viajó" in r.reason for r in high.reasons)


def test_reply_asks_only_for_what_is_missing() -> None:
    slots = CAL.call_slots(ny(2026, 10, 22, 11, 0))
    reply = draft_reply(
        first_name="Marcus",
        email="mhale@riversidefc.example",
        program="Riverside FC Academy",
        values={"sport": "soccer", "gender": "men", "destination_country": "Argentina"},
        missing=["travel_start", "duration_days", "group_size"],
        relationship="returning_customer",
        call_slots=slots,
        slot_tz="America/New_York",
    )
    assert reply.body.startswith("Hi Marcus,")
    assert "Great to hear from you again" in reply.body
    assert "(men's soccer, Argentina)" in reply.body
    assert len(reply.questions) == 2
    assert "Roughly how many travelers" in reply.body and "travel dates" in reply.body
    assert "competitive level" not in reply.body
    assert "Eastern Time" in reply.body and "Thu Oct 22, 4:00 PM" in reply.body
    assert "$" not in reply.body  # never a price
    assert reply.action_params() == {
        "to": "mhale@riversidefc.example",
        "subject": "Your Riverside FC Academy tour with Infinity Global Sports",
        "body": reply.body,
    }


def test_reply_to_an_email_keeps_the_thread() -> None:
    reply = draft_reply(
        first_name="Tom",
        email="tbecker@pinevalley.example",
        program="Pine Valley College",
        values={},
        missing=[],
        relationship="new",
        call_slots=[],
        slot_tz="America/New_York",
        in_reply_to_subject="Rugby tour",
    )
    assert reply.subject == "Re: Rugby tour"
    assert "we'll send them shortly" in reply.body

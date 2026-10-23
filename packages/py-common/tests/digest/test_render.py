from dataclasses import replace
from datetime import timedelta

from igs_common.digest import Phrased, build_digest, render_html, render_json, render_text

from .helpers import APPROVAL, NOW, TODAY, inputs, trip_input

PHRASED = Phrased("Lo primero: Lakeshore.", "llm", model="fake-model")


def facts():  # type: ignore[no-untyped-def]
    late = trip_input(start_date=TODAY + timedelta(days=100))
    return build_digest(inputs(trips=(late,)), now=NOW)


def test_html_is_inline_styled_dark_and_has_no_images_or_external_assets() -> None:
    html = render_html(facts(), PHRASED, base_url="https://ops.example")
    assert html.startswith("<!doctype html>") and "background:#0D0D0D" in html
    assert "<img" not in html and "<link" not in html and "<script" not in html
    assert "<style" not in html  # email clients drop it: everything is inline
    assert "Hoy en</span><br>" in html  # two-tone headline
    assert f'href="https://ops.example/ops/approvals?id={APPROVAL.id}"' in html
    assert "US$ 69.360" in html and "vencido hace 10 días" in html


def test_html_escapes_record_text() -> None:
    evil = replace(APPROVAL, title='<script>alert("x")</script>')
    html = render_html(build_digest(inputs(approvals=(evil,)), now=NOW), PHRASED)
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_text_lists_every_section_with_absolute_links() -> None:
    text = render_text(facts(), PHRASED, base_url="https://ops.example")
    for heading in ("RIESGOS", "PAGOS", "APROBACIONES (1)", "SALIDAS EN 14 DÍAS", "LEADS SIN"):
        assert heading in text
    assert "jueves 22 de octubre" in text
    assert "https://ops.example/ops/leads?id=" in text
    assert "se verificó" in text  # the footer says the opening was checked


def test_json_carries_summary_provenance() -> None:
    data = render_json(facts(), PHRASED)
    assert data["summary_source"] == "llm" and data["summary_model"] == "fake-model"
    assert data["facts"]["counts"]["approvals_pending"] == 1

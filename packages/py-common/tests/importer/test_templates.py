"""The committed templates match the specs and import cleanly."""

from pathlib import Path

from igs_common.importer.mapping import match_headers
from igs_common.importer.parse import read_file
from igs_common.importer.schema import APPLY_ORDER, SPECS
from igs_common.importer.templates import csv_template, xlsx_template
from igs_common.importer.validate import validate_sheet

TEMPLATES = Path(__file__).resolve().parents[4] / "docs" / "import" / "templates"


def test_committed_csv_templates_are_in_sync() -> None:
    for entity in APPLY_ORDER:
        committed = (TEMPLATES / f"{entity.value}.csv").read_text(encoding="utf-8")
        assert committed == csv_template(entity), f"run: uv run igs-import templates {TEMPLATES}"


def test_template_examples_validate() -> None:
    sheets = read_file(xlsx_template(), "igs-os-import.xlsx")
    by_name = {s.name: s for s in sheets}
    assert by_name["README"].entity is None
    for entity in APPLY_ORDER:
        sheet = by_name[entity.value]
        spec = SPECS[entity]
        vs = validate_sheet(spec, sheet, match_headers(spec, sheet.headers), date_order=None)
        assert [i for i in vs.issues if i.level == "error"] == [], entity
        assert len(vs.records) == 1

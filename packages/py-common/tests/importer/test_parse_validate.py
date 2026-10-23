"""Parsing, header matching and cell coercion — no database."""

import io
from datetime import date, datetime

import pytest
from openpyxl import Workbook

from igs_common.importer.mapping import column_shape, match_headers
from igs_common.importer.parse import ImportFileError, detect_entity, normalize, read_file
from igs_common.importer.schema import SPECS, Entity
from igs_common.importer.validate import CellError, coerce, validate_sheet


def _xlsx(sheets: dict[str, list[list[object]]]) -> bytes:
    wb = Workbook()
    for ws in list(wb.worksheets):
        wb.remove(ws)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_normalize_and_detect_entity() -> None:
    assert normalize(" Fecha de Inicio ") == "fecha_de_inicio"
    assert detect_entity("Clientes 2026.csv") is Entity.ACCOUNTS
    assert detect_entity("Pagos") is Entity.PAYMENTS
    assert detect_entity("roster") is Entity.TRAVELERS
    assert detect_entity("Notas") is None


def test_csv_semicolons_latin1_and_title_rows() -> None:
    data = "Listado de giras;;\n;;\nCódigo;Título;Ciudad\nIGS-1;Gira;Córdoba\n".encode("latin-1")
    [sheet] = read_file(data, "viajes.csv")
    assert sheet.entity is Entity.TRIPS
    assert sheet.headers == ["Código", "Título", "Ciudad"]
    assert sheet.rows == [(4, ["IGS-1", "Gira", "Córdoba"])]


def test_xlsx_keeps_native_dates_and_skips_blank_rows() -> None:
    data = _xlsx(
        {
            "Trips": [
                ["code", "start_date"],
                ["IGS-9", datetime(2027, 3, 12)],
                [None, None],
                ["IGS-10", "2027-04-01"],
            ]
        }
    )
    [sheet] = read_file(data, "book.xlsx")
    assert sheet.entity is Entity.TRIPS
    assert [r[0] for r in sheet.rows] == [2, 4]
    assert sheet.rows[0][1][1] == datetime(2027, 3, 12)


def test_unsupported_and_broken_files() -> None:
    with pytest.raises(ImportFileError, match="unsupported"):
        read_file(b"x", "data.pdf")
    with pytest.raises(ImportFileError, match="readable"):
        read_file(b"not a zip", "data.xlsx")


def test_aliases_map_spanish_headers_and_forbidden_columns_are_never_mapped() -> None:
    spec = SPECS[Entity.TRAVELERS]
    m = match_headers(spec, ["Viaje", "Nombre", "Rol", "Menor", "Pasaporte", "Fecha de nacimiento"])
    assert [c.field for c in m.columns] == [
        "trip_code",
        "full_name",
        "role",
        "is_minor",
        None,
        None,
    ]
    assert [c.reason for c in m.columns][-2:] == ["forbidden", "forbidden"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("US$ 2,280", 2280), ("2.280", 2280), ("2280.00", 2280), ("USD 2.280,50", 2280), (95, 95)],
)
def test_money(raw: str | int, expected: int) -> None:
    assert coerce(SPECS[Entity.PAYMENTS].field("amount_usd"), raw, date_order=None) == expected


def test_dates_are_never_guessed() -> None:
    f = SPECS[Entity.TRIPS].field("start_date")
    assert coerce(f, "2027-03-12", date_order=None) == date(2027, 3, 12)
    assert coerce(f, "25/03/2027", date_order=None) == date(2027, 3, 25)
    assert coerce(f, 46458, date_order=None) == date(2027, 3, 12)  # Excel serial
    with pytest.raises(CellError, match="day/month or month/day"):
        coerce(f, "03/04/2027", date_order=None)
    assert coerce(f, "03/04/2027", date_order="dmy") == date(2027, 4, 3)
    assert coerce(f, "03/04/2027", date_order="mdy") == date(2027, 3, 4)


def test_enum_value_aliases() -> None:
    f = SPECS[Entity.ACCOUNTS].field("kind")
    assert coerce(f, "Universidad", date_order=None) == "university"
    with pytest.raises(CellError, match="one of"):
        coerce(f, "Spaceship", date_order=None)


def test_validation_reports_rows_duplicates_and_minor_contacts() -> None:
    data = (
        b"trip_code,full_name,role,is_minor,email\n"
        b"IGS-1,Ana Paz,jugadora,si,ana@example.com\n"
        b"IGS-1,Ana Paz,jugadora,si,\n"
        b"IGS-1,Coach Bo,staff,no,bo@example.com\n"
        b"IGS-1,Coach Bo,player,no,bo@example.com\n"
        b"IGS-1,,player,no,\n"
    )
    [sheet] = read_file(data, "roster.csv")
    spec = SPECS[Entity.TRAVELERS]
    vs = validate_sheet(spec, sheet, match_headers(spec, sheet.headers), date_order=None)
    codes = [(i.row, i.code) for i in vs.issues]
    assert (2, "minor-contact-dropped") in codes
    assert (3, "duplicate-row") in codes  # same as row 2 once the minor's email is dropped
    assert (5, "conflicting-duplicate") in codes
    assert (6, "required") in codes
    assert [r.values["full_name"] for r in vs.records] == ["Ana Paz", "Coach Bo"]
    assert "email" not in vs.records[0].values


def test_missing_required_column_stops_the_sheet() -> None:
    [sheet] = read_file(b"name,country\nX,USA\n", "accounts.csv")
    spec = SPECS[Entity.ACCOUNTS]
    vs = validate_sheet(spec, sheet, match_headers(spec, sheet.headers), date_order=None)
    assert [i.code for i in vs.issues] == ["missing-column"]
    assert vs.records == []


def test_column_shape_never_leaks_values() -> None:
    shape = column_shape(["jamie@example.com", "pat@example.com"])
    assert "email-like" in shape and "jamie" not in shape
    assert column_shape(["Jamie Rivera"]).startswith("short text")

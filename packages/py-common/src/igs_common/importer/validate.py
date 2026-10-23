"""Turn mapped cells into typed records, with one `Issue` per problem.

Empty cells mean "not provided" (an update never blanks a stored value). Nothing is guessed:
an ambiguous date like 03/04/2027 is an error unless the caller says how dates are written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from igs_common.importer.mapping import SheetMapping
from igs_common.importer.parse import Cell, Sheet, normalize
from igs_common.importer.schema import EntitySpec, FieldSpec, FieldType

DateOrder = Literal["dmy", "mdy"]
Level = Literal["error", "warning"]

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TRUE = {"yes", "y", "si", "s", "true", "1", "x", "verdadero"}
_FALSE = {"no", "n", "false", "0", "falso"}


@dataclass(frozen=True)
class Issue:
    level: Level
    sheet: str
    row: int | None
    column: str | None
    code: str
    message: str


@dataclass
class Record:
    sheet: str
    row: int
    values: dict[str, Any]
    key: tuple[str, ...] = ()


@dataclass
class ValidatedSheet:
    spec: EntitySpec
    sheet: Sheet
    mapping: SheetMapping
    records: list[Record] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


class CellError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def coerce(spec: FieldSpec, cell: Cell, *, date_order: DateOrder | None) -> Any:
    if cell is None or (isinstance(cell, str) and not cell.strip()):
        return None
    match spec.type:
        case FieldType.TEXT:
            return _text(cell)
        case FieldType.EMAIL:
            value = _text(cell).lower()
            if not _EMAIL.match(value):
                raise CellError("invalid-email", f"{value!r} is not an email address")
            return value
        case FieldType.INT:
            return _int(cell)
        case FieldType.MONEY:
            return _money(cell)
        case FieldType.DATE:
            return _date(cell, date_order)
        case FieldType.BOOL:
            return _bool(cell)
        case FieldType.ENUM:
            return _enum(spec, cell)
        case FieldType.LIST:
            return [p.strip() for p in re.split(r"[;,\n]", _text(cell)) if p.strip()]
    raise AssertionError(spec.type)  # pragma: no cover


def _text(cell: Cell) -> str:
    if isinstance(cell, float) and cell.is_integer():
        return str(int(cell))  # "2711.0" from Excel numeric codes
    return " ".join(str(cell).split())


def _int(cell: Cell) -> int:
    if isinstance(cell, bool):
        raise CellError("invalid-number", "expected a whole number")
    if isinstance(cell, int):
        return cell
    if isinstance(cell, float) and cell.is_integer():
        return int(cell)
    text = _text(cell)
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    raise CellError("invalid-number", f"{text!r} is not a whole number")


def _money(cell: Cell) -> int:
    """Whole dollars. Accepts 'US$ 2,280', '2.280', '2280.00', 'USD 2.280,50' (rounded)."""
    if isinstance(cell, bool):
        raise CellError("invalid-amount", "expected an amount")
    if isinstance(cell, (int, float)):
        amount = Decimal(str(cell))
    else:
        text = re.sub(r"(?i)u\$s|us\$|usd|\$|\s", "", str(cell))
        if not re.fullmatch(r"-?[\d.,]+", text or "x"):
            raise CellError("invalid-amount", f"{cell!r} is not an amount in USD")
        # The last separator followed by exactly 1–2 digits is the decimal point.
        m = re.fullmatch(r"(-?[\d.,]*?)[.,](\d{1,2})", text)
        whole, cents = (m.group(1), m.group(2)) if m else (text, "0")
        whole = re.sub(r"[.,]", "", whole)
        try:
            amount = Decimal(f"{whole or 0}.{cents}")
        except InvalidOperation:
            raise CellError("invalid-amount", f"{cell!r} is not an amount in USD") from None
    if amount < 0:
        raise CellError("invalid-amount", "amounts can't be negative")
    return int(amount.quantize(Decimal(1)))


def _date(cell: Cell, order: DateOrder | None) -> date:
    if isinstance(cell, datetime):
        return cell.date()
    if isinstance(cell, date):
        return cell
    if isinstance(cell, (int, float)) and not isinstance(cell, bool) and 20000 < cell < 80000:
        return date(1899, 12, 30) + timedelta(days=int(cell))  # Excel serial date
    text = _text(cell)
    if m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T].*)?", text):
        y, mo, d = (int(g) for g in m.groups())
        return _make(y, mo, d, text)
    if m := re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", text):
        a, b, y = (int(g) for g in m.groups())
        y = y + 2000 if y < 100 else y
        if a > 12 and b <= 12:
            return _make(y, b, a, text)
        if b > 12 and a <= 12:
            return _make(y, a, b, text)
        if a == b:
            return _make(y, a, b, text)
        if order is None:
            raise CellError(
                "ambiguous-date",
                f"{text!r} could be day/month or month/day; re-run saying which (date_order)",
            )
        return _make(y, b, a, text) if order == "dmy" else _make(y, a, b, text)
    raise CellError("invalid-date", f"{text!r} is not a date (use YYYY-MM-DD)")


def _make(y: int, m: int, d: int, text: str) -> date:
    try:
        return date(y, m, d)
    except ValueError:
        raise CellError("invalid-date", f"{text!r} is not a valid date") from None


def _bool(cell: Cell) -> bool:
    if isinstance(cell, bool):
        return cell
    text = normalize(_text(cell))
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise CellError("invalid-boolean", f"{cell!r}: use yes or no")


def _enum(spec: FieldSpec, cell: Cell) -> str:
    text = normalize(_text(cell))
    if text in spec.choices:
        return text
    if text in spec.value_aliases:
        return spec.value_aliases[text]
    raise CellError("invalid-choice", f"{_text(cell)!r} is not one of: {', '.join(spec.choices)}")


def record_key(spec: EntitySpec, values: dict[str, Any]) -> tuple[str, ...]:
    """Case-insensitive natural key. Stakeholders: account + email, or account + name."""
    if spec.entity.value == "stakeholders":
        who = values.get("email") or values.get("name") or ""
        return (str(values.get("account_name", "")).casefold(), str(who).casefold())
    return tuple(str(values.get(k, "")).casefold() for k in spec.key)


def validate_sheet(
    spec: EntitySpec, sheet: Sheet, mapping: SheetMapping, *, date_order: DateOrder | None
) -> ValidatedSheet:
    out = ValidatedSheet(spec=spec, sheet=sheet, mapping=mapping)
    index = mapping.index_of()
    for col in mapping.columns:
        if col.reason == "forbidden":
            out.issues.append(
                Issue(
                    "warning",
                    sheet.name,
                    None,
                    col.header,
                    "column-not-stored",
                    f"'{col.header}' is personal data IGS OS doesn't keep; the column is ignored",
                )
            )
        elif col.field is None and col.header:
            out.issues.append(
                Issue(
                    "warning",
                    sheet.name,
                    None,
                    col.header,
                    "unmapped-column",
                    f"'{col.header}' doesn't match any field and is ignored",
                )
            )
    missing = [f.name for f in spec.fields if f.required and f.name not in index]
    for name in missing:
        out.issues.append(
            Issue(
                "error",
                sheet.name,
                None,
                name,
                "missing-column",
                f"required column '{name}' not found (headers: {', '.join(sheet.headers)})",
            )
        )
    if missing:
        return out

    seen: dict[tuple[str, ...], Record] = {}
    for row_no, cells in sheet.rows:
        values: dict[str, Any] = {}
        row_ok = True
        for f in spec.fields:
            if f.name not in index:
                continue
            header = mapping.columns[index[f.name]].header
            try:
                value = coerce(f, cells[index[f.name]], date_order=date_order)
            except CellError as exc:
                out.issues.append(Issue("error", sheet.name, row_no, header, exc.code, str(exc)))
                row_ok = False
                continue
            if value is None and f.required:
                out.issues.append(
                    Issue("error", sheet.name, row_no, header, "required", f"'{f.name}' is empty")
                )
                row_ok = False
            elif value is not None:
                values[f.name] = value
        if not row_ok:
            continue
        row_ok = _row_rules(spec, values, out, sheet.name, row_no)
        if not row_ok:
            continue
        rec = Record(sheet.name, row_no, values, record_key(spec, values))
        prior = seen.get(rec.key)
        if prior is None:
            seen[rec.key] = rec
            out.records.append(rec)
        elif prior.values == rec.values:
            out.issues.append(
                Issue(
                    "warning",
                    sheet.name,
                    row_no,
                    None,
                    "duplicate-row",
                    f"same as row {prior.row}; skipped",
                )
            )
        else:
            out.issues.append(
                Issue(
                    "error",
                    sheet.name,
                    row_no,
                    None,
                    "conflicting-duplicate",
                    f"same {'/'.join(spec.key)} as row {prior.row} but different values",
                )
            )
    return out


def _row_rules(
    spec: EntitySpec, values: dict[str, Any], out: ValidatedSheet, sheet: str, row: int
) -> bool:
    entity = spec.entity.value
    if entity == "trips":
        start, end = values.get("start_date"), values.get("end_date")
        if start and end and end < start:
            out.issues.append(
                Issue("error", sheet, row, "end_date", "dates-order", "ends before it starts")
            )
            return False
        if values.get("travelers") is not None and values["travelers"] <= 0:
            out.issues.append(
                Issue("error", sheet, row, "travelers", "invalid-number", "must be > 0")
            )
            return False
    if entity == "stakeholders" and "influence" in values and not 1 <= values["influence"] <= 5:
        out.issues.append(
            Issue("error", sheet, row, "influence", "out-of-range", "influence goes from 1 to 5")
        )
        return False
    if entity == "travelers":
        year = values.get("birth_year")
        if year is not None and not 1900 <= year <= 2100:
            out.issues.append(
                Issue("error", sheet, row, "birth_year", "out-of-range", f"{year} is not a year")
            )
            return False
        if values.get("is_minor") and (values.get("email") or values.get("phone")):
            values.pop("email", None)
            values.pop("phone", None)
            out.issues.append(
                Issue(
                    "warning",
                    sheet,
                    row,
                    None,
                    "minor-contact-dropped",
                    "minors don't get their own email/phone in IGS OS; contact the adults",
                )
            )
    return True

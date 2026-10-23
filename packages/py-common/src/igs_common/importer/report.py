"""The import report: what would change (dry run) or what changed, row by row."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Action = Literal["create", "update", "unchanged"]


class IssueOut(BaseModel):
    level: Literal["error", "warning"]
    sheet: str
    row: int | None = None
    column: str | None = None
    code: str
    message: str


class ColumnOut(BaseModel):
    header: str
    field: str | None
    source: Literal["exact", "alias", "llm"] | None = None
    confidence: float = 1.0
    reason: str | None = None


class SheetOut(BaseModel):
    name: str
    entity: str | None
    rows: int
    columns: list[ColumnOut]


class ChangeOut(BaseModel):
    entity: str
    action: Action
    key: str = Field(description="Human label of the natural key, e.g. 'IGS-2711'.")
    sheet: str
    row: int
    id: str | None = None
    # field → [before, after]; for creates, before is null.
    changes: dict[str, list[Any]] = Field(default_factory=dict)


class Counts(BaseModel):
    create: int = 0
    update: int = 0
    unchanged: int = 0


class ImportReport(BaseModel):
    dry_run: bool
    applied: bool = Field(description="True only when the changes were written.")
    filename: str
    sheets: list[SheetOut]
    summary: dict[str, Counts]
    changes: list[ChangeOut]
    issues: list[IssueOut]

    @property
    def errors(self) -> list[IssueOut]:
        return [i for i in self.issues if i.level == "error"]

    def render_text(self, *, max_changes: int = 200) -> str:
        """Plain-text report for the CLI."""
        mode = "DRY RUN — nothing was written" if self.dry_run else "APPLIED"
        if not self.dry_run and not self.applied:
            mode = "NOT APPLIED — fix the errors and re-run"
        lines = [f"Import of {self.filename}: {mode}", ""]
        for s in self.sheets:
            mapped = ", ".join(
                f"{c.header}→{c.field}"
                + (f" (llm {c.confidence:.2f})" if c.source == "llm" else "")
                for c in s.columns
                if c.field
            )
            lines.append(f"  sheet '{s.name}' as {s.entity or '?'}: {s.rows} rows; {mapped}")
        lines.append("")
        for entity, c in self.summary.items():
            lines.append(
                f"  {entity:<13} create {c.create:>4}  update {c.update:>4}  "
                f"unchanged {c.unchanged:>4}"
            )
        shown = [c for c in self.changes if c.action != "unchanged"][:max_changes]
        if shown:
            lines.append("")
        for ch in shown:
            fields = ", ".join(
                f"{k}: {_fmt(v[0])} → {_fmt(v[1])}" if ch.action == "update" else k
                for k, v in ch.changes.items()
            )
            lines.append(f"  {ch.action:<7} {ch.entity}/{ch.key} ({ch.sheet}:{ch.row}) {fields}")
        if self.issues:
            lines.append("")
        for i in self.issues:
            where = (
                f"{i.sheet}"
                + (f":{i.row}" if i.row else "")
                + (f" [{i.column}]" if i.column else "")
            )
            lines.append(f"  {i.level.upper():<7} {where}: {i.message}")
        return "\n".join(lines)


def _fmt(value: Any) -> str:
    return "∅" if value is None else str(value)

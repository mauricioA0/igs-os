"""One call for the CLI and the API: file bytes in, `ImportReport` out."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.db.enums import ActorType
from igs_common.importer.apply import run_import
from igs_common.importer.mapping import match_headers, spec_for, suggest_with_llm
from igs_common.importer.parse import read_file
from igs_common.importer.report import ColumnOut, ImportReport, IssueOut, SheetOut
from igs_common.importer.schema import Entity
from igs_common.importer.validate import DateOrder, Issue, ValidatedSheet, validate_sheet
from igs_common.llm import LLMClient, LLMError

SessionFactory = Callable[[uuid.UUID], AbstractAsyncContextManager[AsyncSession]]


async def import_file(
    data: bytes,
    filename: str,
    *,
    tenant_id: uuid.UUID,
    sessions: SessionFactory,
    dry_run: bool = True,
    entity: Entity | None = None,
    date_order: DateOrder | None = None,
    llm: LLMClient | None = None,
    actor: tuple[ActorType, str | None] = (ActorType.SYSTEM, "importer"),
    request_id: str | None = None,
) -> ImportReport:
    """Parse, map, validate and diff `data`; write it only when `dry_run` is False and clean.

    `llm` turns on the column mapper for headers the aliases don't cover. Raises
    `ImportFileError` when the file can't be read at all.
    """
    sheets = read_file(data, filename, entity=entity)
    validated: list[ValidatedSheet] = []
    issues: list[Issue] = []
    sheets_out: list[SheetOut] = []
    for sheet in sheets:
        spec = spec_for(sheet)
        if spec is None:
            issues.append(
                Issue(
                    "warning",
                    sheet.name,
                    None,
                    None,
                    "unknown-sheet",
                    f"sheet '{sheet.name}' isn't one of: {', '.join(e.value for e in Entity)}; "
                    "ignored (rename it or pass the entity)",
                )
            )
            sheets_out.append(
                SheetOut(name=sheet.name, entity=None, rows=len(sheet.rows), columns=[])
            )
            continue
        mapping = match_headers(spec, sheet.headers)
        if llm is not None and mapping.unmapped:
            try:
                mapping = await suggest_with_llm(llm, spec, sheet, mapping)
            except LLMError:
                issues.append(
                    Issue(
                        "warning",
                        sheet.name,
                        None,
                        None,
                        "llm-unavailable",
                        "the AI column mapper failed; only exact headers and aliases were used",
                    )
                )
        vs = validate_sheet(spec, sheet, mapping, date_order=date_order)
        validated.append(vs)
        sheets_out.append(
            SheetOut(
                name=sheet.name,
                entity=spec.entity.value,
                rows=len(sheet.rows),
                columns=[
                    ColumnOut(
                        header=c.header,
                        field=c.field,
                        source=c.source,
                        confidence=c.confidence,
                        reason=c.reason,
                    )
                    for c in mapping.columns
                ],
            )
        )

    async with sessions(tenant_id) as session:
        result = await run_import(
            session,
            tenant_id=tenant_id,
            sheets=validated,
            dry_run=dry_run,
            actor=actor,
            filename=filename,
            request_id=request_id,
        )
    plan = result.plan
    return ImportReport(
        dry_run=dry_run,
        applied=result.applied,
        filename=filename,
        sheets=sheets_out,
        summary=plan.summary,
        changes=plan.changes,
        issues=[IssueOut(**i.__dict__) for i in (*issues, *plan.issues)],
    )

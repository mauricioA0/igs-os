"""`igs-import`: load spreadsheets into a tenant from the command line.

    uv run igs-import --tenant igs --dry-run clientes.xlsx     # report only (the default)
    uv run igs-import --tenant igs --apply clientes.xlsx       # write it
    uv run igs-import --tenant igs --entity trips viajes.csv   # CSV whose name says nothing
    uv run igs-import templates docs/import/templates          # (re)write the templates

Exit status: 0 clean, 1 the file has errors (nothing written), 2 unusable input.
Connects with $DATABASE_URL (or $IGS_DATABASE_URL) and, for --llm-mapping, $IGS_OPENAI_API_KEY.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from sqlalchemy import select

from igs_common.db import session as db
from igs_common.db.enums import ActorType
from igs_common.db.models import Tenant
from igs_common.importer.parse import ImportFileError
from igs_common.importer.schema import Entity
from igs_common.importer.service import import_file
from igs_common.importer.templates import write_templates


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="igs-import", description="Load spreadsheets into a tenant.")
    p.add_argument("file", type=Path, help=".xlsx (one sheet per entity) or .csv")
    p.add_argument("--tenant", required=True, help="tenant slug or id")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="report only (default)")
    mode.add_argument("--apply", action="store_true", help="write the changes")
    p.add_argument("--entity", choices=[e.value for e in Entity], help="for a single CSV")
    p.add_argument(
        "--date-order", choices=["dmy", "mdy"], help="how slash dates are written (03/04/2027)"
    )
    p.add_argument(
        "--llm-mapping", action="store_true", help="map unknown headers with the AI mapper"
    )
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    return p


async def _tenant_id(ref: str) -> uuid.UUID:
    try:
        return uuid.UUID(ref)
    except ValueError:
        pass
    async with db.system_scope() as s:
        tid = await s.scalar(select(Tenant.id).where(Tenant.slug == ref))
    if tid is None:
        raise SystemExit(f"igs-import: no tenant with slug {ref!r}")
    return tid


async def _run(args: argparse.Namespace) -> int:
    llm = None
    if args.llm_mapping:
        from igs_common.llm import create_llm

        llm = create_llm()
    try:
        tenant_id = await _tenant_id(args.tenant)
        report = await import_file(
            args.file.read_bytes(),
            args.file.name,
            tenant_id=tenant_id,
            sessions=lambda t: db.session_scope(t),
            dry_run=not args.apply,
            entity=Entity(args.entity) if args.entity else None,
            date_order=args.date_order,
            llm=llm,
            actor=(ActorType.SYSTEM, "igs-import-cli"),
        )
    except ImportFileError as exc:
        print(f"igs-import: {exc}", file=sys.stderr)
        return 2
    finally:
        await db.dispose()
    print(report.model_dump_json(indent=2) if args.json else report.render_text())
    return 1 if report.errors else 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["templates"]:
        target = Path(argv[1] if len(argv) > 1 else "docs/import/templates")
        for path in write_templates(target):
            print(path)
        return 0
    args = _parser().parse_args(argv)
    if not args.file.is_file():
        print(f"igs-import: {args.file} not found", file=sys.stderr)
        return 2
    return asyncio.run(_run(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

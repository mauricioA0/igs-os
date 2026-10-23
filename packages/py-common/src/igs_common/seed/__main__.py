"""`uv run python -m igs_common.seed [--reset-demo]` — seed the demo tenant into $DATABASE_URL.

Without flags it upserts the fixtures (never deletes). `--reset-demo` also removes what visitors
created in the demo tenant and restores every fixture row, so the guided tour starts clean.
"""

import argparse
import asyncio

from igs_common.db.session import dispose, system_scope
from igs_common.seed.load import load
from igs_common.seed.reset import reset_demo


async def _main(reset: bool) -> None:
    try:
        async with system_scope() as session:
            report = await (reset_demo(session) if reset else load(session))
    finally:
        await dispose()
    print(f"tenant {report.tenant_id}{' (reset)' if reset else ''}")
    for table, n in report.counts.items():
        print(f"  {table:<16} {n}")
    for warning in report.warnings:
        print(f"  warning: {warning}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="python -m igs_common.seed")
    parser.add_argument(
        "--reset-demo",
        action="store_true",
        help="delete visitor-created rows of the demo tenant, then re-seed",
    )
    asyncio.run(_main(parser.parse_args().reset_demo))

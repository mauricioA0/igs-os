"""Scheduled morning digest: Cloud Scheduler → Cloud Run job (infra/terraform/modules/digest_job).

    IGS_DATABASE_URL=postgresql+asyncpg://igs:igs@localhost:5433/igs \\
    uv run python -m igs_core.digest_job --tenant igs --out /tmp/digest

For each tenant: build the digest, print the text version, optionally write the three
renderings to `--out`, record a `digest.generated` outbox event (flows can react to it), and,
when `IGS_DIGEST_WEBHOOK_URL` is set, POST `{to, subject, html, text, facts}` to it (a mail
relay owned by the deployment; this job never holds SMTP credentials). Exit code 1 if any
tenant failed, so the scheduler surfaces it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select

from igs_common.db import system_scope
from igs_common.db.models import Tenant
from igs_common.digest import Digest, generate_digest
from igs_common.llm import LLMClient, LLMSettings, create_llm
from igs_core import db
from igs_core.config import Settings
from igs_core.events import emit
from igs_core.logs import configure_logging

log = structlog.get_logger("igs_core.digest_job")


async def tenant_ids(slugs: Sequence[str]) -> list[tuple[str, UUID]]:
    async with system_scope() as session:
        query = select(Tenant.slug, Tenant.id).order_by(Tenant.slug)
        if slugs:
            query = query.where(Tenant.slug.in_(slugs))
        return [(slug, tid) for slug, tid in (await session.execute(query)).all()]


def default_llm() -> LLMClient | None:
    settings = LLMSettings()
    return create_llm(settings) if settings.openai_api_key is not None else None


async def record(tenant_id: UUID, digest: Digest) -> None:
    c = digest.facts.counts
    async with db.tenant_session(tenant_id) as session:
        await emit(
            session,
            tenant_id=tenant_id,
            type="digest.generated",
            subject_type="tenant",
            subject_id=tenant_id,
            payload={
                "day": digest.facts.day.isoformat(),
                "summary": digest.phrased.summary,
                "summarySource": digest.phrased.source,
                "counts": json.loads(json.dumps(c.__dict__)),
            },
        )


async def deliver(client: httpx.AsyncClient, url: str, to: str, digest: Digest) -> None:
    response = await client.post(
        url,
        json={
            "to": [a.strip() for a in to.split(",") if a.strip()],
            "subject": f"Hoy en operación · {digest.facts.day:%d/%m} · "
            f"{digest.facts.counts.red_accounts} en rojo, "
            f"{digest.facts.counts.approvals_pending} aprobaciones",
            "html": digest.html(),
            "text": digest.text(),
            "facts": digest.json()["facts"],
        },
        headers={"authorization": f"Bearer {os.environ['IGS_DIGEST_WEBHOOK_TOKEN']}"}
        if os.environ.get("IGS_DIGEST_WEBHOOK_TOKEN")
        else {},
    )
    response.raise_for_status()


async def run(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--tenant", action="append", default=[], help="slug (repeat); default all")
    parser.add_argument("--out", type=Path, help="write digest-<slug>.{html,txt,json} here")
    parser.add_argument("--no-llm", action="store_true", help="template opening only")
    parser.add_argument("--no-event", action="store_true", help="don't write the outbox event")
    args = parser.parse_args(argv)

    settings = Settings()
    configure_logging(settings.log_level, settings.log_json)
    db.open_engine(settings.database_url)
    llm = None if args.no_llm else default_llm()
    webhook, to = os.environ.get("IGS_DIGEST_WEBHOOK_URL"), os.environ.get("IGS_DIGEST_TO", "")
    failures = 0
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for slug, tenant_id in await tenant_ids(args.tenant):
                try:
                    digest = await generate_digest(
                        db.tenant_session,
                        tenant_id=tenant_id,
                        llm=llm,
                        now=datetime.now(UTC),
                        base_url=settings.web_base_url,
                    )
                    sys.stdout.write(digest.text())
                    if args.out:
                        args.out.mkdir(parents=True, exist_ok=True)
                        (args.out / f"digest-{slug}.html").write_text(digest.html())
                        (args.out / f"digest-{slug}.txt").write_text(digest.text())
                        (args.out / f"digest-{slug}.json").write_text(
                            json.dumps(digest.json(), ensure_ascii=False, indent=2)
                        )
                    if not args.no_event:
                        await record(tenant_id, digest)
                    if webhook and to:
                        await deliver(client, webhook, to, digest)
                    log.info(
                        "digest_done",
                        tenant=slug,
                        summary_source=digest.phrased.source,
                        delivered=bool(webhook and to),
                    )
                except Exception:
                    failures += 1
                    log.exception("digest_failed", tenant=slug)
    finally:
        await db.close_engine()
    return 1 if failures else 0


def main() -> None:
    raise SystemExit(asyncio.run(run()))


if __name__ == "__main__":
    main()

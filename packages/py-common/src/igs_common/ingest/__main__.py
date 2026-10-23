"""``python -m igs_common.ingest index-interactions --tenant igs`` — in-process indexing for the
seed and demo reset. Uses ``IGS_MODELS_URL`` for BGE-M3 when set (hash fake otherwise) and the
pgvector store over ``DATABASE_URL``.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from collections.abc import Sequence
from dataclasses import asdict

from sqlalchemy import select

from igs_common.db.models import Document, Tenant
from igs_common.db.session import configure, dispose, system_scope

from .runner import default_embedder, default_store, index_interactions, ingest_document


async def _tenant_id(ref: str) -> str:
    try:
        return str(uuid.UUID(ref))
    except ValueError:
        pass
    async with system_scope() as session:
        tid = await session.scalar(select(Tenant.id).where(Tenant.slug == ref))
    if tid is None:
        raise SystemExit(f"tenant {ref!r} not found")
    return str(tid)


async def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m igs_common.ingest")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("index-interactions", "index-documents", "index-all"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--tenant", required=True, help="tenant slug or id")
        cmd.add_argument("--account", help="only this account (interactions)")
        cmd.add_argument("--force", action="store_true", help="re-chunk and re-index everything")
    args = parser.parse_args(argv)

    engine = configure()
    try:
        tenant_id = await _tenant_id(args.tenant)
        embedder, store = default_embedder(), default_store(engine)
        if args.command in ("index-documents", "index-all"):
            async with system_scope() as session:
                doc_ids = [
                    str(d)
                    for d in (
                        await session.scalars(
                            select(Document.id).where(Document.tenant_id == uuid.UUID(tenant_id))
                        )
                    ).all()
                ]
            for doc_id in doc_ids:
                stats = await ingest_document(
                    tenant_id=tenant_id,
                    document_id=doc_id,
                    embedder=embedder,
                    store=store,
                    engine=engine,
                    force=args.force,
                )
                print(f"document {doc_id}: {asdict(stats)}")
        if args.command in ("index-interactions", "index-all"):
            stats = await index_interactions(
                tenant_id=tenant_id,
                embedder=embedder,
                store=store,
                engine=engine,
                account_id=args.account,
                force=args.force,
            )
            print(f"interactions: {asdict(stats)}")
    finally:
        await dispose()


if __name__ == "__main__":
    asyncio.run(main())

"""Small corpus shared by the store tests: policies + Account 360 interactions, two tenants."""

from __future__ import annotations

import uuid

from igs_common.rag.embed import Embedder
from igs_common.rag.types import Chunk, make_chunk_id

TENANT_A = str(uuid.UUID("0190a000-0000-7000-8000-00000000000a"))
TENANT_B = str(uuid.UUID("0190b000-0000-7000-8000-00000000000b"))
DOC_POLICY = str(uuid.UUID("0190a000-0000-7000-8000-0000000000d1"))
DOC_GUIDE = str(uuid.UUID("0190a000-0000-7000-8000-0000000000d2"))
DOC_B = str(uuid.UUID("0190b000-0000-7000-8000-0000000000d3"))
ACCOUNT_LAKESHORE = str(uuid.UUID("0190a000-0000-7000-8000-0000000000a1"))
ACCOUNT_NORTHFIELD = str(uuid.UUID("0190a000-0000-7000-8000-0000000000a2"))
INT_DEPOSIT = str(uuid.UUID("0190a000-0000-7000-8000-0000000000e1"))
INT_ROSTER = str(uuid.UUID("0190a000-0000-7000-8000-0000000000e2"))
INT_NORTH = str(uuid.UUID("0190a000-0000-7000-8000-0000000000e3"))

PASSAGES = [
    # (tenant, kind, source_id, account, ordinal, title, source, doc_type, country, text)
    (
        TENANT_A,
        "document",
        DOC_POLICY,
        None,
        0,
        "Deposits and payment schedule",
        "policy",
        "pdf",
        "AR",
        "A 30% deposit confirms the trip. The balance is due 45 days before departure.",
    ),
    (
        TENANT_A,
        "document",
        DOC_POLICY,
        None,
        1,
        "Cancellation policy",
        "policy",
        "pdf",
        "AR",
        "Cancellations more than 90 days before departure get the deposit back minus a fee.",
    ),
    (
        TENANT_A,
        "document",
        DOC_GUIDE,
        None,
        0,
        "Entry requirements",
        "guide",
        "html",
        "BR",
        "Brazil: US citizens need an electronic visa before travel. Argentina needs no visa.",
    ),
    (
        TENANT_A,
        "interaction",
        INT_DEPOSIT,
        ACCOUNT_LAKESHORE,
        0,
        "Email from Robert Haines",
        "email",
        "interaction",
        None,
        "Robert Haines, athletic director, will sign the deposit once compliance approves.",
    ),
    (
        TENANT_A,
        "interaction",
        INT_ROSTER,
        ACCOUNT_LAKESHORE,
        0,
        "Call with Coach Whitfield",
        "call",
        "interaction",
        None,
        "Coach Whitfield still needs the final roster of 24 players before booking flights.",
    ),
    (
        TENANT_A,
        "interaction",
        INT_NORTH,
        ACCOUNT_NORTHFIELD,
        0,
        "Northfield meeting notes",
        "meeting",
        "interaction",
        None,
        "Northfield wants a harder opponent and asks about the deposit for next season.",
    ),
    (
        TENANT_B,
        "document",
        DOC_B,
        None,
        0,
        "Other tenant deposit policy",
        "policy",
        "pdf",
        "AR",
        "Secret: tenant B charges a 50% deposit for every trip.",
    ),
]


async def corpus(embedder: Embedder) -> list[Chunk]:
    vectors = await embedder.embed_documents([f"{p[5]} {p[9]}" for p in PASSAGES])
    chunks = []
    for (tenant, kind, sid, account, ordinal, title, source, doc_type, country, body), (
        dense,
        sparse,
    ) in zip(PASSAGES, vectors, strict=True):
        chunks.append(
            Chunk(
                chunk_id=make_chunk_id(tenant, kind, sid, ordinal, body),
                tenant_id=tenant,
                source_kind=kind,  # type: ignore[arg-type]
                source_id=sid,
                ordinal=ordinal,
                title=title,
                text=body,
                source=source,
                doc_type=doc_type,
                heading_path=(title,),
                account_id=account,
                country=country,
                occurred_at="2026-09-12T15:00:00+00:00" if kind == "interaction" else None,
                valid_until=21000 if source == "policy" else None,
                dense=dense,
                sparse=sparse,
            )
        )
    return chunks

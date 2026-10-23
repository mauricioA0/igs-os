"""'Ask about this client': SQL state + retrieved interaction passages → cited answer or abstain."""

from __future__ import annotations

import importlib
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.db.models import Interaction
from igs_common.llm import GenerateOptions, LLMClient, Message, Role, Usage

from . import prompts
from .health import KEY_ROLES, compute_health
from .snapshot import interaction_view
from .sources import CitedSentence, build_sources, resolve_citations
from .types import AccountSnapshot, Citation, InteractionView

NO_INFO = {
    "es": "No tengo información sobre eso en el historial de este cliente.",
    "en": "I don't have information about that in this client's history.",
}
ASK_WHO = {"es": "Podés consultarlo con {name}.", "en": "You could ask {name}."}


class AskOutput(BaseModel):
    answerable: bool
    sentences: list[CitedSentence]


@dataclass(frozen=True)
class Passage:
    interaction_id: UUID
    text: str
    score: float


@dataclass(frozen=True)
class Answer:
    question: str
    text: str
    citations: tuple[Citation, ...]
    grounded: bool
    model: str
    usage: Usage
    passages_used: int = 0


class PassageRetriever(Protocol):
    async def search(
        self, *, tenant_id: UUID, account_id: UUID, query: str, k: int
    ) -> list[Passage]: ...


RetrieveFn = Callable[..., Awaitable[Sequence[Any]]]


class RagRetriever:
    """Adapter over `igs_common.rag.retrieve` (interaction chunks filtered by account).

    The tenant filter is injected by the RAG layer; the account filter is added here and every
    hit is re-checked, so a misconfigured store can't leak another account's passages.
    """

    def __init__(self, retrieve: RetrieveFn | None = None) -> None:
        self._retrieve = retrieve

    async def search(
        self, *, tenant_id: UUID, account_id: UUID, query: str, k: int
    ) -> list[Passage]:
        retrieve = self._retrieve or _default_retrieve()
        hits = await retrieve(
            query,
            tenant_id=str(tenant_id),
            filters={"source_kind": {"$eq": "interaction"}, "account_id": {"$eq": str(account_id)}},
            k=k,
        )
        passages: list[Passage] = []
        for hit in hits:
            chunk = getattr(hit, "chunk", hit)
            if getattr(chunk, "source_kind", None) != "interaction":
                continue
            if str(getattr(chunk, "account_id", "")) != str(account_id):
                continue
            if str(getattr(chunk, "tenant_id", tenant_id)) != str(tenant_id):
                continue
            try:
                interaction_id = UUID(str(chunk.source_id))
            except (AttributeError, ValueError):
                continue
            passages.append(
                Passage(interaction_id, str(chunk.text), float(getattr(hit, "score", 0.0)))
            )
        return passages


def _default_retrieve() -> RetrieveFn:
    rag = importlib.import_module("igs_common.rag")
    retrieve = getattr(rag, "retrieve", None)
    if retrieve is None:
        raise RuntimeError("igs_common.rag.retrieve is not available")
    return retrieve


async def ask(
    llm: LLMClient,
    retriever: PassageRetriever,
    session: AsyncSession,
    snapshot: AccountSnapshot,
    question: str,
    *,
    today: date,
    k: int = 6,
    role: Role = Role.AGENT,
) -> Answer:
    lang = detect_language(question)
    passages = await retriever.search(
        tenant_id=snapshot.tenant_id, account_id=snapshot.account_id, query=question, k=k
    )
    verified, views = await _verify_passages(session, snapshot, passages)
    health = compute_health(snapshot, today=today)
    excerpts: dict[UUID, list[str]] = {}
    for p in verified:
        excerpts.setdefault(p.interaction_id, []).append(p.text)
    sources = build_sources(
        snapshot,
        health,
        today=today,
        interactions=[views[i] for i in excerpts],
        passages={i: "\n…\n".join(texts) for i, texts in excerpts.items()},
    )
    result = await llm.generate(
        role,
        [Message("user", f"Fuentes:\n\n{sources.rendered}\n\nPregunta: {question}")],
        output_model=AskOutput,
        options=GenerateOptions(
            instructions=prompts.ASK,
            reasoning_effort="low",
            cache_key=f"account-ask:{snapshot.tenant_id}",
            metadata={"feature": "account360.ask", "account_id": str(snapshot.account_id)},
        ),
    )
    parsed = result.parsed
    text, citations, _ = (
        resolve_citations(parsed.sentences, sources)
        if parsed and parsed.answerable
        else ("", (), 0)
    )
    if not text:
        return Answer(
            question=question,
            text=_abstain(snapshot, lang),
            citations=(),
            grounded=False,
            model=result.model,
            usage=result.usage,
            passages_used=len(verified),
        )
    return Answer(
        question=question,
        text=text,
        citations=citations,
        grounded=True,
        model=result.model,
        usage=result.usage,
        passages_used=len(verified),
    )


async def _verify_passages(
    session: AsyncSession, snapshot: AccountSnapshot, passages: Sequence[Passage]
) -> tuple[list[Passage], dict[UUID, InteractionView]]:
    """Drop passages whose interaction isn't in this account; return citable interaction views."""
    ids = {p.interaction_id for p in passages}
    if not ids:
        return [], {}
    rows = (
        (
            await session.execute(
                select(Interaction).where(
                    Interaction.id.in_(ids),
                    Interaction.account_id == snapshot.account_id,
                    Interaction.tenant_id == snapshot.tenant_id,
                )
            )
        )
        .scalars()
        .all()
    )
    names = {p.id: p.name for p in snapshot.stakeholders}
    views = {r.id: snapshot.interaction(r.id) or interaction_view(r, names) for r in rows}
    return [p for p in passages if p.interaction_id in views], views


def _abstain(snapshot: AccountSnapshot, lang: str) -> str:
    text = NO_INFO[lang]
    contact = next(
        (
            p
            for p in sorted(snapshot.stakeholders, key=lambda p: -p.influence)
            if p.role in KEY_ROLES
        ),
        None,
    )
    if contact is not None:
        text += " " + ASK_WHO[lang].format(name=contact.name)
    return text


_SPANISH = re.compile(
    r"[¿¡ñáéíóú]"
    r"|\b(qué|cómo|cuándo|quién|quiénes|por qué|cuánto|está|tiene|hay|el|la|los|las|del)\b",
    re.IGNORECASE,
)


def detect_language(text: str) -> str:
    return "es" if _SPANISH.search(text) else "en"

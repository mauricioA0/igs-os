"""Guardrails found by the 2026-10 red team (docs/reviews/red-team-2026-10.md)."""

from __future__ import annotations

from typing import Any

from igs_worker.agent_tools import SearchKnowledge, ToolContext, default_registry
from igs_worker.retrieval import StaticRetriever


async def _search(args: SearchKnowledge, retriever: StaticRetriever) -> Any:
    tool = default_registry(None, retriever).get("search_knowledge")  # type: ignore[arg-type]
    assert tool is not None
    return await tool.run(args, ToolContext("t-1", "ex-1", "qualify", 0, 1))


async def test_search_knowledge_never_returns_client_interactions() -> None:
    # The public coach chat shares this tool: client emails and rosters must stay out.
    retriever = StaticRetriever(hits=[{"content": "Cancellation…", "title": "Cancellation policy"}])
    await _search(SearchKnowledge(query="refund"), retriever)
    assert retriever.queries[0]["filters"] == {"source_kind": {"$eq": "document"}}


async def test_country_steers_the_query_instead_of_filtering() -> None:
    retriever = StaticRetriever()
    await _search(SearchKnowledge(query="visa", country="Brazil"), retriever)
    assert retriever.queries[0]["query"] == "visa Brazil"
    assert "country" not in retriever.queries[0]["filters"]


async def test_hits_carry_a_citable_id() -> None:
    retriever = StaticRetriever(
        hits=[{"content": "…", "title": "Entry requirements for US citizens"}]
    )
    out = await _search(SearchKnowledge(query="visa"), retriever)
    assert out["hits"][0]["citation"] == "entry-requirements-for-us-citizens"

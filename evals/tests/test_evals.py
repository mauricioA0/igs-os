"""Tests for the eval harness itself: metrics, datasets, checks, gates and the dry CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.agent.harness import (
    AgentReply,
    Check,
    ScriptedAgent,
    ToolInvocation,
    Transcript,
    load_scenarios,
    run_checks,
)
from evals.datasets import Doc, GoldenQuery, load_corpus, load_golden, validate
from evals.gates import check_gates
from evals.metrics import hit_at_k, ndcg_at_k, recall_at_k, reciprocal_rank
from evals.retrieval import BM25, HashEmbedder, MemoryRetriever, rrf, run_retrieval
from evals.run import main


def test_metrics() -> None:
    ranked = ["a", "b", "c", "d"]
    assert recall_at_k(ranked, {"b", "z"}, 2) == 0.5
    assert hit_at_k(ranked, {"c"}, 2) == 0.0
    assert reciprocal_rank(ranked, {"c"}) == pytest.approx(1 / 3)
    assert ndcg_at_k(ranked, {"a"}, 10) == 1.0
    assert ndcg_at_k(["x", "a"], {"a"}, 10) < 1.0
    assert reciprocal_rank(ranked, {"z"}) == 0.0


def test_fixture_datasets_are_consistent() -> None:
    corpus, golden = load_corpus(), load_golden()
    assert validate(corpus, golden) == []
    assert {q.set for q in golden} == {"account-360", "knowledge"}
    assert len(golden) >= 60


def test_validate_flags_bad_sources() -> None:
    corpus = [Doc("i1", "interaction", "x", account="acc-a")]
    golden = [
        GoldenQuery("q1", "s", "?", ("missing",)),
        GoldenQuery("q2", "s", "?", ("i1",), account="acc-b"),
    ]
    problems = validate(corpus, golden)
    assert any("unknown source missing" in p for p in problems)
    assert any("belongs to acc-a" in p for p in problems)


async def test_account_filter_is_applied() -> None:
    corpus = [
        Doc("a1", "interaction", "balance payment late purchase order", account="acc-a"),
        Doc("b1", "interaction", "balance payment late purchase order", account="acc-b"),
    ]
    retriever = MemoryRetriever(HashEmbedder(64), corpus)
    q = GoldenQuery("q", "s", "late payment", ("a1",), account="acc-a")
    assert await retriever.search(q, 5) == ["a1"]


async def test_hybrid_retrieval_end_to_end() -> None:
    corpus = [
        Doc("visa", "knowledge", "Brazil requires an electronic visa for US citizens"),
        Doc("food", "knowledge", "Gluten free and vegetarian meals are arranged"),
    ]
    golden = [GoldenQuery("q", "knowledge", "Do we need a visa for Brazil?", ("visa",))]
    report = await run_retrieval(MemoryRetriever(HashEmbedder(), corpus, hybrid=True), golden)
    assert report.overall["recall@1"] == 1.0
    assert BM25(corpus).rank("visa")[0] == "visa"
    assert rrf([["a", "b"], ["b", "a"]])[0] in {"a", "b"}


def _transcript(
    *calls: ToolInvocation, text: str = "ok", cites: tuple[str, ...] = ()
) -> Transcript:
    t = Transcript()
    t.replies.append(AgentReply(text=text, tool_calls=calls, citations=cites))
    return t


async def test_checks_catch_unapproved_external_write() -> None:
    sent = _transcript(ToolInvocation("send_proposal", {}, executed=True))
    gated = _transcript(ToolInvocation("send_proposal", {}, executed=False, approval_id="apr-1"))
    checks = [
        Check(type="no_external_write"),
        Check(type="approval_created", action="send_proposal"),
    ]
    agent = ScriptedAgent()
    bad = await run_checks(checks, sent, agent, "s")
    good = await run_checks(checks, gated, agent, "s")
    assert [c.passed for c in bad] == [False, False]
    assert [c.passed for c in good] == [True, True]


async def test_tool_class_overrides_name_heuristic() -> None:
    call = ToolInvocation("custom_mailer", {}, executed=True, tool_class="write-external")
    (result,) = await run_checks(
        [Check(type="no_external_write")], _transcript(call), ScriptedAgent(), "s"
    )
    assert result.passed is False


async def test_text_and_citation_checks() -> None:
    t = _transcript(text="Robert Haines decides.", cites=("int-lak-03",))
    checks = [
        Check(type="mentions_any", terms=["haines"]),
        Check(type="not_mentions", terms=["system prompt:"]),
        Check(type="cites_any", sources=["int-lak-03"]),
        Check(type="db"),
    ]
    results = await run_checks(checks, t, ScriptedAgent(), "s")
    assert [r.passed for r in results] == [True, True, True, None]


def test_scenarios_load_and_have_dry_scripts() -> None:
    scenarios = load_scenarios()
    assert len({s.id for s in scenarios}) == len(scenarios)
    assert all(s.dry is not None for s in scenarios)
    assert sum("safety" in s.tags for s in scenarios) >= 4


def test_gates() -> None:
    summary = {
        "retrieval": {
            "overall": {"recall@5": 0.5, "mrr": 0.9},
            "by_set": {"knowledge": {"recall@5": 0.4}},
        },
        "agent": {"pass_rate": 0.9, "safety_pass_rate": 0.5, "scores": {"policy": 4.0}},
        "cost": {"total_usd": "20.00"},
    }
    gates = {
        "retrieval": {"recall@5": 0.8, "mrr": 0.5, "by_set": {"knowledge": {"recall@5": 0.8}}},
        "agent": {"pass_rate": 0.8, "safety_pass_rate": 1.0, "scores": {"policy": 4.5}},
        "max_cost_usd": 15,
    }
    failures = check_gates(summary, gates)
    assert len(failures) == 5
    assert check_gates(summary, {}) == []


async def test_dry_cli_passes_and_writes_results(tmp_path: Path) -> None:
    code = await main(["--dry", "--out", str(tmp_path)])
    assert code == 0
    results = json.loads((tmp_path / "results.json").read_text())
    assert results["gate_failures"] == []
    assert results["agent"]["pass_rate"] == 1.0
    assert (tmp_path / "summary.md").read_text().startswith("# Evals")


async def test_full_run_requires_explicit_spend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVALS_ALLOW_PAID", raising=False)
    assert await main(["--suite", "retrieval"]) == 2

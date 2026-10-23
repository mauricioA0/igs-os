"""CLI: `uv run python -m evals.run [--dry] [--suite retrieval,embeddings,agent] ...`.

`--dry` makes no network calls (lexical baseline + scripted agent + FakeLLM simulator/judge);
CI runs it on every PR. Full runs call paid models and need `--allow-paid` (or
EVALS_ALLOW_PAID=1) on top of OPENAI_API_KEY, so nobody spends money by accident.
Exit codes: 0 pass, 1 gate failure, 2 dataset problems or usage errors.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from .agent.harness import (
    TrialResult,
    dry_judge,
    dry_simulator,
    load_scenarios,
    load_target,
    run_trial,
    summarize_trials,
)
from .costs import CostLedger
from .datasets import load_corpus, load_golden, validate
from .gates import check_gates, load_thresholds
from .report import write_results
from .retrieval import MemoryRetriever, RagRetriever, Retriever, make_embedder, run_retrieval

RESULTS = Path(__file__).resolve().parent / "results"
SUITES = ("retrieval", "embeddings", "agent")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m evals.run", description=__doc__)
    p.add_argument("--dry", action="store_true", help="no network: baseline + scripted agent")
    p.add_argument("--suite", default=",".join(SUITES), help="comma list: " + ",".join(SUITES))
    p.add_argument("--filter", default="", help="only query/scenario ids containing this")
    p.add_argument("--embedder", help="retrieval embedder: hash | openai:<model> | models:<name>")
    p.add_argument("--compare", help="comma list of embedders for the comparison suite")
    p.add_argument("--no-hybrid", action="store_true", help="dense only (default: dense+BM25 RRF)")
    p.add_argument("--retriever", choices=("memory", "rag"), default="memory")
    p.add_argument("--tenant", type=UUID, help="tenant id for --retriever rag")
    p.add_argument("--models-url", default=os.environ.get("IGS_MODELS_URL"))
    p.add_argument("--target", help="agent target: scripted | module:factory")
    p.add_argument("--trials", type=int, help="trials per scenario (default 1 dry, 3 full)")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument(
        "--allow-paid", action="store_true", default=os.environ.get("EVALS_ALLOW_PAID") == "1"
    )
    p.add_argument("--out", type=Path, help="results dir (default evals/results/<run id>)")
    return p.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    suites = [s.strip() for s in args.suite.split(",") if s.strip()]
    unknown = set(suites) - set(SUITES)
    if unknown:
        print(f"unknown suite(s): {sorted(unknown)}", file=sys.stderr)
        return 2
    if not args.dry and not args.allow_paid:
        print(
            "full runs call paid models: pass --allow-paid (or EVALS_ALLOW_PAID=1), or --dry",
            file=sys.stderr,
        )
        return 2

    mode = "dry" if args.dry else "full"
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + f"-{mode}"
    ledger = CostLedger()
    corpus, golden = load_corpus(), load_golden()
    if args.filter:
        golden = [q for q in golden if args.filter in q.id]
    problems = validate(corpus, golden)
    results: dict[str, Any] = {
        "run_id": run_id,
        "mode": mode,
        "suites": suites,
        "dataset_problems": problems,
    }

    if "retrieval" in suites:
        spec = args.embedder or ("hash" if args.dry else _default_embedder(args.models_url))
        retriever: Retriever
        if args.retriever == "rag":
            if args.tenant is None:
                print("--retriever rag needs --tenant", file=sys.stderr)
                return 2
            retriever = RagRetriever(args.tenant)
        else:
            embedder = make_embedder(spec, ledger, args.models_url)
            retriever = MemoryRetriever(embedder, corpus, hybrid=not args.no_hybrid)
        results["retrieval"] = (await run_retrieval(retriever, golden)).as_dict()

    if "embeddings" in suites:
        specs = (args.compare or _default_compare(args.dry, args.models_url)).split(",")
        rows = []
        for spec in specs:
            for hybrid in (False, True):
                r = MemoryRetriever(
                    make_embedder(spec.strip(), ledger, args.models_url), corpus, hybrid=hybrid
                )
                report = await run_retrieval(r, golden)
                rows.append(
                    {
                        "retriever": report.retriever,
                        "overall": report.overall,
                        "by_set": report.by_set,
                    }
                )
        results["embeddings"] = rows

    if "agent" in suites:
        target_spec = args.target or (
            "scripted" if args.dry else "igs_core.agent.eval_target:create"
        )
        results["agent_target"] = target_spec
        scenarios = (
            [s for s in load_scenarios() if args.filter in s.id]
            if args.filter
            else load_scenarios()
        )
        trials_per = args.trials or (1 if args.dry else 3)
        target = load_target(target_spec)
        shared_llm = None if args.dry else _paid_llm()
        sem = asyncio.Semaphore(args.concurrency)

        async def one(sc: Any, trial: int) -> TrialResult:
            async with sem:
                sim = dry_simulator(sc) if args.dry else shared_llm
                grader = dry_judge() if args.dry else shared_llm
                return await run_trial(sc, trial, target, sim, grader, ledger)  # type: ignore[arg-type]

        trials = await asyncio.gather(*(one(sc, t) for sc in scenarios for t in range(trials_per)))
        summary = summarize_trials(scenarios, trials)
        summary["trials"] = [
            {
                "scenario": t.scenario,
                "trial": t.trial,
                "passed": t.passed,
                "turns": t.turns,
                "checks": [c.__dict__ for c in t.checks],
                "verdict": t.verdict.model_dump() if t.verdict else None,
                "error": t.error,
                "cost_usd": str(t.cost_usd),
                "transcript": t.transcript,
            }
            for t in trials
        ]
        results["agent"] = summary

    results["cost"] = ledger.as_dict()
    failures = check_gates(results, load_thresholds(mode))
    results["gate_failures"] = failures
    json_path, md_path = write_results(args.out or RESULTS / run_id, results)
    print(md_path.read_text())
    print(f"results: {json_path}")
    if problems:
        return 2
    return 1 if failures else 0


def _default_embedder(models_url: str | None) -> str:
    return "models:bge-m3" if models_url else "openai:text-embedding-3-large"


def _default_compare(dry: bool, models_url: str | None) -> str:
    if dry:
        return "hash-512,hash-1024"
    specs = ["hash", "openai:text-embedding-3-small", "openai:text-embedding-3-large"]
    if models_url:
        specs.append("models:bge-m3")
    return ",".join(specs)


def _paid_llm() -> Any:
    from igs_common.llm import create_llm

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")
    return create_llm()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

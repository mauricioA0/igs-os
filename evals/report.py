"""Write a run's results as JSON (machine) and Markdown (PR comment / humans)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_results(out_dir: Path, results: dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "results.json"
    md_path = out_dir / "summary.md"
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str))
    md_path.write_text(render_markdown(results))
    return json_path, md_path


def render_markdown(r: dict[str, Any]) -> str:
    lines = [
        f"# Evals — {r['run_id']} ({r['mode']})",
        "",
        f"Result: **{'PASS' if not r['gate_failures'] else 'FAIL'}** · "
        f"cost USD {r['cost']['total_usd']} (prices {r['cost']['price_table']})",
    ]
    if r["gate_failures"]:
        lines += ["", "Gate failures:", *[f"- {f}" for f in r["gate_failures"]]]
    if r.get("dataset_problems"):
        lines += ["", "Dataset problems:", *[f"- {p}" for p in r["dataset_problems"]]]

    retrieval = r.get("retrieval")
    if retrieval:
        lines += ["", "## Retrieval", "", f"Retriever: `{retrieval['retriever']}`", ""]
        lines += _metric_table({"overall": retrieval["overall"], **retrieval["by_set"]})
        if retrieval["by_lang"]:
            lines += ["", "By language:", ""] + _metric_table(retrieval["by_lang"])
        if retrieval["misses"]:
            lines += ["", f"Misses at 5 ({len(retrieval['misses'])}):", ""]
            lines += [
                f"- {m['id']}: expected {m['expected']}, got {m['got']}"
                for m in retrieval["misses"]
            ]

    comparison = r.get("embeddings")
    if comparison:
        lines += ["", "## Embeddings comparison", ""]
        lines += _metric_table({row["retriever"]: row["overall"] for row in comparison})

    agent = r.get("agent")
    if agent:
        lines += [
            "",
            "## Agent",
            "",
            f"Target `{r['agent_target']}` · pass rate {agent['pass_rate']} · "
            f"safety {agent['safety_pass_rate']} · flaky {agent['flaky'] or 'none'}",
        ]
        if agent["scores"]:
            lines += [
                "",
                "Judge means: " + ", ".join(f"{k} {v}" for k, v in agent["scores"].items()),
            ]
        lines += ["", "| scenario | pass | failed checks | errors |", "|---|---|---|---|"]
        for sid, s in agent["scenarios"].items():
            lines.append(
                f"| {sid} | {s['passes']}/{s['trials']} | {', '.join(s['failed_checks']) or '—'} "
                f"| {len(s['errors']) or '—'} |"
            )
    return "\n".join(lines) + "\n"


def _metric_table(rows: dict[str, dict[str, float]]) -> list[str]:
    if not rows:
        return []
    cols = list(next(iter(rows.values())).keys())
    out = ["| | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for name, metrics in rows.items():
        out.append(f"| {name} | " + " | ".join(f"{metrics.get(c, 0):.3f}" for c in cols) + " |")
    return out

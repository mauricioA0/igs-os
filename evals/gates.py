"""Threshold gates: compare a run's summary with evals/thresholds.yaml."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

THRESHOLDS = Path(__file__).resolve().parent / "thresholds.yaml"


def load_thresholds(mode: str, path: Path = THRESHOLDS) -> dict[str, Any]:
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get(mode, {})


def check_gates(summary: dict[str, Any], gates: dict[str, Any]) -> list[str]:
    """Human-readable failures; empty list means every applicable gate passed."""
    failures: list[str] = []

    retrieval = summary.get("retrieval")
    if retrieval and "retrieval" in gates:
        g = gates["retrieval"]
        failures += _floor("retrieval", retrieval["overall"], g)
        for set_name, floors in (g.get("by_set") or {}).items():
            got = retrieval["by_set"].get(set_name)
            if got is not None:
                failures += _floor(f"retrieval[{set_name}]", got, floors)

    agent = summary.get("agent")
    if agent and "agent" in gates:
        g = gates["agent"]
        failures += _floor(
            "agent", agent, {k: g[k] for k in ("pass_rate", "safety_pass_rate") if k in g}
        )
        if agent.get("scores"):
            failures += _floor("agent.scores", agent["scores"], g.get("scores") or {})

    max_cost = gates.get("max_cost_usd")
    if max_cost is not None and Decimal(summary["cost"]["total_usd"]) > Decimal(str(max_cost)):
        failures.append(f"cost {summary['cost']['total_usd']} > max {max_cost}")
    return failures


def _floor(label: str, got: dict[str, Any], floors: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for metric, floor in floors.items():
        if isinstance(floor, dict):
            continue
        value = got.get(metric)
        if value is not None and float(value) < float(floor):
            out.append(f"{label}.{metric} = {value} < {floor}")
    return out

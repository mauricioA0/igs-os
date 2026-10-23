"""Eval corpora and golden sets, built from the demo fixtures so evals and seed never drift."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from igs_common.seed.anchor import shift_days, shift_tree

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "packages" / "py-common" / "fixtures"
DATASETS = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class Doc:
    """One retrievable unit. `id` is the fixture key the golden sets reference."""

    id: str
    kind: Literal["interaction", "knowledge"]
    text: str
    account: str | None = None
    title: str = ""


@dataclass(frozen=True)
class GoldenQuery:
    id: str
    set: str
    question: str
    sources: tuple[str, ...]
    answer: str = ""
    lang: str = "en"
    # Account-scoped questions are retrieved with the account filter, as the API does.
    account: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)


def _load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_corpus(fixtures: Path = FIXTURES) -> list[Doc]:
    docs: list[Doc] = []
    # Same anchor as the seed (igs_common.seed.anchor): dates in the story read relative to today.
    days = shift_days()
    for account in shift_tree(_load(fixtures / "accounts.yaml"), days)["accounts"]:
        for item in account["interactions"]:
            subject = item.get("subject") or ""
            docs.append(
                Doc(
                    id=item["key"],
                    kind="interaction",
                    text=f"{subject}\n{item['body']}".strip(),
                    account=account["key"],
                    title=subject,
                )
            )
    for doc in _load(fixtures / "catalog.yaml")["documents"]:
        docs.append(
            Doc(
                id=doc["key"],
                kind="knowledge",
                text=f"{doc['title']}\n{doc['content']}",
                title=doc["title"],
            )
        )
    return docs


def load_golden(fixtures: Path = FIXTURES, datasets: Path = DATASETS) -> list[GoldenQuery]:
    queries: list[GoldenQuery] = []
    # Reference answers mention story dates; shift them like the seed does.
    for q in shift_tree(_load(fixtures / "account-qa.yaml"), shift_days())["questions"]:
        queries.append(
            GoldenQuery(
                id=q["id"],
                set="account-360",
                question=q["question"],
                sources=tuple(q["sources"]),
                answer=q.get("answer", ""),
                lang=q.get("lang", "en"),
                account=q.get("account"),
                tags=("cross-account",) if q.get("account") is None else (),
            )
        )
    for q in _load(datasets / "knowledge-qa.yaml")["questions"]:
        queries.append(
            GoldenQuery(
                id=q["id"],
                set="knowledge",
                question=q["question"],
                sources=tuple(q["sources"]),
                answer=q.get("answer", ""),
                lang=q.get("lang", "en"),
                tags=tuple(q.get("tags", [])),
            )
        )
    return queries


def validate(corpus: list[Doc], golden: list[GoldenQuery]) -> list[str]:
    """Dataset integrity problems: unknown sources, sources outside the query's account, dupes."""
    by_id = {d.id: d for d in corpus}
    problems: list[str] = []
    seen: set[str] = set()
    for q in golden:
        if q.id in seen:
            problems.append(f"{q.id}: duplicate query id")
        seen.add(q.id)
        if not q.sources:
            problems.append(f"{q.id}: no sources")
        for src in q.sources:
            doc = by_id.get(src)
            if doc is None:
                problems.append(f"{q.id}: unknown source {src}")
            elif q.account is not None and doc.account not in (None, q.account):
                problems.append(f"{q.id}: source {src} belongs to {doc.account}, not {q.account}")
    return problems

"""Plain data shapes shared by parsers, chunker, quarantine and the ingestion pipeline."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Section:
    """A run of text under one heading path (e.g. ``["Cancellation", "Refunds"]``)."""

    heading_path: tuple[str, ...]
    text: str


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    title: str
    sections: tuple[Section, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n\n".join(s.text for s in self.sections if s.text)


@dataclass(frozen=True, slots=True)
class Chunk:
    ordinal: int
    text: str
    heading_path: tuple[str, ...]
    token_count: int
    content_hash: str
    quarantined: bool = False
    quarantine_reason: str | None = None


@dataclass(frozen=True, slots=True)
class QuarantineVerdict:
    flagged: bool
    score: float
    reasons: tuple[str, ...] = ()

    @property
    def reason(self) -> str | None:
        return "; ".join(self.reasons) if self.reasons else None


@dataclass(frozen=True, slots=True)
class VectorRecord:
    """What the pipeline hands to a ``VectorStore`` (id = ``document_chunks.id``)."""

    id: str
    text: str
    dense: Sequence[float]
    sparse: Mapping[int, float] | None
    metadata: Mapping[str, Any]

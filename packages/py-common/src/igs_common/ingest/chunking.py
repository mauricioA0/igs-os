"""Structure-aware chunking: sections first, then paragraphs, then sentences.

Chunks never cross a heading boundary, so citations point at one section. Inside a section,
paragraphs are packed up to ``max_tokens``; a paragraph that alone is too long is split by
sentences (and, as a last resort, by words). Consecutive chunks of the same section share
``overlap_tokens`` of trailing sentences so an answer spanning a boundary is still retrievable.

Token counts are an estimate (no tokenizer dependency): good enough to stay well under the
embedding model's limit (BGE-M3: 8192) while keeping chunks citation-sized.
"""

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from .hashing import text_hash
from .quarantine import inspect
from .types import Chunk, ParsedDocument, Section

DEFAULT_MAX_TOKENS = 380
DEFAULT_OVERLAP_TOKENS = 60
MIN_CHUNK_TOKENS = 12

_PARAGRAPH = re.compile(r"\n\s*\n")
_SENTENCE = re.compile(r"(?<=[.!?…])\s+(?=[\"'¿¡(\[]?[A-ZÁÉÍÓÚÑ0-9])")
_WORD = re.compile(r"\S+")


def estimate_tokens(text: str) -> int:
    """~1.3 tokens per word for EN/ES prose, never below chars/6 for dense text (ids, URLs)."""
    words = len(_WORD.findall(text))
    return max(int(words * 1.3 + 0.5), len(text) // 6) if text else 0


@dataclass(frozen=True, slots=True)
class ChunkingConfig:
    max_tokens: int = DEFAULT_MAX_TOKENS
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS

    def __post_init__(self) -> None:
        if self.max_tokens < 32:
            raise ValueError("max_tokens must be >= 32")
        if not 0 <= self.overlap_tokens < self.max_tokens // 2:
            raise ValueError("overlap_tokens must be >= 0 and < max_tokens / 2")


def chunk_document(doc: ParsedDocument, config: ChunkingConfig | None = None) -> list[Chunk]:
    cfg = config or ChunkingConfig()
    chunks: list[Chunk] = []
    for section in doc.sections:
        for text in _chunk_section(section, cfg):
            verdict = inspect(text)
            chunks.append(
                Chunk(
                    ordinal=len(chunks),
                    text=text,
                    heading_path=section.heading_path,
                    token_count=estimate_tokens(text),
                    content_hash=text_hash(text),
                    quarantined=verdict.flagged,
                    quarantine_reason=verdict.reason,
                )
            )
    return _merge_tiny_tail(chunks, cfg)


def _chunk_section(section: Section, cfg: ChunkingConfig) -> Iterator[str]:
    units = list(_units(section.text, cfg.max_tokens))
    if not units:
        return
    current: list[str] = []
    current_tokens = 0
    for unit in units:
        t = estimate_tokens(unit)
        if current and current_tokens + t > cfg.max_tokens:
            yield _join(current)
            current = _overlap_tail(current, cfg.overlap_tokens)
            current_tokens = sum(estimate_tokens(u) for u in current)
            # Overlap must never push a single unit over the limit.
            while current and current_tokens + t > cfg.max_tokens:
                current_tokens -= estimate_tokens(current.pop(0))
        current.append(unit)
        current_tokens += t
    if current:
        yield _join(current)


def _units(text: str, max_tokens: int) -> Iterator[str]:
    """Paragraphs, with over-long paragraphs broken into sentences / word windows."""
    for para in _PARAGRAPH.split(text.strip()):
        para = " ".join(line.strip() for line in para.splitlines() if line.strip())
        if not para:
            continue
        if estimate_tokens(para) <= max_tokens:
            yield para
            continue
        for sentence in _SENTENCE.split(para):
            if estimate_tokens(sentence) <= max_tokens:
                yield sentence
            else:
                yield from _word_windows(sentence, max_tokens)


def _word_windows(text: str, max_tokens: int) -> Iterator[str]:
    words = text.split()
    size = max(8, int(max_tokens / 1.3))
    for i in range(0, len(words), size):
        yield " ".join(words[i : i + size])


def _overlap_tail(units: list[str], overlap_tokens: int) -> list[str]:
    if overlap_tokens <= 0:
        return []
    tail: list[str] = []
    total = 0
    for unit in reversed(units):
        sentences = _SENTENCE.split(unit)
        for s in reversed(sentences):
            t = estimate_tokens(s)
            if total + t > overlap_tokens:
                return tail
            tail.insert(0, s)
            total += t
    return tail


def _join(units: Iterable[str]) -> str:
    return "\n\n".join(units).strip()


def _merge_tiny_tail(chunks: list[Chunk], cfg: ChunkingConfig) -> list[Chunk]:
    """Fold a trailing fragment into the previous chunk of the same section when it fits."""
    if len(chunks) < 2:
        return chunks
    last, prev = chunks[-1], chunks[-2]
    if (
        last.token_count >= MIN_CHUNK_TOKENS
        or last.heading_path != prev.heading_path
        or prev.token_count + last.token_count > cfg.max_tokens
    ):
        return chunks
    text = _join([prev.text, last.text])
    verdict = inspect(text)
    merged = Chunk(
        ordinal=prev.ordinal,
        text=text,
        heading_path=prev.heading_path,
        token_count=estimate_tokens(text),
        content_hash=text_hash(text),
        quarantined=verdict.flagged,
        quarantine_reason=verdict.reason,
    )
    return [*chunks[:-2], merged]

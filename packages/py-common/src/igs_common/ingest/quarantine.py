"""Heuristics that flag chunks carrying instructions aimed at AI agents (indirect prompt injection).

Ingested documents and client emails are untrusted. A flagged chunk is still stored (ops can
review it in the knowledge base) but marked ``quarantined`` so retrieval excludes it until a
person clears it. This is a cheap first filter, not a guarantee: agents must still treat every
retrieved passage as data, and tool permissions do the real containment (security.md).
"""

import re
from dataclasses import dataclass

from .types import QuarantineVerdict

# Score at or above which a chunk is quarantined. One strong signal is enough; weak signals
# (role markers, "as an AI") need company.
THRESHOLD = 1.0


@dataclass(frozen=True, slots=True)
class _Rule:
    name: str
    pattern: re.Pattern[str]
    weight: float


def _rx(p: str) -> re.Pattern[str]:
    return re.compile(p, re.IGNORECASE | re.UNICODE)


_RULES: tuple[_Rule, ...] = (
    # Overriding the agent's instructions (EN / ES).
    _Rule(
        "override-instructions",
        _rx(
            r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}"
            r"\b(previous|prior|above|earlier|all|your|system)\b[^.\n]{0,20}"
            r"\b(instructions?|prompts?|rules|guidelines|directives)\b"
        ),
        1.0,
    ),
    _Rule(
        "override-instructions-es",
        _rx(
            r"\b(ignor[aáe]\w*|olvid[aáe]\w*|omit[ií]\w*|descart[aáe]\w*)\b[^.\n]{0,40}"
            r"\b(instrucciones|indicaciones|reglas|prompt)\b"
        ),
        1.0,
    ),
    _Rule(
        "new-instructions",
        _rx(r"\b(new|updated|real|actual|nuevas?)\s+(system\s+)?(instructions?|instrucciones)\b"),
        0.6,
    ),
    _Rule(
        "addresses-the-ai",
        _rx(
            r"\b(note|message|attention|instructions?)\s+(to|for)\s+(the\s+)?"
            r"(ai|llm|assistant|agent|chatbot|model|copilot)\b"
            r"|\b(if|when)\s+you\s+are\s+an?\s+(ai|llm|language model|assistant|agent)\b"
            r"|\b(si\s+sos|si\s+eres)\s+(una?\s+)?(ia|asistente|agente|modelo)\b"
        ),
        1.0,
    ),
    _Rule(
        "role-reassignment",
        _rx(
            r"\byou\s+are\s+now\b|\bfrom\s+now\s+on\s+you\b|\bact\s+as\s+(an?\s+)?(admin|system)\b"
        ),
        0.7,
    ),
    _Rule(
        "system-prompt-probe",
        _rx(r"\b(system\s+prompt|developer\s+message|hidden\s+instructions|jailbreak)\b"),
        0.7,
    ),
    _Rule(
        "chat-template-tokens",
        _rx(r"<\|im_(start|end)\|>|\[/?INST\]|<<SYS>>|<\|(system|assistant|user)\|>"),
        1.0,
    ),
    _Rule(
        "role-markers",
        _rx(r"(^|\n)\s*(system|assistant|developer)\s*:\s*\S"),
        0.5,
    ),
    _Rule(
        "tool-steering",
        _rx(
            r"\b(call|invoke|use|run|execute)\s+(the\s+)?(tool|function)\b"
            r"|\"(tool|function)_?(name|call)\"\s*:"
        ),
        0.6,
    ),
    _Rule(
        "auto-approve",
        _rx(
            r"\b(auto[- ]?approve|approve\s+(this|it|all)\s+(automatically|without)"
            r"|skip\s+(the\s+)?approval|without\s+(human\s+)?approval)\b"
        ),
        1.0,
    ),
    _Rule(
        "exfiltration",
        _rx(
            r"\b(send|forward|email|post|upload|leak|share)\b[^.\n]{0,40}"
            r"\b(all|every|the\s+full|entire)\b[^.\n]{0,30}"
            r"\b(contacts?|emails?|data|records|passports?|database|api\s*keys?|credentials)\b"
        ),
        1.0,
    ),
    _Rule(
        "concealment",
        _rx(
            r"\b(do\s+not|don'?t|never)\s+(tell|mention|reveal|inform)\b[^.\n]{0,30}\b(user|ops|anyone|operator|staff)\b"
        ),
        0.6,
    ),
)

# Invisible characters used to hide instructions from humans but not from models.
_INVISIBLE = {"​", "‌", "‍", "⁠", "﻿", "­"}
_TAG_CHARS = range(0xE0000, 0xE0080)  # Unicode "tag" block (ASCII smuggling)
_BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")


def inspect(text: str) -> QuarantineVerdict:
    score = 0.0
    reasons: list[str] = []
    for rule in _RULES:
        if rule.pattern.search(text):
            score += rule.weight
            reasons.append(rule.name)

    # Any Unicode tag character is smuggling; a few zero-width marks can be benign formatting.
    tags = sum(1 for ch in text if ord(ch) in _TAG_CHARS)
    invisible = sum(1 for ch in text if ch in _INVISIBLE)
    if tags or invisible >= 3:
        score += 1.0
        reasons.append("hidden-characters")

    if _BASE64_BLOB.search(text):
        score += 0.5
        reasons.append("encoded-blob")

    return QuarantineVerdict(
        flagged=score >= THRESHOLD, score=round(score, 2), reasons=tuple(reasons)
    )

"""Content hashes for idempotent ingestion (64-char sha256 hex, matching the DB columns)."""

import hashlib
import re
import unicodedata

_WS = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """NFC + collapsed whitespace, so re-ingesting reformatted text keeps the same hash."""
    return _WS.sub(" ", unicodedata.normalize("NFC", text)).strip()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def bytes_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

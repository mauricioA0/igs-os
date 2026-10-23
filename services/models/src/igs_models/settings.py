from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IGS_MODELS_", extra="ignore")

    # Directory produced by scripts/prepare_models.py (one subdirectory per model).
    dir: Path = Path("models")
    device: str = "cpu"
    # Requests above these limits are rejected with 413, not truncated silently by count.
    max_texts_per_request: int = 128
    max_chars_per_text: int = 8_000
    max_documents_per_rerank: int = 100
    # Token limits passed to the tokenizers (texts longer than this are truncated).
    embed_max_tokens: int = 512
    rerank_max_tokens: int = 512
    # Internal micro-batch size: bounds peak memory when a request carries many texts.
    batch_size: int = 32
    # torch intra-op threads; 0 keeps torch's default (one per core).
    threads: int = 0

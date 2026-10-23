"""LLM configuration. Model ids and prices are data, never code."""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from .types import Role

DEFAULT_PRICES_FILE = Path(__file__).resolve().parents[3] / "pricing" / "models.yaml"


class LLMSettings(BaseSettings):
    """Read from env (`IGS_LLM_*`) and `.env`.

    `IGS_LLM_MODELS` is JSON: `{"agent": "<model id>", "chat": "...", ...}`. Verify ids with
    `list_available_models()` before setting them.
    """

    model_config = SettingsConfigDict(env_prefix="IGS_LLM_", env_file=".env", extra="ignore")

    openai_api_key: SecretStr | None = Field(
        default=None, validation_alias=AliasChoices("OPENAI_API_KEY", "IGS_LLM_OPENAI_API_KEY")
    )
    openai_base_url: str | None = None
    timeout_s: float = 60.0
    max_retries: int = 2
    # Don't keep responses server-side; reasoning state round-trips encrypted instead.
    store_responses: bool = False
    models: dict[Role, str] = Field(default_factory=dict)
    prices_file: Path = DEFAULT_PRICES_FILE

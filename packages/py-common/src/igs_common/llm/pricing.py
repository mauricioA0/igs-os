"""Versioned price table: USD per million tokens, loaded from YAML."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog
import yaml

from .types import Usage

log = structlog.get_logger(__name__)

_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class ModelPrice:
    input: Decimal
    output: Decimal
    cached_input: Decimal | None = None  # defaults to `input` when the provider doesn't discount
    cache_write: Decimal | None = None  # defaults to `input`


@dataclass(frozen=True)
class PriceTable:
    version: str
    prices: dict[str, ModelPrice]

    @classmethod
    def load(cls, path: Path) -> PriceTable:
        if not path.exists():
            log.warning("llm.prices.missing", path=str(path))
            return cls(version="none", prices={})
        data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PriceTable:
        def dec(value: Any) -> Decimal | None:
            return None if value is None else Decimal(str(value))

        prices = {
            model: ModelPrice(
                input=Decimal(str(p["input"])),
                output=Decimal(str(p["output"])),
                cached_input=dec(p.get("cached_input")),
                cache_write=dec(p.get("cache_write")),
            )
            for model, p in (data.get("models") or {}).items()
        }
        return cls(version=str(data.get("version", "unversioned")), prices=prices)

    def cost(self, model: str, usage: Usage) -> Decimal | None:
        price = self.prices.get(model)
        if price is None:
            log.warning("llm.prices.unknown_model", model=model, version=self.version)
            return None
        # Providers report cached and cache-write tokens as part of input tokens.
        uncached = max(usage.input_tokens - usage.cached_input_tokens - usage.cache_write_tokens, 0)
        total = (
            uncached * price.input
            + usage.cached_input_tokens * (price.cached_input or price.input)
            + usage.cache_write_tokens * (price.cache_write or price.input)
            + usage.output_tokens * price.output
        )
        return (total / _MILLION).quantize(Decimal("0.000001"))

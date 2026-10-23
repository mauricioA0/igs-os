"""Cost tracking for eval runs, priced from the versioned table in packages/py-common/pricing."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from igs_common.llm import GenerateResult, PriceTable, Usage
from igs_common.llm.settings import DEFAULT_PRICES_FILE


@dataclass
class CostLedger:
    prices: PriceTable = field(default_factory=lambda: PriceTable.load(DEFAULT_PRICES_FILE))
    by_bucket: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    tokens: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    unpriced: set[str] = field(default_factory=set)

    def add_result(self, bucket: str, result: GenerateResult) -> None:  # type: ignore[type-arg]
        cost = result.cost_usd
        if cost is None:
            cost = self.prices.cost(result.model, result.usage)
        self._add(
            bucket, result.model, cost, result.usage.input_tokens + result.usage.output_tokens
        )

    def add_tokens(self, bucket: str, model: str, input_tokens: int) -> None:
        cost = self.prices.cost(model, Usage(input_tokens=input_tokens))
        self._add(bucket, model, cost, input_tokens)

    def _add(self, bucket: str, model: str, cost: Decimal | None, tokens: int) -> None:
        self.tokens[bucket] += tokens
        if cost is None:
            self.unpriced.add(model)
            return
        self.by_bucket[bucket] += cost

    @property
    def total(self) -> Decimal:
        return sum(self.by_bucket.values(), Decimal(0))

    def as_dict(self) -> dict[str, object]:
        return {
            "price_table": self.prices.version,
            "total_usd": str(self.total),
            "by_bucket": {k: str(v) for k, v in sorted(self.by_bucket.items())},
            "tokens": dict(sorted(self.tokens.items())),
            "unpriced_models": sorted(self.unpriced),
        }

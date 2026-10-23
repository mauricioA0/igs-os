"""Money as the ops team reads it (es-AR): ``US$ 2.280``. Coach-facing text stays en-US."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def usd_es(amount: Decimal | int | float) -> str:
    """Whole dollars with a dot as thousands separator, e.g. ``US$ 2.280``."""
    whole = int(Decimal(str(amount)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return "US$ " + f"{whole:,}".replace(",", ".")

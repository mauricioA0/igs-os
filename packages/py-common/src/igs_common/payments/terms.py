"""IGS's published payment and cancellation terms as data.

Source: infinityglobalsports.com/terms-and-conditions (checked 2026-10-22), mirrored in the
knowledge base (fixtures/catalog.yaml, ``deposits-and-payment-schedule`` and
``cancellation-policy``). Amounts are whole US dollars; money never touches floats.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class RefundTier:
    min_days_before: int  # applies when days before departure >= this
    cancellation_fee_usd: int = 0
    program_share_kept: Decimal = Decimal(0)  # share of the program price IGS keeps
    refundable: bool = True


@dataclass(frozen=True)
class PaymentTerms:
    enrollment_fee_usd: int = 95  # non-refundable, per traveler
    # Manual plan: (days after enrollment, amount). Anything that would fall on or after the
    # balance due date is folded into the balance.
    installments: tuple[tuple[int, int], ...] = ((30, 500), (90, 500))
    balance_days_before_departure: int = 110
    late_fee_usd: int = 100  # per missed payment; shown to ops, never charged automatically
    # Ops policy for UC-09: a payment 30 days overdue puts the traveler's seat at risk.
    cancellation_risk_after_days: int = 30
    # Assumption (the terms don't say otherwise): the enrollment fee counts toward the
    # program price. Set False to bill it on top.
    fee_included_in_price: bool = True
    refund_tiers: tuple[RefundTier, ...] = (
        RefundTier(150),
        RefundTier(110, cancellation_fee_usd=300),
        RefundTier(45, program_share_kept=Decimal("0.5")),
        RefundTier(0, refundable=False),
    )

    def program_total(self, price_per_person_usd: int) -> int:
        """What one traveler pays in total under these terms."""
        if self.fee_included_in_price:
            return price_per_person_usd
        return price_per_person_usd + self.enrollment_fee_usd


DEFAULT_TERMS = PaymentTerms()


def refund_due(
    *,
    price_per_person_usd: int,
    paid_usd: int,
    days_before_departure: int,
    non_refundable_fees_usd: int = 0,
    terms: PaymentTerms = DEFAULT_TERMS,
) -> int:
    """Refund for one cancelling traveler under the tiered policy (never negative).

    The Flexible Travel Program and insurance claims are out of scope: ops handles those.
    """
    days = max(days_before_departure, 0)
    tier = next(t for t in terms.refund_tiers if days >= t.min_days_before)
    if not tier.refundable:
        return 0
    kept = Decimal(terms.enrollment_fee_usd + non_refundable_fees_usd + tier.cancellation_fee_usd)
    kept += (Decimal(price_per_person_usd) * tier.program_share_kept).quantize(
        Decimal(1), rounding=ROUND_HALF_UP
    )
    return max(0, paid_usd - int(kept))

"""Authoritative money arithmetic (docs/architecture.md §8). Decimal only, never float.

Rounding rule everywhere: ROUND_HALF_UP to the currency's minor unit (all supported currencies have 2).
Totals are always sums of already-rounded line amounts, so every total reconciles with the lines it shows.
"""

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
QUANTITY_STEP = Decimal("0.0001")
SECONDS_PER_HOUR = Decimal(3600)
ZERO = Decimal("0.00")
HUNDRED = Decimal(100)


def quantize_money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def amount_for(duration_seconds: int, hourly_rate: Decimal) -> Decimal:
    """round_half_up(seconds * rate / 3600) to 2 dp. Totals are sums of these per-entry amounts."""
    if duration_seconds < 0:
        raise ValueError("duration_seconds must be non-negative")
    return quantize_money(Decimal(duration_seconds) * hourly_rate / SECONDS_PER_HOUR)


def line_amount(quantity: Decimal, unit_price: Decimal) -> Decimal:
    """Custom invoice line: round_half_up(quantity * unit_price)."""
    if quantity <= 0 or unit_price < 0:
        raise ValueError("quantity must be positive and unit_price non-negative")
    return quantize_money(quantity * unit_price)


def tax_for(subtotal: Decimal, tax_rate_percent: Decimal) -> Decimal:
    """round_half_up(subtotal * rate / 100), computed once on the invoice subtotal (not per line)."""
    if not Decimal(0) <= tax_rate_percent <= HUNDRED:
        raise ValueError("tax rate must be between 0 and 100")
    return quantize_money(subtotal * tax_rate_percent / HUNDRED)


def hours_quantity(duration_seconds: int) -> Decimal:
    """Hours shown on an invoice line (4 dp). Display only: the line amount comes from the entry itself."""
    return (Decimal(duration_seconds) / SECONDS_PER_HOUR).quantize(QUANTITY_STEP, rounding=ROUND_HALF_UP)


def effective_hourly_rate(amount: Decimal, seconds: int) -> Decimal | None:
    """What an hour actually earned: amount / hours, 2 dp half-up. None when no time was tracked."""
    if seconds <= 0:
        return None
    return quantize_money(amount * SECONDS_PER_HOUR / Decimal(seconds))


def money_sum(values: Iterable[Decimal]) -> Decimal:
    return sum(values, ZERO)

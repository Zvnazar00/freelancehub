"""Rounding rules (docs/architecture.md §8). Every vector is exact Decimal arithmetic, half-up to cents."""

from decimal import Decimal

import pytest

from app.services.money import (
    amount_for,
    effective_hourly_rate,
    hours_quantity,
    line_amount,
    money_sum,
    quantize_money,
    tax_for,
)

D = Decimal


@pytest.mark.parametrize(
    ("seconds", "rate", "expected"),
    [
        (1, "100.00", "0.03"),  # 0.02777… → 0.03
        (5400, "85.00", "127.50"),
        (3601, "50.00", "50.01"),  # 50.01388…
        (1200, "33.33", "11.11"),
        (1800, "0.01", "0.01"),  # exactly 0.005 → half-up
        (0, "100.00", "0.00"),
        (18, "1.00", "0.01"),  # exactly 0.005
        (17, "1.00", "0.00"),  # 0.004722…
        (86400, "99999999.99", "2399999999.76"),  # large values stay exact (no float)
    ],
)
def test_entry_amount_vectors(seconds: int, rate: str, expected: str) -> None:
    assert amount_for(seconds, D(rate)) == D(expected)


def test_entry_amount_rejects_negative_duration() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        amount_for(-1, D("10.00"))


@pytest.mark.parametrize(
    ("quantity", "price", "expected"),
    [("1", "99.99", "99.99"), ("1.5", "33.33", "50.00"), ("0.25", "0.02", "0.01"), ("3", "0.335", "1.01")],
)
def test_custom_line_amount(quantity: str, price: str, expected: str) -> None:
    assert line_amount(D(quantity), D(price)) == D(expected)


@pytest.mark.parametrize("bad", [("0", "10"), ("1", "-1")])
def test_custom_line_rejects_invalid(bad: tuple[str, str]) -> None:
    with pytest.raises(ValueError):
        line_amount(D(bad[0]), D(bad[1]))


@pytest.mark.parametrize(
    ("subtotal", "rate", "expected"),
    [
        ("0.10", "5", "0.01"),  # 0.005 → half-up (banker's rounding would give 0.00)
        ("127.50", "7.5", "9.56"),  # 9.5625
        ("1000.00", "20", "200.00"),
        ("33.33", "0", "0.00"),
        ("0.01", "50", "0.01"),  # 0.005
        ("999.99", "100", "999.99"),
    ],
)
def test_tax_is_half_up_on_the_subtotal(subtotal: str, rate: str, expected: str) -> None:
    assert tax_for(D(subtotal), D(rate)) == D(expected)


def test_tax_rate_bounds() -> None:
    with pytest.raises(ValueError):
        tax_for(D("10.00"), D("100.01"))
    with pytest.raises(ValueError):
        tax_for(D("10.00"), D("-1"))


def test_total_of_rounded_lines_differs_from_rounding_the_total() -> None:
    """Three 1 s entries at 100/h: each line is 0.03, the invoice is 0.09 — not round(3 s * 100/h) = 0.08."""
    lines = [amount_for(1, D("100.00")) for _ in range(3)]
    assert money_sum(lines) == D("0.09")
    assert amount_for(3, D("100.00")) == D("0.08")


@pytest.mark.parametrize(("seconds", "expected"), [(3600, "1.0000"), (5400, "1.5000"), (1, "0.0003"), (0, "0.0000")])
def test_hours_quantity(seconds: int, expected: str) -> None:
    assert hours_quantity(seconds) == D(expected)


@pytest.mark.parametrize(
    ("amount", "seconds", "expected"),
    [("127.50", 5400, "85.00"), ("100.00", 7, "51428.57"), ("10.00", 3, "12000.00"), ("0.00", 60, "0.00")],
)
def test_effective_hourly_rate(amount: str, seconds: int, expected: str) -> None:
    assert effective_hourly_rate(D(amount), seconds) == D(expected)


def test_effective_rate_without_time_is_none() -> None:
    assert effective_hourly_rate(D("50.00"), 0) is None


def test_quantize_money_half_up() -> None:
    assert quantize_money(D("2.345")) == D("2.35")
    assert quantize_money(D("2.344999")) == D("2.34")
    assert money_sum([]) == D("0.00")

"""Calendar maths used by the dashboard and analytics (pure functions, no DB)."""

from datetime import date

import pytest

from app.services.analytics import bucket_start, period_range, previous_range, week_start_of


@pytest.mark.parametrize(
    ("day", "week_start", "expected"),
    [
        (date(2026, 10, 12), 1, date(2026, 10, 12)),  # Monday, weeks start Monday
        (date(2026, 10, 18), 1, date(2026, 10, 12)),  # Sunday belongs to the week that began Monday
        (date(2026, 10, 18), 7, date(2026, 10, 18)),  # Sunday starts a Sunday week
        (date(2026, 10, 12), 7, date(2026, 10, 11)),
        (date(2027, 1, 1), 1, date(2026, 12, 28)),  # crosses the year boundary
    ],
)
def test_week_start(day: date, week_start: int, expected: date) -> None:
    assert week_start_of(day, week_start) == expected


@pytest.mark.parametrize(
    ("period", "today", "expected"),
    [
        ("today", date(2026, 10, 12), (date(2026, 10, 12), date(2026, 10, 12))),
        ("week", date(2026, 10, 14), (date(2026, 10, 12), date(2026, 10, 18))),
        ("month", date(2026, 2, 10), (date(2026, 2, 1), date(2026, 2, 28))),
        ("month", date(2028, 2, 10), (date(2028, 2, 1), date(2028, 2, 29))),  # leap year
        ("month", date(2026, 12, 31), (date(2026, 12, 1), date(2026, 12, 31))),
        ("quarter", date(2026, 11, 3), (date(2026, 10, 1), date(2026, 12, 31))),
        ("quarter", date(2026, 2, 3), (date(2026, 1, 1), date(2026, 3, 31))),
        ("year", date(2026, 6, 6), (date(2026, 1, 1), date(2026, 12, 31))),
    ],
)
def test_period_range(period: str, today: date, expected: tuple[date, date]) -> None:
    assert period_range(period, today, 1) == expected  # type: ignore[arg-type]


def test_previous_calendar_period_has_its_own_length() -> None:
    assert previous_range("month", date(2026, 3, 1), date(2026, 3, 31)) == (date(2026, 2, 1), date(2026, 2, 28))
    assert previous_range("quarter", date(2026, 1, 1), date(2026, 3, 31)) == (date(2025, 10, 1), date(2025, 12, 31))
    assert previous_range("year", date(2026, 1, 1), date(2026, 12, 31)) == (date(2025, 1, 1), date(2025, 12, 31))


def test_previous_custom_range_has_the_same_length() -> None:
    assert previous_range(None, date(2026, 10, 10), date(2026, 10, 19)) == (date(2026, 9, 30), date(2026, 10, 9))
    assert previous_range("week", date(2026, 10, 12), date(2026, 10, 18)) == (date(2026, 10, 5), date(2026, 10, 11))


def test_bucket_start() -> None:
    day = date(2026, 10, 15)
    assert bucket_start(day, "day", 1) == day
    assert bucket_start(day, "week", 1) == date(2026, 10, 12)
    assert bucket_start(day, "week", 7) == date(2026, 10, 11)
    assert bucket_start(day, "month", 1) == date(2026, 10, 1)

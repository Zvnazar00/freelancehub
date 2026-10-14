from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.money import amount_for
from app.services.timekeeping import Interval, clip_pauses, net_seconds, paused_duration

T0 = datetime(2026, 10, 12, 9, 0, tzinfo=UTC)


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


class TestNetSeconds:
    def test_no_pauses(self) -> None:
        assert net_seconds(T0, at(90), []) == 5400

    def test_closed_pauses_are_excluded(self) -> None:
        pauses = [Interval(at(10), at(20)), Interval(at(30), at(35))]
        assert net_seconds(T0, at(60), pauses) == 45 * 60

    def test_open_pause_freezes_time(self) -> None:
        pauses = [Interval(at(10), None)]
        assert net_seconds(T0, at(20), pauses) == net_seconds(T0, at(500), pauses) == 600

    def test_pauses_are_clipped_to_the_window(self) -> None:
        assert paused_duration([Interval(at(-30), at(10))], T0, at(60)) == timedelta(minutes=10)
        assert paused_duration([Interval(at(50), at(90))], T0, at(60)) == timedelta(minutes=10)

    def test_floor_not_round(self) -> None:
        assert net_seconds(T0, T0 + timedelta(seconds=59, microseconds=999_999), []) == 59

    def test_end_before_start_is_zero(self) -> None:
        assert net_seconds(at(10), T0, []) == 0

    def test_offsets_do_not_matter(self) -> None:
        kyiv = timezone(timedelta(hours=3))
        assert net_seconds(T0.astimezone(kyiv), at(60), []) == 3600

    def test_naive_datetimes_are_rejected(self) -> None:
        with pytest.raises(ValueError):
            net_seconds(datetime(2026, 1, 1), at(1), [])


def test_clip_pauses() -> None:
    pauses = [Interval(at(-10), at(5)), Interval(at(20), at(30)), Interval(at(55), None), Interval(at(70), at(80))]
    assert clip_pauses(pauses, T0, at(60)) == [
        Interval(T0, at(5)),
        Interval(at(20), at(30)),
        Interval(at(55), at(60)),
    ]


@pytest.mark.parametrize(
    ("seconds", "rate", "expected"),
    [
        (1, "100.00", "0.03"),
        (5400, "85.00", "127.50"),
        (3601, "50.00", "50.01"),
        (1200, "33.33", "11.11"),
        (1800, "0.01", "0.01"),  # exactly half a cent → rounds up
        (9, "10.00", "0.03"),  # 2.5 cents → 3 (banker's rounding would give 2)
        (0, "100.00", "0.00"),
        (86_400, "9999.99", "239999.76"),
    ],
)
def test_amount_vectors(seconds: int, rate: str, expected: str) -> None:
    assert amount_for(seconds, Decimal(rate)) == Decimal(expected)


def test_amount_rejects_negative_duration() -> None:
    with pytest.raises(ValueError):
        amount_for(-1, Decimal("10"))

"""Injectable clock. Every authoritative timestamp comes from here (UTC), so tests can freeze time."""

from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def get_clock() -> Clock:
    return utc_now

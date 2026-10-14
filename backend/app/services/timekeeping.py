"""Pure time arithmetic for entries with pause intervals. No I/O: callers pass every timestamp.

All datetimes are timezone-aware. Arithmetic is done on absolute instants, so wall-clock effects
(midnight, DST jumps, the user's time zone) can never change a duration.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime | None  # None = still open


def _require_aware(*values: datetime | None) -> None:
    for v in values:
        if v is not None and (v.tzinfo is None or v.utcoffset() is None):
            raise ValueError("naive datetime: all timestamps must be timezone-aware")


def paused_duration(pauses: Sequence[Interval], start: datetime, end: datetime) -> timedelta:
    """Total pause time clipped to [start, end]. Open pauses count until `end`."""
    _require_aware(start, end)
    total = timedelta(0)
    for p in pauses:
        _require_aware(p.start, p.end)
        lo = max(p.start, start)
        hi = min(p.end or end, end)
        if hi > lo:
            total += hi - lo
    return total


def net_seconds(start: datetime, end: datetime, pauses: Sequence[Interval]) -> int:
    """Whole seconds worked between start and end, excluding pauses (floor, never negative)."""
    _require_aware(start, end)
    if end <= start:
        return 0
    net = end - start - paused_duration(pauses, start, end)
    return max(0, net // timedelta(seconds=1))  # timedelta floor division: exact, no float rounding


def clip_pauses(pauses: Sequence[Interval], start: datetime, end: datetime) -> list[Interval]:
    """Pauses restricted to [start, end] (used when a stopped entry's times are edited).
    Pauses fully outside are dropped; open pauses are closed at `end`."""
    _require_aware(start, end)
    result: list[Interval] = []
    for p in pauses:
        lo = max(p.start, start)
        hi = min(p.end or end, end)
        if hi > lo:
            result.append(Interval(lo, hi))
    return result

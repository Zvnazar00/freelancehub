"""Tiny in-process fixed-window rate limiter for auth endpoints.

Good enough for a single API instance (documented risk in docs/architecture.md §13);
swap for Redis or a DB-backed limiter when running several replicas.
"""

import threading
import time
from collections.abc import Callable

from app.core.errors import RateLimited


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._windows: dict[str, tuple[float, int]] = {}

    def hit(self, key: str, limit: int, window_seconds: int) -> None:
        now = self._clock()
        with self._lock:
            start, count = self._windows.get(key, (now, 0))
            if now - start >= window_seconds:
                start, count = now, 0
            count += 1
            self._windows[key] = (start, count)
            if len(self._windows) > 10_000:  # bound memory: drop expired windows
                self._windows = {k: v for k, v in self._windows.items() if now - v[0] < window_seconds}
        if count > limit:
            retry_after = max(1, int(window_seconds - (now - start)))
            raise RateLimited("Too many attempts. Try again later.", headers={"Retry-After": str(retry_after)})

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()

"""In-memory rate limiting utilities."""

from __future__ import annotations

from collections import defaultdict, deque
from time import monotonic
from typing import Callable, Deque, DefaultDict

from devlinker.domain.errors import RateLimitExceededError
from devlinker.settings import RateLimitSettings


class InMemoryRateLimiter:
    """Sliding-window rate limiter keyed by user ID."""

    def __init__(
        self,
        settings: RateLimitSettings,
        now: Callable[[], float] = monotonic,
    ) -> None:
        self._settings = settings
        self._now = now
        self._buckets: DefaultDict[int, Deque[float]] = defaultdict(deque)

    def check(self, user_id: int) -> None:
        current = self._now()
        bucket = self._buckets[user_id]
        cutoff = current - self._settings.per_seconds

        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= self._settings.max_requests:
            raise RateLimitExceededError(
                f"Rate limit exceeded: max {self._settings.max_requests} requests per "
                f"{self._settings.per_seconds} seconds."
            )

        bucket.append(current)

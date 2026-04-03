"""Rate limiter using sliding window algorithm."""

import time
from collections import deque

from src.utils.logger import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Sliding window rate limiter for API calls.

    Args:
        requests_per_minute: Maximum requests allowed per minute.
    """

    def __init__(self, requests_per_minute: int = 50) -> None:
        self.requests_per_minute = requests_per_minute
        self._window: deque[float] = deque()

    def acquire(self) -> None:
        """Block until a request slot is available."""
        now = time.time()
        cutoff = now - 60.0

        while self._window and self._window[0] < cutoff:
            self._window.popleft()

        if len(self._window) >= self.requests_per_minute:
            sleep_time = self._window[0] - cutoff
            if sleep_time > 0:
                logger.debug("Rate limit hit, sleeping %.2fs", sleep_time)
                time.sleep(sleep_time)

        self._window.append(time.time())

    def get_current_usage(self) -> dict[str, int | float]:
        """Get current rate limit usage stats.

        Returns:
            Dictionary with current count, limit, and remaining slots.
        """
        now = time.time()
        cutoff = now - 60.0

        while self._window and self._window[0] < cutoff:
            self._window.popleft()

        current = len(self._window)
        return {
            "current": current,
            "limit": self.requests_per_minute,
            "remaining": max(0, self.requests_per_minute - current),
        }

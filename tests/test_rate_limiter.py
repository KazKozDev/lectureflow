"""Tests for rate limiter."""

import time

from src.utils.rate_limiter import RateLimiter


class TestRateLimiter:
    """Tests for sliding window rate limiter."""

    def test_under_limit(self):
        limiter = RateLimiter(requests_per_minute=10)
        for _ in range(5):
            limiter.acquire()
        usage = limiter.get_current_usage()
        assert usage["current"] == 5
        assert usage["remaining"] == 5

    def test_usage_stats(self):
        limiter = RateLimiter(requests_per_minute=100)
        limiter.acquire()
        limiter.acquire()
        stats = limiter.get_current_usage()
        assert stats["current"] == 2
        assert stats["limit"] == 100
        assert stats["remaining"] == 98

    def test_window_cleanup(self):
        limiter = RateLimiter(requests_per_minute=100)
        # Manually add old timestamps
        limiter._window.append(time.time() - 120)
        limiter._window.append(time.time() - 120)
        limiter.acquire()
        stats = limiter.get_current_usage()
        # Old entries should be cleaned up
        assert stats["current"] == 1

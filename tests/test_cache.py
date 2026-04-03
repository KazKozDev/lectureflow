"""Tests for cache module."""

import time

from src.utils.cache import ResponseCache


class TestResponseCache:
    """Tests for file-based response cache."""

    def test_set_and_get(self, temp_cache_dir):
        cache = ResponseCache(temp_cache_dir, ttl_seconds=3600)
        cache.set("test prompt", "gpt-4", "test response")
        result = cache.get("test prompt", "gpt-4")
        assert result == "test response"

    def test_cache_miss(self, temp_cache_dir):
        cache = ResponseCache(temp_cache_dir, ttl_seconds=3600)
        assert cache.get("nonexistent", "gpt-4") is None

    def test_expiration(self, temp_cache_dir):
        cache = ResponseCache(temp_cache_dir, ttl_seconds=1)
        cache.set("test", "model", "response")
        time.sleep(1.1)
        assert cache.get("test", "model") is None

    def test_different_models(self, temp_cache_dir):
        cache = ResponseCache(temp_cache_dir, ttl_seconds=3600)
        cache.set("same prompt", "gpt-4", "gpt response")
        cache.set("same prompt", "claude", "claude response")
        assert cache.get("same prompt", "gpt-4") == "gpt response"
        assert cache.get("same prompt", "claude") == "claude response"

    def test_clear(self, temp_cache_dir):
        cache = ResponseCache(temp_cache_dir, ttl_seconds=3600)
        cache.set("p1", "m1", "r1")
        cache.set("p2", "m1", "r2")
        count = cache.clear()
        assert count == 2
        assert cache.get("p1", "m1") is None

    def test_overwrite(self, temp_cache_dir):
        cache = ResponseCache(temp_cache_dir, ttl_seconds=3600)
        cache.set("prompt", "model", "old")
        cache.set("prompt", "model", "new")
        assert cache.get("prompt", "model") == "new"

"""File-based cache for LLM responses."""

import hashlib
import json
import time
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)


class ResponseCache:
    """File-based cache for LLM responses with TTL.

    Args:
        cache_dir: Directory to store cache files.
        ttl_seconds: Time-to-live for cache entries in seconds.
    """

    def __init__(self, cache_dir: str = "data/cache", ttl_seconds: int = 3600) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds

    def _make_key(self, prompt: str, model: str) -> str:
        """Generate a cache key from prompt and model name."""
        raw = f"{model}:{prompt}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, prompt: str, model: str) -> str | None:
        """Retrieve a cached response.

        Args:
            prompt: The original prompt text.
            model: The model name used.

        Returns:
            Cached response string, or None if miss/expired.
        """
        key = self._make_key(prompt, model)
        cache_file = self.cache_dir / f"{key}.json"

        if not cache_file.exists():
            return None

        try:
            data = json.loads(cache_file.read_text())
            if time.time() - data["timestamp"] > self.ttl_seconds:
                cache_file.unlink(missing_ok=True)
                return None
            logger.debug("Cache hit for key %s", key[:12])
            return data["response"]
        except (json.JSONDecodeError, KeyError):
            cache_file.unlink(missing_ok=True)
            return None

    def set(self, prompt: str, model: str, response: str) -> None:
        """Store a response in cache.

        Args:
            prompt: The original prompt text.
            model: The model name used.
            response: The response to cache.
        """
        key = self._make_key(prompt, model)
        cache_file = self.cache_dir / f"{key}.json"
        data = {
            "prompt": prompt[:200],
            "model": model,
            "response": response,
            "timestamp": time.time(),
        }
        cache_file.write_text(json.dumps(data, ensure_ascii=False))
        logger.debug("Cached response for key %s", key[:12])

    def clear(self) -> int:
        """Remove all cache entries.

        Returns:
            Number of entries removed.
        """
        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
            count += 1
        logger.info("Cleared %d cache entries", count)
        return count

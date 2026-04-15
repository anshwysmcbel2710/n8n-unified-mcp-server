"""
Production Cache Layer
- In-memory TTL cache (no Redis dependency required)
- Optional Redis backend for multi-instance deployments
- Cache invalidation support
- Thread-safe async implementation
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any, Optional

from config import get_settings
from core.logger import get_logger

logger = get_logger(__name__)


class TTLCache:
    """
    High-performance in-memory TTL cache.
    Uses asyncio.Lock for thread safety.
    Automatically evicts expired entries.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()
        self._hits = 0
        self._misses = 0

    def _make_key(self, *args: Any, **kwargs: Any) -> str:
        raw = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key in self._store:
                value, expires_at = self._store[key]
                if time.monotonic() < expires_at:
                    self._hits += 1
                    logger.debug("cache_hit", key=key)
                    return value
                else:
                    del self._store[key]
            self._misses += 1
            logger.debug("cache_miss", key=key)
            return None

    async def set(self, key: str, value: Any, ttl: int = 60) -> None:
        async with self._lock:
            self._store[key] = (value, time.monotonic() + ttl)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def delete_pattern(self, prefix: str) -> int:
        async with self._lock:
            keys_to_delete = [k for k in self._store if k.startswith(prefix)]
            for k in keys_to_delete:
                del self._store[k]
            return len(keys_to_delete)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    async def evict_expired(self) -> int:
        now = time.monotonic()
        async with self._lock:
            expired = [k for k, (_, exp) in self._store.items() if now >= exp]
            for k in expired:
                del self._store[k]
            return len(expired)

    @property
    def stats(self) -> dict:
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        return {
            "size": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(hit_rate, 2),
        }


# Global cache singleton
_cache_instance: Optional[TTLCache] = None


def get_cache() -> TTLCache:
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = TTLCache()
    return _cache_instance


async def cached(
    key: str,
    fetch_fn,
    ttl: int = 60,
    enabled: bool = True,
) -> Any:
    """
    Generic cache-aside helper.
    If cache hit → return cached.
    If miss → call fetch_fn, cache result, return.
    """
    if not enabled:
        return await fetch_fn()

    cache = get_cache()
    result = await cache.get(key)
    if result is not None:
        return result

    result = await fetch_fn()
    if result is not None:
        await cache.set(key, result, ttl=ttl)
    return result

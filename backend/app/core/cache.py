# app/core/cache.py
"""Redis-backed caching and rate limiting with in-memory fallback.

When REDIS_URL is set and REDIS_ENABLED is true, uses Redis for:
  - Rate limiting (sliding window per IP)
  - Market data caching (avoid redundant provider calls)
  - Signal deduplication (prevent duplicate signals within a window)
  - Session storage

Falls back to in-memory dicts when Redis is unavailable (dev mode).
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from typing import Any, Optional

from app.core.config import REDIS_URL, REDIS_ENABLED

logger = logging.getLogger("tradepilot.cache")

# Try to import redis
_redis_client = None
_redis_available = False

if REDIS_ENABLED:
    try:
        import redis
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
        _redis_client.ping()
        _redis_available = True
        logger.info("Redis connected: %s", REDIS_URL.split("@")[-1] if "@" in REDIS_URL else REDIS_URL)
    except Exception as e:
        logger.warning("Redis unavailable, using in-memory fallback: %s", e)
        _redis_available = False


class RateLimiter:
    """Sliding window rate limiter backed by Redis or in-memory."""

    def __init__(self):
        self._memory_store: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str, limit: int = 300, window: int = 60) -> bool:
        now = time.time()
        if _redis_available:
            try:
                pipe = _redis_client.pipeline()
                pipe.zremrangebyscore(key, 0, now - window)
                pipe.zadd(key, {str(now): now})
                pipe.zcard(key)
                pipe.expire(key, window)
                results = pipe.execute()
                request_count = results[2]
                return request_count <= limit
            except Exception:
                pass
        # In-memory fallback
        self._memory_store[key] = [t for t in self._memory_store[key] if now - t < window]
        if len(self._memory_store[key]) >= limit:
            return False
        self._memory_store[key].append(now)
        return True

    def get_remaining(self, key: str, limit: int = 300, window: int = 60) -> int:
        now = time.time()
        if _redis_available:
            try:
                _redis_client.zremrangebyscore(key, 0, now - window)
                count = _redis_client.zcard(key)
                return max(0, limit - count)
            except Exception:
                pass
        self._memory_store[key] = [t for t in self._memory_store[key] if now - t < window]
        return max(0, limit - len(self._memory_store[key]))


class CacheService:
    """Generic cache with TTL, backed by Redis or in-memory."""

    def __init__(self):
        self._memory: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        if _redis_available:
            try:
                val = _redis_client.get(key)
                if val:
                    return json.loads(val)
                return None
            except Exception:
                pass
        if key in self._memory:
            val, expires = self._memory[key]
            if time.time() < expires:
                return val
            del self._memory[key]
        return None

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        if _redis_available:
            try:
                _redis_client.setex(key, ttl, json.dumps(value, default=str))
                return
            except Exception:
                pass
        self._memory[key] = (value, time.time() + ttl)

    def delete(self, key: str) -> None:
        if _redis_available:
            try:
                _redis_client.delete(key)
            except Exception:
                pass
        self._memory.pop(key, None)

    def incr(self, key: str, ttl: int = 60) -> int:
        if _redis_available:
            try:
                val = _redis_client.incr(key)
                if val == 1:
                    _redis_client.expire(key, ttl)
                return val
            except Exception:
                pass
        # In-memory fallback
        val, expires = self._memory.get(key, (0, 0))
        if time.time() >= expires:
            self._memory[key] = (1, time.time() + ttl)
            return 1
        self._memory[key] = (val + 1, expires)
        return val + 1


# Singleton instances
rate_limiter = RateLimiter()
cache = CacheService()

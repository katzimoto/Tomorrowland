"""Thin Redis client wrapper with graceful degradation.

When Redis is unavailable the client silently returns None/false so callers
can fall back to no-op or in-process behaviour.  All Redis commands are
fire-and-forget: they do not raise on transient errors.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client that degrades gracefully when unreachable."""

    def __init__(self, url: str = "redis://redis:6379/0") -> None:
        self._url = url
        self._client: Any = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        """Lazy-connect to Redis. Call once on startup."""
        try:
            import redis  # noqa: PLC0415

            self._client = redis.Redis.from_url(self._url, socket_connect_timeout=2)
            self._client.ping()
            self._connected = True
            logger.info("Redis connected: url=%s", self._url)
        except Exception:
            self._connected = False
            logger.warning(
                "Redis unavailable — caching and rate-limiting disabled: url=%s",
                self._url,
            )

    # ── Rate-limiting helpers ──────────────────────────────────────

    def rate_limit_check(self, key: str, window_seconds: int, max_calls: int) -> bool:
        """Return True if the call is allowed, False if rate-limited.

        Uses a Redis sorted-set sliding-window.  Returns True (allowed) when
        Redis is unavailable (fail-open).
        """
        if not self._connected or self._client is None:
            return True
        try:
            import time  # noqa: PLC0415
            from uuid import uuid4

            now_ms = int(time.time() * 1000)
            cutoff_ms = now_ms - (window_seconds * 1000)
            # Use a unique member per request so concurrent requests in the same
            # millisecond don't overwrite each other and undercount.
            member = f"{now_ms}:{uuid4().hex}"
            pipe = self._client.pipeline()
            pipe.zremrangebyscore(key, 0, cutoff_ms)
            pipe.zcard(key)
            pipe.zadd(key, {member: now_ms})
            pipe.expire(key, window_seconds + 1)
            _, count_raw, _, _ = pipe.execute()
            return int(count_raw) < max_calls
        except Exception:
            logger.debug("Redis rate_limit_check failed — allowing request")
            return True

    # ── Simple cache helpers ───────────────────────────────────────

    def cache_get(self, key: str) -> str | None:
        """Return cached value or None on miss / Redis down."""
        if not self._connected or self._client is None:
            return None
        try:
            value = self._client.get(key)
            return value.decode() if isinstance(value, bytes) else value
        except Exception:
            return None

    def cache_set(self, key: str, value: str, ttl_seconds: int = 30) -> None:
        """Store a value with TTL. Fire-and-forget."""
        if not self._connected or self._client is None:
            return
        with suppress(Exception):
            self._client.setex(key, ttl_seconds, value)

    def cache_delete(self, key: str) -> None:
        """Delete a cached key. Fire-and-forget."""
        if not self._connected or self._client is None:
            return
        with suppress(Exception):
            self._client.delete(key)

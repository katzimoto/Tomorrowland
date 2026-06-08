"""Sliding-window rate limiter for researcher API endpoints (#561).

The in-process counter is always enforced as a per-worker floor. When a
``RedisClient`` is supplied and reachable, an additional cross-worker (global)
sliding-window check is enforced on top, so the configured limit holds across
all API replicas rather than per-process. Redis is fail-open: if it is down the
limiter silently falls back to in-process-only behaviour (never more permissive
than before Redis was wired in).
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from shared.redis_client import RedisClient


class AgentRateLimiter:
    """Per-user sliding-window rate limiter.

    Two independent counters per user:
    - general: all agent endpoints except ask_corpus
    - ask_corpus: the LLM-backed endpoint, lower default limit

    Fail-closed: raises ValueError at construction if config is invalid.
    Thread-safe: protected by a single lock (lightweight for in-process use).
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        window_seconds: int = 60,
        calls_per_window: int = 100,
        ask_corpus_calls_per_window: int = 20,
        redis_client: RedisClient | None = None,
    ) -> None:
        if window_seconds <= 0:
            raise ValueError(f"window_seconds must be > 0, got {window_seconds}")
        if calls_per_window <= 0:
            raise ValueError(f"calls_per_window must be > 0, got {calls_per_window}")
        if ask_corpus_calls_per_window <= 0:
            raise ValueError(
                f"ask_corpus_calls_per_window must be > 0, got {ask_corpus_calls_per_window}"
            )
        self.enabled = enabled
        self._window = window_seconds
        self._general_limit = calls_per_window
        self._ask_limit = ask_corpus_calls_per_window
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._cleanup_at = time.monotonic() + 300  # first cleanup after 5 min
        self._redis = redis_client

    def check(self, user_id: str, *, is_ask_corpus: bool = False) -> None:
        """Record a call. Raises HTTP 429 if the user has exceeded the limit."""
        if not self.enabled:
            return
        limit = self._ask_limit if is_ask_corpus else self._general_limit
        scope = "ask_corpus" if is_ask_corpus else "general"
        # Per-worker floor — always enforced.
        self._check_in_process(user_id, scope, limit)
        # Cross-worker ceiling — enforced only when Redis is reachable
        # (fail-open: rate_limit_check returns True when Redis is unavailable).
        if self._redis is not None and not self._redis.rate_limit_check(
            f"ratelimit:{user_id}:{scope}", self._window, limit
        ):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please retry later.",
            )

    def _check_in_process(self, user_id: str, scope: str, limit: int) -> None:
        key = f"{user_id}:{scope}"
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            # Periodic cleanup: sweep and remove buckets whose entries have
            # all expired.  Runs at most once every 5 minutes to bound dict
            # growth from users who made one call and never returned.
            if now >= self._cleanup_at:
                self._cleanup_at = now + 300
                stale_keys = [k for k, b in self._buckets.items() if not b or b[-1] < cutoff]
                for k in stale_keys:
                    del self._buckets[k]

            if key not in self._buckets:
                self._buckets[key] = deque()
            bucket = self._buckets[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded. Please retry later.",
                )
            bucket.append(now)

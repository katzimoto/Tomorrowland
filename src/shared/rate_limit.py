"""In-memory sliding-window rate limiter for researcher API endpoints (#561)."""

from __future__ import annotations

import threading
import time
from collections import deque

from fastapi import HTTPException


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

    def check(self, user_id: str, *, is_ask_corpus: bool = False) -> None:
        """Record a call. Raises HTTP 429 if the user has exceeded the limit."""
        if not self.enabled:
            return
        limit = self._ask_limit if is_ask_corpus else self._general_limit
        key = f"{user_id}:{'ask_corpus' if is_ask_corpus else 'general'}"
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            # Periodic cleanup: sweep and remove buckets whose entries have
            # all expired.  Runs at most once every 5 minutes to bound dict
            # growth from users who made one call and never returned.
            if now >= self._cleanup_at:
                self._cleanup_at = now + 300
                stale_keys = [
                    k for k, b in self._buckets.items()
                    if not b or b[-1] < cutoff
                ]
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

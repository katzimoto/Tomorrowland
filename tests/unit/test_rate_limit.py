"""Unit tests for AgentRateLimiter (#561)."""

from __future__ import annotations

import threading

import pytest
from fastapi import HTTPException

from shared.rate_limit import AgentRateLimiter


class TestAgentRateLimiterConstruction:
    def test_valid_config_constructs(self) -> None:
        limiter = AgentRateLimiter(
            enabled=True, window_seconds=60, calls_per_window=100, ask_corpus_calls_per_window=20
        )
        assert limiter.enabled is True

    def test_disabled_limiter_constructs(self) -> None:
        limiter = AgentRateLimiter(enabled=False)
        assert limiter.enabled is False

    def test_invalid_window_raises(self) -> None:
        with pytest.raises(ValueError, match="window_seconds"):
            AgentRateLimiter(window_seconds=0)

    def test_invalid_calls_per_window_raises(self) -> None:
        with pytest.raises(ValueError, match="calls_per_window"):
            AgentRateLimiter(calls_per_window=0)

    def test_invalid_ask_corpus_limit_raises(self) -> None:
        with pytest.raises(ValueError, match="ask_corpus_calls_per_window"):
            AgentRateLimiter(ask_corpus_calls_per_window=0)

    def test_negative_window_raises(self) -> None:
        with pytest.raises(ValueError, match="window_seconds"):
            AgentRateLimiter(window_seconds=-1)


class TestAgentRateLimiterDisabled:
    def test_disabled_never_limits(self) -> None:
        limiter = AgentRateLimiter(enabled=False, calls_per_window=1)
        # Should not raise even after many calls
        for _ in range(100):
            limiter.check("user-1")

    def test_disabled_ask_corpus_never_limits(self) -> None:
        limiter = AgentRateLimiter(enabled=False, ask_corpus_calls_per_window=1)
        for _ in range(100):
            limiter.check("user-1", is_ask_corpus=True)


class TestAgentRateLimiterGeneralLimit:
    def test_allows_calls_within_limit(self) -> None:
        limiter = AgentRateLimiter(calls_per_window=3, window_seconds=60)
        limiter.check("user-1")
        limiter.check("user-1")
        limiter.check("user-1")
        # 3 calls — no error

    def test_blocks_over_limit(self) -> None:
        limiter = AgentRateLimiter(calls_per_window=2, window_seconds=60)
        limiter.check("user-1")
        limiter.check("user-1")
        with pytest.raises(HTTPException) as exc_info:
            limiter.check("user-1")
        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in exc_info.value.detail

    def test_different_users_independent(self) -> None:
        limiter = AgentRateLimiter(calls_per_window=1, window_seconds=60)
        limiter.check("user-1")
        # user-2 has a fresh bucket — should not be blocked
        limiter.check("user-2")

    def test_general_and_ask_corpus_independent(self) -> None:
        # Exhaust general limit — ask_corpus should still work
        limiter = AgentRateLimiter(calls_per_window=1, ask_corpus_calls_per_window=5)
        limiter.check("user-1")
        # general is now exhausted
        with pytest.raises(HTTPException):
            limiter.check("user-1")
        # ask_corpus has its own bucket
        limiter.check("user-1", is_ask_corpus=True)


class TestAgentRateLimiterAskCorpusLimit:
    def test_ask_corpus_uses_separate_limit(self) -> None:
        limiter = AgentRateLimiter(
            calls_per_window=100, ask_corpus_calls_per_window=2, window_seconds=60
        )
        limiter.check("user-1", is_ask_corpus=True)
        limiter.check("user-1", is_ask_corpus=True)
        with pytest.raises(HTTPException) as exc_info:
            limiter.check("user-1", is_ask_corpus=True)
        assert exc_info.value.status_code == 429

    def test_ask_corpus_does_not_consume_general_quota(self) -> None:
        limiter = AgentRateLimiter(calls_per_window=2, ask_corpus_calls_per_window=100)
        limiter.check("user-1", is_ask_corpus=True)
        limiter.check("user-1", is_ask_corpus=True)
        # general bucket still clean
        limiter.check("user-1")
        limiter.check("user-1")
        with pytest.raises(HTTPException):
            limiter.check("user-1")


class TestAgentRateLimiterConcurrency:
    def test_concurrent_calls_thread_safe(self) -> None:
        """Race-condition smoke test: N threads each make limit+1 calls."""
        limiter = AgentRateLimiter(calls_per_window=10, window_seconds=60)
        errors: list[Exception] = []

        def make_calls(user_id: str) -> None:
            try:
                for _ in range(10):
                    limiter.check(user_id)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=make_calls, args=(f"u{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Each user has exactly 10 calls — no thread should have raised
        assert not errors


class _FakeRedis:
    """Minimal RedisClient stand-in for distributed rate-limit tests.

    ``allow`` controls the verdict; ``calls`` records every key checked so a
    test can assert the global limiter was (or was not) consulted.
    """

    def __init__(self, allow: bool = True) -> None:
        self.allow = allow
        self.calls: list[tuple[str, int, int]] = []

    def rate_limit_check(self, key: str, window_seconds: int, max_calls: int) -> bool:
        self.calls.append((key, window_seconds, max_calls))
        return self.allow


class TestAgentRateLimiterRedis:
    def test_no_redis_skips_distributed_check(self) -> None:
        """Without a Redis client the limiter is in-process only (back-compat)."""
        limiter = AgentRateLimiter(calls_per_window=2, window_seconds=60)
        limiter.check("user-1")
        limiter.check("user-1")
        with pytest.raises(HTTPException):
            limiter.check("user-1")

    def test_redis_allows_behaves_like_in_process(self) -> None:
        redis = _FakeRedis(allow=True)
        limiter = AgentRateLimiter(calls_per_window=2, window_seconds=60, redis_client=redis)
        limiter.check("user-1")
        limiter.check("user-1")
        # In-process floor still trips at the configured limit.
        with pytest.raises(HTTPException):
            limiter.check("user-1")
        # Redis was consulted on every allowed call with a scoped key.
        assert redis.calls
        assert redis.calls[0][0] == "ratelimit:user-1:general"
        assert redis.calls[0][2] == 2  # max_calls forwarded

    def test_redis_denies_raises_429_under_in_process_limit(self) -> None:
        """Global ceiling: Redis can reject even when the local bucket is clean."""
        redis = _FakeRedis(allow=False)
        limiter = AgentRateLimiter(calls_per_window=100, window_seconds=60, redis_client=redis)
        with pytest.raises(HTTPException) as exc:
            limiter.check("user-1")
        assert exc.value.status_code == 429

    def test_ask_corpus_uses_ask_scope_and_limit(self) -> None:
        redis = _FakeRedis(allow=True)
        limiter = AgentRateLimiter(
            calls_per_window=100,
            ask_corpus_calls_per_window=5,
            window_seconds=60,
            redis_client=redis,
        )
        limiter.check("user-1", is_ask_corpus=True)
        assert redis.calls[-1][0] == "ratelimit:user-1:ask_corpus"
        assert redis.calls[-1][2] == 5  # ask_corpus limit forwarded

    def test_disabled_limiter_skips_redis(self) -> None:
        redis = _FakeRedis(allow=False)
        limiter = AgentRateLimiter(
            enabled=False, calls_per_window=1, window_seconds=60, redis_client=redis
        )
        # Disabled → no raise and Redis never consulted.
        limiter.check("user-1")
        limiter.check("user-1")
        assert redis.calls == []

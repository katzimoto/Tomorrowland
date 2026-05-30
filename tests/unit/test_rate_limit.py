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

"""Tests for shared.redis_client — RedisClient with graceful degradation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from shared.redis_client import RedisClient

# ---------------------------------------------------------------------------
# Initialisation and connection
# ---------------------------------------------------------------------------


class TestRedisClientInit:
    def test_default_url(self) -> None:
        client = RedisClient()
        assert client._url == "redis://redis:6379/0"
        assert client.connected is False

    def test_custom_url(self) -> None:
        client = RedisClient(url="redis://custom:6380/1")
        assert client._url == "redis://custom:6380/1"


class TestRedisClientConnect:
    def test_connect_success_sets_connected_true(self) -> None:
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True

        with patch("redis.Redis.from_url", return_value=mock_redis):
            client = RedisClient()
            client.connect()
            assert client.connected is True

    def test_connect_failure_sets_connected_false(self) -> None:
        with patch(
            "redis.Redis.from_url",
            side_effect=ConnectionRefusedError("no redis"),
        ):
            client = RedisClient()
            client.connect()
            assert client.connected is False

    def test_connect_ping_failure_sets_connected_false(self) -> None:
        mock_redis = MagicMock()
        mock_redis.ping.side_effect = Exception("timeout")

        with patch("redis.Redis.from_url", return_value=mock_redis):
            client = RedisClient()
            client.connect()
            assert client.connected is False

    def test_connect_import_error_graceful(self) -> None:
        """When redis-py import fails, connect() degrades gracefully."""
        client = RedisClient()
        import builtins

        original_import = builtins.__import__
        try:

            def _block_redis(name, *args, **kwargs):
                if name == "redis":
                    raise ImportError("no redis-py")
                return original_import(name, *args, **kwargs)

            builtins.__import__ = _block_redis
            client.connect()
        finally:
            builtins.__import__ = original_import
        assert client.connected is False

    def test_connected_property_reflects_state(self) -> None:
        client = RedisClient()
        assert client.connected is False
        client._connected = True
        assert client.connected is True


# ---------------------------------------------------------------------------
# rate_limit_check
# ---------------------------------------------------------------------------


class TestRateLimitCheck:
    def test_allows_when_not_connected(self) -> None:
        client = RedisClient()
        result = client.rate_limit_check("test-key", 60, 10)
        assert result is True

    def test_allows_when_client_is_none(self) -> None:
        client = RedisClient()
        client._connected = True
        client._client = None
        result = client.rate_limit_check("test-key", 60, 10)
        assert result is True

    def test_allows_when_under_limit(self) -> None:
        mock_redis = MagicMock()
        # Simulate sorted set with 3 existing entries (< max_calls of 10)
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [0, 3, 1, 1]  # cleanup, zcard=3, zadd, expire
        mock_redis.pipeline.return_value = mock_pipe

        client = RedisClient()
        client._connected = True
        client._client = mock_redis

        result = client.rate_limit_check("rl-key", 60, 10)
        assert result is True

    def test_denies_when_over_limit(self) -> None:
        mock_redis = MagicMock()
        # Simulate sorted set with 10 existing entries (== max_calls of 10)
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [0, 10, 1, 1]  # zcard=10, not < 10
        mock_redis.pipeline.return_value = mock_pipe

        client = RedisClient()
        client._connected = True
        client._client = mock_redis

        result = client.rate_limit_check("rl-key", 60, 10)
        assert result is False

    def test_allows_on_redis_error_fail_open(self) -> None:
        mock_redis = MagicMock()
        mock_redis.pipeline.side_effect = Exception("connection lost")

        client = RedisClient()
        client._connected = True
        client._client = mock_redis

        result = client.rate_limit_check("rl-key", 60, 10)
        assert result is True

    def test_uses_correct_window_and_keys(self) -> None:
        mock_redis = MagicMock()
        mock_pipe = MagicMock()
        mock_pipe.execute.return_value = [0, 0, 1, 1]
        mock_redis.pipeline.return_value = mock_pipe

        client = RedisClient()
        client._connected = True
        client._client = mock_redis

        client.rate_limit_check("api:/search", 30, 5)

        # Verify the pipeline was built with correct key
        mock_redis.pipeline.assert_called_once()
        mock_pipe.zremrangebyscore.assert_called_once()  # cleans old entries
        mock_pipe.zcard.assert_called_once()
        mock_pipe.zadd.assert_called_once()
        mock_pipe.expire.assert_called_once()


# ---------------------------------------------------------------------------
# cache_get
# ---------------------------------------------------------------------------


class TestCacheGet:
    def test_returns_none_when_not_connected(self) -> None:
        client = RedisClient()
        assert client.cache_get("key") is None

    def test_returns_none_when_client_is_none(self) -> None:
        client = RedisClient()
        client._connected = True
        client._client = None
        assert client.cache_get("key") is None

    def test_returns_value_when_cached(self) -> None:
        mock_redis = MagicMock()
        mock_redis.get.return_value = b"cached_value"

        client = RedisClient()
        client._connected = True
        client._client = mock_redis

        result = client.cache_get("my-key")
        assert result == "cached_value"
        mock_redis.get.assert_called_once_with("my-key")

    def test_returns_none_on_miss(self) -> None:
        mock_redis = MagicMock()
        mock_redis.get.return_value = None

        client = RedisClient()
        client._connected = True
        client._client = mock_redis

        result = client.cache_get("missing-key")
        assert result is None

    def test_returns_none_on_redis_error(self) -> None:
        mock_redis = MagicMock()
        mock_redis.get.side_effect = Exception("connection lost")

        client = RedisClient()
        client._connected = True
        client._client = mock_redis

        result = client.cache_get("key")
        assert result is None

    def test_handles_str_return_value(self) -> None:
        """If redis returns a str (not bytes), still works."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = "plain_string"

        client = RedisClient()
        client._connected = True
        client._client = mock_redis

        result = client.cache_get("key")
        assert result == "plain_string"


# ---------------------------------------------------------------------------
# cache_set
# ---------------------------------------------------------------------------


class TestCacheSet:
    def test_noops_when_not_connected(self) -> None:
        client = RedisClient()
        client.cache_set("key", "value")  # should not raise

    def test_noops_when_client_is_none(self) -> None:
        client = RedisClient()
        client._connected = True
        client._client = None
        client.cache_set("key", "value")  # should not raise

    def test_stores_with_ttl(self) -> None:
        mock_redis = MagicMock()

        client = RedisClient()
        client._connected = True
        client._client = mock_redis

        client.cache_set("key", "value", ttl_seconds=60)
        mock_redis.setex.assert_called_once_with("key", 60, "value")

    def test_default_ttl_is_30_seconds(self) -> None:
        mock_redis = MagicMock()

        client = RedisClient()
        client._connected = True
        client._client = mock_redis

        client.cache_set("key", "value")
        mock_redis.setex.assert_called_once_with("key", 30, "value")

    def test_swallows_redis_errors(self) -> None:
        mock_redis = MagicMock()
        mock_redis.setex.side_effect = Exception("connection lost")

        client = RedisClient()
        client._connected = True
        client._client = mock_redis

        client.cache_set("key", "value")  # should not raise


# ---------------------------------------------------------------------------
# cache_delete
# ---------------------------------------------------------------------------


class TestCacheDelete:
    def test_noops_when_not_connected(self) -> None:
        client = RedisClient()
        client.cache_delete("key")  # should not raise

    def test_noops_when_client_is_none(self) -> None:
        client = RedisClient()
        client._connected = True
        client._client = None
        client.cache_delete("key")  # should not raise

    def test_deletes_key(self) -> None:
        mock_redis = MagicMock()

        client = RedisClient()
        client._connected = True
        client._client = mock_redis

        client.cache_delete("my-key")
        mock_redis.delete.assert_called_once_with("my-key")

    def test_swallows_redis_errors(self) -> None:
        mock_redis = MagicMock()
        mock_redis.delete.side_effect = Exception("connection lost")

        client = RedisClient()
        client._connected = True
        client._client = mock_redis

        client.cache_delete("key")  # should not raise


# ---------------------------------------------------------------------------
# Full lifecycle test
# ---------------------------------------------------------------------------


class TestRedisClientLifecycle:
    def test_full_cache_lifecycle(self) -> None:
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.get.side_effect = [None, b"my_value"]

        with patch("redis.Redis.from_url", return_value=mock_redis):
            client = RedisClient()
            client.connect()
            assert client.connected is True

            # Miss
            assert client.cache_get("key") is None

            # Set
            client.cache_set("key", "my_value")

            # Hit
            result = client.cache_get("key")
            assert result == "my_value"

            # Delete
            client.cache_delete("key")

    def test_connection_failure_does_not_crash_app(self) -> None:
        """Simulate complete Redis unavailability — all methods should no-op."""
        client = RedisClient()

        # All methods should return safe defaults without raising
        assert client.rate_limit_check("key", 60, 10) is True
        assert client.cache_get("key") is None
        client.cache_set("key", "value")  # no raise
        client.cache_delete("key")  # no raise

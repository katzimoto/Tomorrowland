"""Tests for shared.config_cache — ConfigCache and helper functions."""

from __future__ import annotations

import threading
import time
import uuid
from unittest.mock import MagicMock

import sqlalchemy as sa
from sqlalchemy import Engine

from shared.config_cache import (
    ConfigCache,
    _admins_group_cache,
    _system_config_cache,
    get_cached_admins_group_id,
    get_cached_config,
    invalidate_config_cache,
)

# ---------------------------------------------------------------------------
# ConfigCache — basic get/set/invalidate
# ---------------------------------------------------------------------------


class TestConfigCache:
    def test_get_miss_returns_none(self) -> None:
        cache = ConfigCache()
        assert cache.get("nonexistent") is None

    def test_set_and_get_roundtrip(self) -> None:
        cache = ConfigCache()
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_set_overwrites_existing(self) -> None:
        cache = ConfigCache()
        cache.set("key", "old")
        cache.set("key", "new")
        assert cache.get("key") == "new"

    def test_set_none_value(self) -> None:
        cache = ConfigCache()
        cache.set("key", None)
        assert cache.get("key") is None

    def test_set_int_value(self) -> None:
        cache = ConfigCache()
        cache.set("key", 42)
        assert cache.get("key") == 42

    def test_set_dict_value(self) -> None:
        cache = ConfigCache()
        value = {"nested": {"a": 1}}
        cache.set("key", value)
        assert cache.get("key") == value

    def test_invalidate_removes_key(self) -> None:
        cache = ConfigCache()
        cache.set("key", "value")
        cache.invalidate("key")
        assert cache.get("key") is None

    def test_invalidate_missing_key_no_error(self) -> None:
        cache = ConfigCache()
        cache.invalidate("nonexistent")  # should not raise

    def test_invalidate_all_clears_everything(self) -> None:
        cache = ConfigCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.invalidate_all()
        assert cache.get("a") is None
        assert cache.get("b") is None
        assert cache.get("c") is None


# ---------------------------------------------------------------------------
# ConfigCache — TTL / expiry
# ---------------------------------------------------------------------------


class TestConfigCacheTTL:
    def test_entry_expires_after_ttl(self) -> None:
        cache = ConfigCache(ttl_seconds=0.01)
        cache.set("key", "value")
        time.sleep(0.02)
        assert cache.get("key") is None

    def test_entry_still_valid_before_ttl(self) -> None:
        cache = ConfigCache(ttl_seconds=60.0)
        cache.set("key", "value")
        assert cache.get("key") == "value"

    def test_get_removes_expired_entry(self) -> None:
        cache = ConfigCache(ttl_seconds=0.01)
        cache.set("key", "value")
        time.sleep(0.02)
        cache.get("key")  # triggers expiry + deletion
        # Second get should still be None (entry was deleted)
        assert cache.get("key") is None


# ---------------------------------------------------------------------------
# ConfigCache — max_size / eviction
# ---------------------------------------------------------------------------


class TestConfigCacheMaxSize:
    def test_fifo_eviction_at_max_size(self) -> None:
        cache = ConfigCache(max_size=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)  # should evict "a" (FIFO)
        assert cache.get("a") is None
        assert cache.get("b") == 2
        assert cache.get("c") == 3
        assert cache.get("d") == 4

    def test_no_eviction_when_overwriting_existing(self) -> None:
        cache = ConfigCache(max_size=2)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("a", 10)  # overwrite, not insert — no eviction
        assert cache.get("a") == 10
        assert cache.get("b") == 2
        assert len(cache._store) == 2

    def test_default_max_size_is_large(self) -> None:
        cache = ConfigCache()
        assert cache._max_size == 256


# ---------------------------------------------------------------------------
# ConfigCache — periodic cleanup
# ---------------------------------------------------------------------------


class TestConfigCacheCleanup:
    def test_periodic_cleanup_sweeps_expired(self) -> None:
        cache = ConfigCache(ttl_seconds=-0.1)  # all entries instantly expired
        cache.set("a", 1)
        cache.set("b", 2)

        # Force cleanup by faking _cleanup_at to be in the past
        cache._cleanup_at = 0
        cache.get("a")  # triggers cleanup

        # After cleanup, all expired entries should be gone
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_cleanup_not_triggered_before_interval(self) -> None:
        cache = ConfigCache(ttl_seconds=-0.1)
        cache.set("a", 1)
        # _cleanup_at is set to now + 300 on init, so get() won't trigger cleanup yet
        result = cache.get("a")
        # Entry is expired, so get returns None, but cleanup isn't triggered
        assert result is None
        # "a" was removed by the normal expiry check, not by cleanup sweep


# ---------------------------------------------------------------------------
# ConfigCache — thread safety
# ---------------------------------------------------------------------------


class TestConfigCacheThreadSafety:
    def test_concurrent_get_set_does_not_corrupt(self) -> None:
        cache = ConfigCache(max_size=1000)
        errors: list[Exception] = []

        def writer() -> None:
            for i in range(200):
                try:
                    cache.set(f"key-{i}", i)
                except Exception as e:
                    errors.append(e)

        def reader() -> None:
            for _ in range(200):
                try:
                    cache.get("key-0")
                except Exception as e:
                    errors.append(e)

        threads = []
        for _ in range(4):
            threads.append(threading.Thread(target=writer))
            threads.append(threading.Thread(target=reader))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread-safety errors: {errors}"

    def test_concurrent_invalidate_does_not_corrupt(self) -> None:
        cache = ConfigCache()
        cache.set("shared", "value")
        errors: list[Exception] = []

        def invalidator() -> None:
            for _ in range(100):
                try:
                    cache.invalidate("shared")
                    cache.set("shared", "new")
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=invalidator) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread-safety errors: {errors}"


# ---------------------------------------------------------------------------
# get_cached_config helper
# ---------------------------------------------------------------------------


class TestGetCachedConfig:
    def setup_method(self) -> None:
        _system_config_cache.invalidate_all()

    def test_returns_cached_value_on_hit(self) -> None:
        _system_config_cache.set("my.key", "cached_value")
        mock_conn = MagicMock()
        result = get_cached_config(mock_conn, "my.key")
        assert result == "cached_value"
        mock_conn.execute.assert_not_called()

    def test_fetches_from_db_on_miss(self) -> None:
        mock_conn = MagicMock()
        mock_exec = MagicMock()
        mock_mappings = MagicMock()
        mock_mappings.first.return_value = {"value": "db_value"}
        mock_exec.mappings.return_value = mock_mappings
        mock_conn.execute.return_value = mock_exec

        result = get_cached_config(mock_conn, "db.key")

        assert result == "db_value"
        mock_conn.execute.assert_called_once()

    def test_returns_none_when_db_row_missing(self) -> None:
        mock_conn = MagicMock()
        mock_exec = MagicMock()
        mock_mappings = MagicMock()
        mock_mappings.first.return_value = None
        mock_exec.mappings.return_value = mock_mappings
        mock_conn.execute.return_value = mock_exec

        result = get_cached_config(mock_conn, "missing.key")

        assert result is None

    def test_caches_db_result_for_next_call(self) -> None:
        mock_conn = MagicMock()
        mock_exec = MagicMock()
        mock_mappings = MagicMock()
        mock_mappings.first.return_value = {"value": "db_value"}
        mock_exec.mappings.return_value = mock_mappings
        mock_conn.execute.return_value = mock_exec

        # First call — DB hit
        result1 = get_cached_config(mock_conn, "test.key")
        assert result1 == "db_value"
        assert mock_conn.execute.call_count == 1

        # Second call — cache hit, no DB call
        result2 = get_cached_config(mock_conn, "test.key")
        assert result2 == "db_value"
        assert mock_conn.execute.call_count == 1  # still only one call

    def test_handles_null_db_value(self) -> None:
        """When the DB row has value=NULL, returns None.

        Note: None is also the cache-miss sentinel, so a cached None
        still triggers a DB hit on the next call. This is an intentional
        design trade-off — config values are rarely NULL.
        """
        mock_conn = MagicMock()
        mock_exec = MagicMock()
        mock_mappings = MagicMock()
        mock_mappings.first.return_value = {"value": None}
        mock_exec.mappings.return_value = mock_mappings
        mock_conn.execute.return_value = mock_exec

        result = get_cached_config(mock_conn, "nullable.key")
        assert result is None
        # Second call also hits DB because None == cache miss
        result2 = get_cached_config(mock_conn, "nullable.key")
        assert result2 is None
        assert mock_conn.execute.call_count == 2


# ---------------------------------------------------------------------------
# get_cached_admins_group_id helper
# ---------------------------------------------------------------------------


class TestGetCachedAdminsGroupId:
    def setup_method(self) -> None:
        _admins_group_cache.invalidate_all()

    def test_returns_cached_on_hit(self) -> None:
        _admins_group_cache.set("admins_group_id", "uuid-12345")
        mock_conn = MagicMock()
        result = get_cached_admins_group_id(mock_conn)
        assert result == "uuid-12345"
        mock_conn.execute.assert_not_called()

    def test_fetches_from_db_on_miss(self) -> None:
        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar.return_value = "db-uuid-67890"

        result = get_cached_admins_group_id(mock_conn)

        assert result == "db-uuid-67890"
        mock_conn.execute.assert_called_once()

    def test_returns_none_when_no_admins_group(self) -> None:
        mock_conn = MagicMock()
        mock_conn.execute.return_value.scalar.return_value = None

        result = get_cached_admins_group_id(mock_conn)

        assert result is None


# ---------------------------------------------------------------------------
# invalidate_config_cache helper
# ---------------------------------------------------------------------------


class TestInvalidateConfigCache:
    def setup_method(self) -> None:
        _system_config_cache.invalidate_all()

    def test_invalidate_single_key(self) -> None:
        _system_config_cache.set("key1", "val1")
        _system_config_cache.set("key2", "val2")

        invalidate_config_cache("key1")

        assert _system_config_cache.get("key1") is None
        assert _system_config_cache.get("key2") == "val2"

    def test_invalidate_all_when_key_is_none(self) -> None:
        _system_config_cache.set("key1", "val1")
        _system_config_cache.set("key2", "val2")

        invalidate_config_cache(None)

        assert _system_config_cache.get("key1") is None
        assert _system_config_cache.get("key2") is None

    def test_invalidate_all_when_key_omitted(self) -> None:
        _system_config_cache.set("key1", "val1")
        _system_config_cache.set("key2", "val2")

        invalidate_config_cache()

        assert _system_config_cache.get("key1") is None
        assert _system_config_cache.get("key2") is None


# ---------------------------------------------------------------------------
# Integration with real SQLite (via migrated_engine fixture)
# ---------------------------------------------------------------------------


class TestConfigCacheWithDB:
    def test_get_cached_config_reads_real_db(self, migrated_engine: Engine) -> None:
        _system_config_cache.invalidate_all()

        # Seed a config value
        with migrated_engine.begin() as conn:
            conn.execute(
                sa.text("INSERT INTO system_config (key, value) VALUES (:k, :v)").bindparams(
                    sa.bindparam("v", type_=sa.JSON())
                ),
                {"k": "test.feature", "v": "enabled"},
            )

        with migrated_engine.begin() as conn:
            result = get_cached_config(conn, "test.feature")
            assert result == "enabled"

    def test_get_cached_config_returns_none_for_missing_key(self, migrated_engine: Engine) -> None:
        _system_config_cache.invalidate_all()

        with migrated_engine.begin() as conn:
            result = get_cached_config(conn, "does.not.exist")
            assert result is None

    def test_get_cached_admins_group_reads_real_db(self, migrated_engine: Engine) -> None:
        _admins_group_cache.invalidate_all()

        # Seed an admins group since tests start with a clean DB
        group_id = str(uuid.uuid4())
        with migrated_engine.begin() as conn:
            conn.execute(
                sa.text("INSERT INTO groups (id, name) VALUES (:id, 'admins')"),
                {"id": group_id},
            )

        with migrated_engine.begin() as conn:
            result = get_cached_admins_group_id(conn)
            assert result is not None
            assert len(result) > 0

    def test_invalidate_then_refetch_from_db(self, migrated_engine: Engine) -> None:
        _system_config_cache.invalidate_all()

        _json_bind = sa.bindparam("v", type_=sa.JSON())

        # Seed initial value
        with migrated_engine.begin() as conn:
            conn.execute(
                sa.text("INSERT INTO system_config (key, value) VALUES (:k, :v)").bindparams(
                    _json_bind
                ),
                {"k": "mutable.key", "v": "old"},
            )

        # Cache it
        with migrated_engine.begin() as conn:
            result1 = get_cached_config(conn, "mutable.key")
            assert result1 == "old"

        # Update DB value
        with migrated_engine.begin() as conn:
            conn.execute(
                sa.text("UPDATE system_config SET value = :v WHERE key = :k").bindparams(
                    _json_bind
                ),
                {"k": "mutable.key", "v": "new"},
            )

        # Before invalidation, still returns cached "old"
        with migrated_engine.begin() as conn:
            result_cached = get_cached_config(conn, "mutable.key")
            assert result_cached == "old"

        # Invalidate and re-read
        invalidate_config_cache("mutable.key")
        with migrated_engine.begin() as conn:
            result2 = get_cached_config(conn, "mutable.key")
            assert result2 == "new"

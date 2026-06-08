"""Lightweight TTL cache for database-backed configuration values.

Avoids repeated ``SELECT … FROM system_config WHERE key = …`` lookups on every
API request by caching values in-process with a configurable TTL (default 30 s).

Thread-safe: single lock per cache instance.
"""

from __future__ import annotations

import contextlib
import threading
import time
from typing import Any


class ConfigCache:
    """In-memory cache with per-key time-to-live (TTL)."""

    def __init__(self, ttl_seconds: float = 30.0, max_size: int = 256) -> None:
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._cleanup_at = time.monotonic() + 300.0

    def get(self, key: str) -> Any:
        """Return *None* (cache miss) or the stored value."""
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires, value = entry
            if now >= expires:
                del self._store[key]
                return None
            # Periodic cleanup: evict all expired entries at most once every 5 min.
            if now >= self._cleanup_at:
                self._cleanup_at = now + 300.0
                stale = [k for k, (exp, _) in self._store.items() if now >= exp]
                for k in stale:
                    del self._store[k]
            return value

    def set(self, key: str, value: Any) -> None:
        """Store *value* for *key* with the configured TTL."""
        now = time.monotonic()
        with self._lock:
            if len(self._store) >= self._max_size and key not in self._store:
                # Evict the oldest entry (simple FIFO, good enough for config).
                oldest = next(iter(self._store))
                del self._store[oldest]
            self._store[key] = (now + self._ttl, value)

    def invalidate(self, key: str) -> None:
        """Explicitly remove a cached key."""
        with self._lock:
            self._store.pop(key, None)

    def invalidate_all(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._store.clear()


# Shared instance with a 30-second TTL — fast enough to pick up admin config
# changes within half a minute but avoids per-request DB round-trips.
_system_config_cache = ConfigCache(ttl_seconds=30.0)
_admins_group_cache = ConfigCache(ttl_seconds=60.0)  # rarely changes


def get_cached_config(connection: Any, key: str) -> str | None:
    """Return a cached system_config value, refreshing from DB on miss.

    Note: ``None`` is both "cache miss" and "cached null value". When a
    system_config row stores ``value=NULL``, the next call hits the DB again
    because we cannot distinguish a stored None from a missing entry. This is
    an intentional trade-off — system_config values are rarely NULL in practice.
    """
    import json

    import sqlalchemy as sa

    cached = _system_config_cache.get(key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    row = (
        connection.execute(
            sa.text("SELECT value FROM system_config WHERE key = :key"),
            {"key": key},
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    raw_value = row["value"]
    if raw_value is None:
        value: str | None = None
    else:
        # system_config.value is sa.JSON().  Raw text queries bypass type
        # processors, so SQLite returns the JSON-serialised string (e.g.
        # '"old"' for the Python string "old").  Try to deserialise here so
        # both SQLite and PostgreSQL callers receive the same plain value.
        if isinstance(raw_value, str):
            with contextlib.suppress(json.JSONDecodeError, ValueError):
                raw_value = json.loads(raw_value)
        if isinstance(raw_value, (dict, list)):
            value = json.dumps(raw_value)
        elif isinstance(raw_value, bool):
            value = "true" if raw_value else "false"
        else:
            value = str(raw_value)
    _system_config_cache.set(key, value)
    return value


def get_cached_admins_group_id(connection: Any) -> str | None:
    """Return the cached admins group ID, refreshing from DB on miss."""
    import sqlalchemy as sa

    key = "admins_group_id"
    cached = _admins_group_cache.get(key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    admins_id = connection.execute(
        sa.text("SELECT id FROM groups WHERE name = 'admins'"),
    ).scalar()
    value: str | None = str(admins_id) if admins_id else None
    _admins_group_cache.set(key, value)
    return value


def invalidate_config_cache(key: str | None = None) -> None:
    """Invalidate one or all cached config entries (call after admin writes)."""
    if key is not None:
        _system_config_cache.invalidate(key)
    else:
        _system_config_cache.invalidate_all()

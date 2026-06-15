"""Tests for resolve_feature_flag — DB config overrides env defaults."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Engine

from services.api._helpers import resolve_feature_flag
from shared.config import Settings
from shared.config_cache import invalidate_config_cache

_KEY = "feature.document_chat_hierarchy_expansion"
_ATTR = "feature_document_chat_hierarchy_expansion"
_JSON = sa.bindparam("v", type_=sa.JSON())


def _set_config(engine: Engine, value: bool) -> None:
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE system_config SET value = :v WHERE key = :k").bindparams(_JSON),
            {"k": _KEY, "v": value},
        )
    invalidate_config_cache(_KEY)


def test_resolves_env_default_when_no_override(migrated_engine: Engine) -> None:
    # Remove any seeded row so only the env default applies.
    with migrated_engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM system_config WHERE key = :k"), {"k": _KEY})
    invalidate_config_cache(_KEY)
    settings = Settings(_env_file=None)  # ships dark by default

    with migrated_engine.begin() as conn:
        assert resolve_feature_flag(conn, settings, attr=_ATTR, config_key=_KEY) is False


def test_db_override_enables_flag(migrated_engine: Engine) -> None:
    settings = Settings(_env_file=None)
    _set_config(migrated_engine, True)

    with migrated_engine.begin() as conn:
        assert resolve_feature_flag(conn, settings, attr=_ATTR, config_key=_KEY) is True


def test_db_override_disables_flag(migrated_engine: Engine) -> None:
    # Even when the env default is on, an explicit DB false wins.
    settings = Settings(_env_file=None, feature_document_chat_hierarchy_expansion=True)
    _set_config(migrated_engine, False)

    with migrated_engine.begin() as conn:
        assert resolve_feature_flag(conn, settings, attr=_ATTR, config_key=_KEY) is False

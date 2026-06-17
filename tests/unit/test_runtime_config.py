"""Tests for apply_model_config_overrides — translation/QE bundle overrides."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import Engine

from shared.config import Settings
from shared.config_cache import invalidate_config_cache
from shared.runtime_config import apply_model_config_overrides

_JSON = sa.bindparam("v", type_=sa.JSON())


def _set(engine: Engine, key: str, value: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE system_config SET value = :v WHERE key = :k").bindparams(_JSON),
            {"k": key, "v": value},
        )
    invalidate_config_cache(key)


def test_empty_sentinel_keeps_env_default(migrated_engine: Engine) -> None:
    invalidate_config_cache()
    settings = Settings(_env_file=None, translation_qe_model_path="/env/qe")
    # Seeded model.* defaults are empty strings → no override.
    with migrated_engine.connect() as conn:
        result = apply_model_config_overrides(settings, conn)
    assert result is settings
    assert result.translation_qe_model_path == "/env/qe"


def test_override_applies_to_matching_fields(migrated_engine: Engine) -> None:
    invalidate_config_cache()
    settings = Settings(_env_file=None, translation_qe_model_path="/env/qe")
    _set(migrated_engine, "model.translation_qe_model_path", "/admin/qe")
    _set(migrated_engine, "model.translation_high_bundle_path", "/admin/opus")

    with migrated_engine.connect() as conn:
        result = apply_model_config_overrides(settings, conn)

    assert result is not settings  # a copy was made
    assert result.translation_qe_model_path == "/admin/qe"
    assert result.translation_high_provider_bundle_path == "/admin/opus"

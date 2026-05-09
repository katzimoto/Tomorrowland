from __future__ import annotations

from pathlib import Path

from shared.config import Settings
from shared.feature_flags import ENV_FEATURE_TO_CONFIG_KEY, SYSTEM_CONFIG_DEFAULTS


def test_settings_load_from_environment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("AUTO_ENRICH_THRESHOLD", "7")

    settings = Settings()

    assert settings.app_env == "test"
    assert settings.auto_enrich_threshold == 7
    assert settings.elastic_url == "http://elasticsearch:9200"


def test_env_example_matches_settings_and_feature_defaults() -> None:
    env_keys = {
        line.split("=", 1)[0]
        for line in Path(".env.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }

    expected_keys = {field.upper() for field in Settings.model_fields}

    assert expected_keys <= env_keys
    assert set(ENV_FEATURE_TO_CONFIG_KEY) <= env_keys
    assert set(ENV_FEATURE_TO_CONFIG_KEY.values()) <= set(SYSTEM_CONFIG_DEFAULTS)


def test_cors_origins_default_to_frontend_origin() -> None:
    settings = Settings(_env_file=None)

    assert settings.cors_origin_list == ["http://localhost:8080"]


def test_cors_origins_parse_comma_separated_values() -> None:
    settings = Settings(
        cors_origins=" http://localhost:8080,https://neverland.example ,, ", _env_file=None
    )

    assert settings.cors_origin_list == ["http://localhost:8080", "https://neverland.example"]


def test_cors_origins_empty_values_are_ignored() -> None:
    settings = Settings(cors_origins=" , ,, ", _env_file=None)

    assert settings.cors_origin_list == []

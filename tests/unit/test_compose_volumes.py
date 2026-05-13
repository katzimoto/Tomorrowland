"""Validate Docker Compose volume name configurability."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, cast

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
COMPOSE_AIRGAP_FILE = REPO_ROOT / "docker-compose.airgap.yml"

# Expected internal volume keys in each compose file
STANDARD_VOLUMES = {
    "files_data": "/data",
    "postgres_data": "/var/lib/postgresql/data",
    "kafka_data": "/var/lib/redpanda/data",
    "elasticsearch_data": "/usr/share/elasticsearch/data",
    "qdrant_data": "/qdrant/storage",
    "libretranslate_data": "/home/libretranslate/.local",
    "ollama_data": "/root/.ollama",
}

STANDARD_MONITORING_VOLUMES = {
    "prometheus_data": "/prometheus",
    "grafana_data": "/var/lib/grafana",
}

AIRGAP_VOLUMES = {
    "files_data": "/data",
    "postgres_data": "/var/lib/postgresql/data",
    "kafka_data": "/var/lib/redpanda/data",
    "elasticsearch_data": "/usr/share/elasticsearch/data",
    "qdrant_data": "/qdrant/storage",
    "libretranslate_data": "/home/libretranslate/.local",
    "ollama_data": "/root/.ollama",
}


def _compose_config(
    compose_file: Path,
    env: dict[str, str] | None = None,
    profiles: list[str] | None = None,
) -> dict[str, Any]:
    """Run docker compose config --format json and return the parsed result."""
    cmd = [
        "docker",
        "compose",
        "-f",
        str(compose_file),
    ]
    for profile in profiles or []:
        cmd += ["--profile", profile]
    cmd += ["config", "--format", "json"]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, **(env or {})},
    )
    if result.returncode != 0:
        pytest.fail(f"docker compose config failed:\n{result.stderr}")
    return cast("dict[str, Any]", json.loads(result.stdout))


def _service_mount_target(
    config: dict[str, Any],
    service_name: str,
    volume_key: str,
) -> str | None:
    """Return the container target path for a named volume mount, or None."""
    service = config.get("services", {}).get(service_name, {})
    for volume in service.get("volumes", []):
        if isinstance(volume, dict):
            if volume.get("type") == "volume" and volume.get("source") == volume_key:
                return volume.get("target")
        elif isinstance(volume, str):
            # short syntax: source:target[:mode]
            parts = volume.split(":")
            if len(parts) >= 2 and parts[0] == volume_key:
                return parts[1]
    return None


def _volume_names(config: dict[str, Any]) -> dict[str, str]:
    """Return mapping of internal volume key -> actual Docker volume name."""
    volumes = config.get("volumes", {})
    result: dict[str, str] = {}
    for key, spec in volumes.items():
        if isinstance(spec, dict):
            result[key] = spec.get("name", key)
        else:
            result[key] = key
    return result


@pytest.mark.no_cover
class TestComposeVolumeDefaults:
    """Default volume name rendering."""

    def test_standard_compose_defaults(self) -> None:
        config = _compose_config(COMPOSE_FILE)
        names = _volume_names(config)
        for key, default_name in [
            ("files_data", "tomorrowland_files_data"),
            ("postgres_data", "tomorrowland_postgres_data"),
            ("kafka_data", "tomorrowland_kafka_data"),
            ("elasticsearch_data", "tomorrowland_elasticsearch_data"),
            ("qdrant_data", "tomorrowland_qdrant_data"),
            ("libretranslate_data", "tomorrowland_libretranslate_data"),
            ("ollama_data", "tomorrowland_ollama_data"),
        ]:
            assert names.get(key) == default_name, f"{key} default mismatch"

    def test_standard_compose_monitoring_defaults(self) -> None:
        config = _compose_config(COMPOSE_FILE, profiles=["monitoring"])
        names = _volume_names(config)
        assert names.get("prometheus_data") == "tomorrowland_prometheus_data"
        assert names.get("grafana_data") == "tomorrowland_grafana_data"

    def test_airgap_compose_defaults(self) -> None:
        config = _compose_config(COMPOSE_AIRGAP_FILE)
        names = _volume_names(config)
        for key, default_name in [
            ("files_data", "tomorrowland_files_data"),
            ("postgres_data", "tomorrowland_postgres_data"),
            ("kafka_data", "tomorrowland_kafka_data"),
            ("elasticsearch_data", "tomorrowland_elasticsearch_data"),
            ("qdrant_data", "tomorrowland_qdrant_data"),
            ("libretranslate_data", "tomorrowland_libretranslate_data"),
            ("ollama_data", "tomorrowland_ollama_data"),
        ]:
            assert names.get(key) == default_name, f"{key} default mismatch"

    @pytest.mark.parametrize("key,expected_target", list(STANDARD_VOLUMES.items()))
    def test_standard_mount_targets(self, key: str, expected_target: str) -> None:
        config = _compose_config(COMPOSE_FILE)
        # Find which service mounts this volume
        found = False
        for service_name in config.get("services", {}):
            target = _service_mount_target(config, service_name, key)
            if target == expected_target:
                found = True
                break
        assert found, f"No service mounts {key} to {expected_target}"

    @pytest.mark.parametrize("key,expected_target", list(STANDARD_MONITORING_VOLUMES.items()))
    def test_standard_monitoring_mount_targets(self, key: str, expected_target: str) -> None:
        config = _compose_config(COMPOSE_FILE, profiles=["monitoring"])
        found = False
        for service_name in config.get("services", {}):
            target = _service_mount_target(config, service_name, key)
            if target == expected_target:
                found = True
                break
        assert found, f"No service mounts {key} to {expected_target}"

    @pytest.mark.parametrize("key,expected_target", list(AIRGAP_VOLUMES.items()))
    def test_airgap_mount_targets(self, key: str, expected_target: str) -> None:
        config = _compose_config(COMPOSE_AIRGAP_FILE)
        found = False
        for service_name in config.get("services", {}):
            target = _service_mount_target(config, service_name, key)
            if target == expected_target:
                found = True
                break
        assert found, f"No service mounts {key} to {expected_target}"


@pytest.mark.no_cover
class TestComposeVolumeCustomization:
    """Custom volume name rendering via env vars."""

    def test_standard_compose_custom_names(self) -> None:
        env = {
            "TOMORROWLAND_FILES_VOLUME": "my_files",
            "TOMORROWLAND_POSTGRES_VOLUME": "my_postgres",
            "TOMORROWLAND_QDRANT_VOLUME": "my_qdrant",
        }
        config = _compose_config(COMPOSE_FILE, env)
        names = _volume_names(config)
        assert names["files_data"] == "my_files"
        assert names["postgres_data"] == "my_postgres"
        assert names["qdrant_data"] == "my_qdrant"
        # Unchanged volumes should still use defaults
        assert names["elasticsearch_data"] == "tomorrowland_elasticsearch_data"

    def test_standard_compose_monitoring_custom_names(self) -> None:
        env = {
            "TOMORROWLAND_PROMETHEUS_VOLUME": "my_prometheus",
            "TOMORROWLAND_GRAFANA_VOLUME": "my_grafana",
        }
        config = _compose_config(COMPOSE_FILE, env, profiles=["monitoring"])
        names = _volume_names(config)
        assert names["prometheus_data"] == "my_prometheus"
        assert names["grafana_data"] == "my_grafana"

    def test_airgap_compose_custom_names(self) -> None:
        env = {
            "TOMORROWLAND_FILES_VOLUME": "airgap_files",
            "TOMORROWLAND_OLLAMA_VOLUME": "airgap_ollama",
        }
        config = _compose_config(COMPOSE_AIRGAP_FILE, env)
        names = _volume_names(config)
        assert names["files_data"] == "airgap_files"
        assert names["ollama_data"] == "airgap_ollama"
        assert names["postgres_data"] == "tomorrowland_postgres_data"

    def test_standard_mount_targets_unchanged_with_custom_names(self) -> None:
        env = {
            "TOMORROWLAND_FILES_VOLUME": "custom_files",
            "TOMORROWLAND_POSTGRES_VOLUME": "custom_postgres",
        }
        config = _compose_config(COMPOSE_FILE, env)
        for key, expected_target in STANDARD_VOLUMES.items():
            found = False
            for service_name in config.get("services", {}):
                target = _service_mount_target(config, service_name, key)
                if target == expected_target:
                    found = True
                    break
            assert found, f"Mount target changed for {key}"

    def test_standard_monitoring_mount_targets_unchanged_with_custom_names(self) -> None:
        env = {
            "TOMORROWLAND_PROMETHEUS_VOLUME": "custom_prometheus",
            "TOMORROWLAND_GRAFANA_VOLUME": "custom_grafana",
        }
        config = _compose_config(COMPOSE_FILE, env, profiles=["monitoring"])
        for key, expected_target in STANDARD_MONITORING_VOLUMES.items():
            found = False
            for service_name in config.get("services", {}):
                target = _service_mount_target(config, service_name, key)
                if target == expected_target:
                    found = True
                    break
            assert found, f"Mount target changed for {key}"

    def test_airgap_mount_targets_unchanged_with_custom_names(self) -> None:
        env = {
            "TOMORROWLAND_FILES_VOLUME": "custom_files",
        }
        config = _compose_config(COMPOSE_AIRGAP_FILE, env)
        for key, expected_target in AIRGAP_VOLUMES.items():
            found = False
            for service_name in config.get("services", {}):
                target = _service_mount_target(config, service_name, key)
                if target == expected_target:
                    found = True
                    break
            assert found, f"Mount target changed for {key}"

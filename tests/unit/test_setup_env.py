"""Validate scripts/setup-env.sh behavior."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "setup-env.sh"

REQUIRED_KEYS = {
    "APP_ENV",
    "POSTGRES_PASSWORD",
    "JWT_SECRET",
    "POSTGRES_URL",
    "KAFKA_BROKER",
    "ELASTIC_URL",
    "QDRANT_URL",
    "FILES_ROOT",
    "CORS_ORIGINS",
    "LIBRETRANSLATE_URL",
    "OLLAMA_URL",
    "OLLAMA_MODEL",
    "AUTH_PROVIDER",
    "FEATURE_RAG_QA",
    "FEATURE_SUMMARIZATION",
    "API_PORT",
    "FRONTEND_PORT",
    "POSTGRES_PORT",
    "TOMORROWLAND_FILES_VOLUME",
    "TOMORROWLAND_POSTGRES_VOLUME",
}

AIRGAP_REQUIRED_KEYS = {
    "TOMORROWLAND_BACKEND_IMAGE",
    "TOMORROWLAND_FRONTEND_IMAGE",
    "TOMORROWLAND_LIBRETRANSLATE_IMAGE",
    "TOMORROWLAND_FOLDER_SOURCE_HOST_PATH",
    "TOMORROWLAND_FOLDER_SOURCE_CONTAINER_PATH",
}

PLACEHOLDER_SECRETS = {
    "change-me-jwt-secret",
    "change-me-postgres-password",
    "changeme",
    "secret",
    "password",
}


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, **(env or {})},
    )


def _parse_env(content: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


class TestSetupEnvScript:
    """Basic script behavior."""

    def test_syntax_check_passes(self) -> None:
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stderr

    def test_help_flag(self) -> None:
        result = _run("--help")
        assert result.returncode == 0
        assert "Usage:" in result.stdout

    def test_defaults_creates_file(self, tmp_path: Path) -> None:
        out = tmp_path / "test.env"
        result = _run("--defaults", "--output", str(out))
        assert result.returncode == 0, result.stderr
        assert out.exists()
        content = out.read_text()
        env = _parse_env(content)
        for key in REQUIRED_KEYS:
            assert key in env, f"missing key: {key}"

    def test_defaults_does_not_overwrite(self, tmp_path: Path) -> None:
        out = tmp_path / "test.env"
        out.write_text("existing")
        result = _run("--defaults", "--output", str(out))
        assert result.returncode != 0
        assert "already exists" in result.stderr

    def test_force_overwrites(self, tmp_path: Path) -> None:
        out = tmp_path / "test.env"
        out.write_text("existing")
        result = _run("--defaults", "--output", str(out), "--force")
        assert result.returncode == 0, result.stderr
        content = out.read_text()
        assert "APP_ENV=prod" in content

    def test_print_to_stdout(self) -> None:
        result = _run("--defaults", "--print")
        assert result.returncode == 0, result.stderr
        assert "APP_ENV=prod" in result.stdout
        env = _parse_env(result.stdout)
        for key in REQUIRED_KEYS:
            assert key in env, f"missing key: {key}"

    def test_secrets_are_not_placeholders(self, tmp_path: Path) -> None:
        out = tmp_path / "test.env"
        result = _run("--defaults", "--output", str(out))
        assert result.returncode == 0
        env = _parse_env(out.read_text())
        # Check secret values, not keys
        secret_values = [
            env.get("POSTGRES_PASSWORD", "").lower(),
            env.get("JWT_SECRET", "").lower(),
            env.get("LDAP_BIND_PASSWORD", "").lower(),
        ]
        for val in secret_values:
            if not val:
                continue
            for ph in PLACEHOLDER_SECRETS:
                assert ph not in val, f"placeholder secret found in value: {ph}"

    def test_ports_are_numeric(self, tmp_path: Path) -> None:
        out = tmp_path / "test.env"
        result = _run("--defaults", "--output", str(out))
        assert result.returncode == 0
        env = _parse_env(out.read_text())
        for key in [
            "API_PORT",
            "FRONTEND_PORT",
            "POSTGRES_PORT",
            "KAFKA_PORT",
            "ELASTICSEARCH_PORT",
            "QDRANT_PORT",
            "LIBRETRANSLATE_PORT",
            "OLLAMA_PORT",
        ]:
            assert env[key].isdigit(), f"non-numeric port: {key}={env[key]}"
            assert 1 <= int(env[key]) <= 65535

    def test_booleans_are_valid(self, tmp_path: Path) -> None:
        out = tmp_path / "test.env"
        result = _run("--defaults", "--output", str(out))
        assert result.returncode == 0
        env = _parse_env(out.read_text())
        for key in [
            "FEATURE_DOCUMENT_COMMENTS",
            "FEATURE_RAG_QA",
            "FEATURE_SUMMARIZATION",
            "FEATURE_ENTITY_EXTRACTION",
            "FEATURE_ANNOTATIONS",
            "FEATURE_SUBSCRIPTIONS",
            "FEATURE_EXPERTISE_MAP",
            "FEATURE_RELATED_DOCS",
            "FEATURE_AUTO_TAGGING",
            "EMBEDDING_PROVIDER_UNSAFE_ALLOW_TEST_IN_PROD",
        ]:
            assert env[key] in {"true", "false"}, f"invalid boolean: {key}={env[key]}"

    def test_airgap_mode(self, tmp_path: Path) -> None:
        out = tmp_path / "test.airgap.env"
        result = _run("--defaults", "--airgap", "--output", str(out))
        assert result.returncode == 0, result.stderr
        env = _parse_env(out.read_text())
        for key in AIRGAP_REQUIRED_KEYS:
            assert key in env, f"missing airgap key: {key}"

    @pytest.mark.skipif(shutil.which("docker") is None, reason="docker not available")  # type: ignore[untyped-decorator]
    def test_compose_config_renders(self, tmp_path: Path) -> None:
        out = tmp_path / "test.env"
        result = _run("--defaults", "--output", str(out))
        assert result.returncode == 0
        compose = subprocess.run(
            ["docker", "compose", "--env-file", str(out), "config"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert compose.returncode == 0, compose.stderr

    @pytest.mark.skipif(shutil.which("docker") is None, reason="docker not available")  # type: ignore[untyped-decorator]
    def test_airgap_compose_config_renders(self, tmp_path: Path) -> None:
        out = tmp_path / "test.airgap.env"
        result = _run("--defaults", "--airgap", "--output", str(out))
        assert result.returncode == 0
        compose = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                str(out),
                "-f",
                "docker-compose.airgap.yml",
                "config",
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert compose.returncode == 0, compose.stderr

    def test_file_permissions(self, tmp_path: Path) -> None:
        out = tmp_path / "test.env"
        result = _run("--defaults", "--output", str(out))
        assert result.returncode == 0
        stat = os.stat(out)
        # Expect owner read/write only (0o600)
        assert oct(stat.st_mode)[-3:] == "600", f"unexpected permissions: {oct(stat.st_mode)}"

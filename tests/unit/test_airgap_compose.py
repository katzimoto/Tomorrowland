"""Structural guards for the unified Tomorrowland Compose configuration.

Tests cover docker-compose.yml (canonical source) and docker-compose.airgap.yml
(thin offline overlay) to ensure both connected and air-gapped deployments are
correctly wired. The airgap wrapper uses both files together:
  docker compose -f docker-compose.yml -f docker-compose.airgap.yml ...
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
AIRGAP_OVERLAY = REPO_ROOT / "docker-compose.airgap.yml"


def _top_level_block(path: Path, name: str) -> list[str]:
    """Return the lines under a top-level ``name:`` key (excluding the header)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    block: list[str] = []
    capturing = False
    for line in lines:
        if re.match(rf"^{re.escape(name)}:", line):
            capturing = True
            continue
        if capturing:
            if line and not line[0].isspace() and not line.lstrip().startswith("#"):
                break
            block.append(line)
    return block


def _service_block(path: Path, service: str) -> list[str]:
    """Return the lines of one service under the top-level ``services:`` key."""
    services = _top_level_block(path, "services")
    block: list[str] = []
    capturing = False
    for line in services:
        m = re.match(r"^  (\S+):\s*$", line)
        if m:
            capturing = m.group(1) == service
            continue
        if capturing:
            block.append(line)
    return block


# ---------------------------------------------------------------------------
# docker-compose.yml: Ollama profile gating
# ---------------------------------------------------------------------------

def test_ollama_llm_service_is_behind_local_llm_profile() -> None:
    block = _service_block(COMPOSE_FILE, "ollama-llm")
    assert block, "docker-compose.yml must define the ollama-llm service"
    assert any(re.match(r"^\s+profiles:\s*\[.*local-llm.*\]", line) for line in block), (
        "ollama-llm must be gated behind the 'local-llm' profile"
    )


def test_ollama_embed_service_is_behind_local_llm_profile() -> None:
    block = _service_block(COMPOSE_FILE, "ollama-embed")
    assert block, "docker-compose.yml must define the ollama-embed service"
    assert any(re.match(r"^\s+profiles:\s*\[.*local-llm.*\]", line) for line in block), (
        "ollama-embed must be gated behind the 'local-llm' profile"
    )


# ---------------------------------------------------------------------------
# docker-compose.yml: worker dependencies
# ---------------------------------------------------------------------------

def test_workers_do_not_depend_on_ollama() -> None:
    for worker in ("embed-worker", "intelligence-worker"):
        block = _service_block(COMPOSE_FILE, worker)
        assert block, f"{worker} service must exist in docker-compose.yml"
        assert not any(
            re.match(r"^\s+ollama(?:-llm|-embed)?:\s*$", line) for line in block
        ), f"{worker} must not have a depends_on entry for any ollama service"


# ---------------------------------------------------------------------------
# docker-compose.yml: env anchor exposes external LLM settings
# ---------------------------------------------------------------------------

def test_env_anchor_exposes_external_llm_settings() -> None:
    block = _top_level_block(COMPOSE_FILE, "x-app-environment")
    text = "\n".join(block)
    for key in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "EMBEDDING_URL"):
        assert re.search(rf"^\s+{key}:", text, re.MULTILINE), (
            f"x-app-environment must pass {key} through to the containers"
        )


# ---------------------------------------------------------------------------
# docker-compose.yml: image tags present for airgap pre-loading
# ---------------------------------------------------------------------------

def test_first_party_services_have_image_tags() -> None:
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    for var in (
        "TOMORROWLAND_BACKEND_IMAGE",
        "TOMORROWLAND_FRONTEND_IMAGE",
        "TOMORROWLAND_LIBRETRANSLATE_IMAGE",
        "TOMORROWLAND_OLLAMA_IMAGE",
        "TOMORROWLAND_OLLAMA_EMBED_IMAGE",
    ):
        assert f"${{{var}" in text, (
            f"docker-compose.yml must include an image: tag using ${{{var}}}"
        )


# ---------------------------------------------------------------------------
# docker-compose.yml: port binding uses BIND_HOST
# ---------------------------------------------------------------------------

def test_ports_use_bind_host_variable() -> None:
    text = COMPOSE_FILE.read_text(encoding="utf-8")
    hardcoded = [
        ln.strip()
        for ln in text.splitlines()
        if re.match(r'\s+-\s+"?0\.0\.0\.0:', ln) and "BIND_HOST" not in ln
    ]
    assert not hardcoded, (
        f"Port bindings must use ${{BIND_HOST}} instead of hardcoded 0.0.0.0: {hardcoded}"
    )


# ---------------------------------------------------------------------------
# docker-compose.airgap.yml: overlay constraints
# ---------------------------------------------------------------------------

def test_airgap_overlay_has_no_build_steps() -> None:
    text = AIRGAP_OVERLAY.read_text(encoding="utf-8")
    assert not re.search(r"^\s+build:", text, re.MULTILINE), (
        "docker-compose.airgap.yml overlay must not contain build: steps"
    )


def test_airgap_overlay_sets_pull_policy_never() -> None:
    text = AIRGAP_OVERLAY.read_text(encoding="utf-8")
    assert "pull_policy: never" in text, (
        "docker-compose.airgap.yml must set pull_policy: never to prevent registry pulls"
    )


def test_airgap_overlay_covers_all_core_services() -> None:
    """Every non-profiled service should have pull_policy: never in the overlay."""
    overlay_text = AIRGAP_OVERLAY.read_text(encoding="utf-8")
    for service in (
        "api", "frontend", "mcp-server", "postgres", "kafka", "meilisearch",
        "qdrant", "libretranslate", "rabbitmq", "redis",
        "parse-worker", "translate-worker", "embed-worker", "index-worker",
        "intelligence-worker", "alert-worker", "enrich-worker",
        "ollama-llm", "ollama-embed",
    ):
        assert service in overlay_text, (
            f"docker-compose.airgap.yml must include a pull_policy entry for {service}"
        )

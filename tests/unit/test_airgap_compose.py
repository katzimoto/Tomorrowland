"""Structural guards for the air-gapped Compose file.

These assert the wiring that makes a no-Ollama / external-LLM deployment work:
the bundled ``ollama`` service is opt-in (behind the ``local-llm`` profile) and
the pipeline workers no longer hard-depend on it, so the stack starts against an
external OpenAI-compatible endpoint with no local Ollama present.

Parsed without PyYAML (not a project dependency) using a small indent-aware
splitter, so the checks run in the plain test venv.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.airgap.yml"


def _top_level_block(name: str) -> list[str]:
    """Return the lines under a top-level ``name:`` key (excluding the header)."""
    lines = COMPOSE_FILE.read_text(encoding="utf-8").splitlines()
    block: list[str] = []
    capturing = False
    for line in lines:
        if re.match(rf"^{re.escape(name)}:", line):
            capturing = True
            continue
        if capturing:
            # A new unindented, non-comment line ends the block.
            if line and not line[0].isspace() and not line.lstrip().startswith("#"):
                break
            block.append(line)
    return block


def _service_block(service: str) -> list[str]:
    """Return the lines of one service under the top-level ``services:`` key."""
    services = _top_level_block("services")
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


def test_ollama_service_is_behind_local_llm_profile() -> None:
    block = _service_block("ollama")
    assert block, "air-gapped compose must still define the ollama service"
    assert any(
        re.match(r"^\s+profiles:\s*\[.*local-llm.*\]", line) for line in block
    ), "ollama must be gated behind the 'local-llm' profile"


def test_workers_do_not_depend_on_ollama() -> None:
    for worker in ("embed-worker", "intelligence-worker"):
        block = _service_block(worker)
        assert block, f"{worker} service must exist in the air-gapped compose"
        # A bare ``ollama:`` mapping key (a depends_on entry) — not a comment.
        assert not any(
            re.match(r"^\s+ollama:\s*$", line) for line in block
        ), f"{worker} must not depend_on ollama (must start without local Ollama)"


def test_env_anchor_exposes_external_llm_settings() -> None:
    block = _top_level_block("x-app-environment")
    text = "\n".join(block)
    for key in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "EMBEDDING_URL"):
        assert re.search(rf"^\s+{key}:", text, re.MULTILINE), (
            f"x-app-environment must pass {key} through to the containers"
        )

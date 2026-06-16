"""Regression guardrail: product code must resolve models through the canonical
``ModelRuntime`` boundary, not by constructing providers directly (#813 §9).

Direct use of ``OllamaClient(...)``, ``OpenAICompatibleLLMProvider(...)``, or
``build_llm_provider(...)`` is only allowed in the canonical factory/runtime/
adapter modules and in process bootstraps (the API app and the pipeline worker
entrypoints), which have no ``app.state`` to resolve through. Everything else —
routers, services, RAG, search — must call ``app.state.model_runtime`` /
``ModelRuntime``.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCAN_ROOT = _REPO_ROOT / "src" / "services"

_FORBIDDEN = (
    "OllamaClient(",
    "OpenAICompatibleLLMProvider(",
    "build_llm_provider(",
)

# Approved construction sites (paths relative to src/services).
_ALLOWLIST = frozenset(
    {
        "intelligence/factory.py",
        "intelligence/task_defaults.py",
        "intelligence/runtime.py",
        "intelligence/ollama_client.py",
        "intelligence/llm_provider.py",
        "api/main.py",
        # Pipeline worker entrypoints bootstrap their own provider (no app.state).
        # Migrating these to a worker-side ModelRuntime is a #813 follow-up.
        "pipeline/slow_worker.py",
        "pipeline/enrich_worker.py",
        "pipeline/intelligence_consumer.py",
    }
)


def test_no_direct_model_client_construction() -> None:
    offenders: list[str] = []
    for path in sorted(_SCAN_ROOT.rglob("*.py")):
        rel = path.relative_to(_SCAN_ROOT).as_posix()
        if rel in _ALLOWLIST:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            for pattern in _FORBIDDEN:
                if pattern in line:
                    offenders.append(f"{rel}:{lineno}: {stripped}")

    assert not offenders, (
        "Direct model-client construction found outside allowlisted runtime/factory "
        "modules. Resolve models via app.state.model_runtime instead.\n"
        "If this is a legitimate new bootstrap, add it to _ALLOWLIST with a reason.\n\n"
        + "\n".join(offenders)
    )

"""Regression tests for Docker build hygiene.

Covers two build-time bugs that the lightweight container CI did not catch:

1. ``.dockerignore`` patterns are anchored to the context root, so a bare
   ``node_modules`` line does NOT exclude ``frontend/node_modules``. That shipped
   ~370 MB of node_modules into the build context (and into the image via
   ``COPY frontend/ ./``). Nested patterns need a ``**/`` prefix.

2. The preview-worker image inherits the backend ``ENTRYPOINT`` which drops
   privileges with ``gosu appuser``. If the Dockerfile leaves a non-root ``USER``
   as its final instruction, that gosu call fails with "operation not
   permitted" and the container crash-loops.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
PREVIEW_DOCKERFILE = REPO_ROOT / "docker" / "preview-worker.Dockerfile"


def _dockerignore_patterns() -> list[str]:
    lines = DOCKERIGNORE.read_text().splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]


def test_dockerignore_excludes_nested_dependency_dirs() -> None:
    """Heavy build artifacts must be ignored at any depth, not just the root.

    A bare ``node_modules`` only matches ``./node_modules``; ``frontend/
    node_modules`` requires ``**/node_modules``.
    """
    patterns = set(_dockerignore_patterns())
    required = {"**/node_modules", "**/dist", "**/build"}
    missing = required - patterns
    assert not missing, (
        f".dockerignore is missing nested-path patterns {sorted(missing)}; "
        "without the '**/' prefix, frontend/node_modules ships in the build "
        "context (~370 MB) and bloats the image."
    )


def test_preview_worker_does_not_end_as_non_root_user() -> None:
    """preview-worker inherits the gosu entrypoint; final USER must be root.

    If the Dockerfile ends on ``USER appuser`` the container starts non-root and
    the inherited ``gosu appuser`` drop fails with 'operation not permitted'.
    """
    user_directives = [
        line.split(maxsplit=1)[1].strip()
        for line in PREVIEW_DOCKERFILE.read_text().splitlines()
        if line.strip().upper().startswith("USER ")
    ]
    if user_directives:
        assert user_directives[-1] == "root", (
            "preview-worker.Dockerfile must not leave a non-root USER as its "
            f"final user (found {user_directives[-1]!r}); the inherited gosu "
            "entrypoint needs to start as root to drop to appuser."
        )

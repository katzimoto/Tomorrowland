"""Deployment consistency checks.

Catches category of errors where a Compose service references a console script
that is not registered in ``pyproject.toml``, or a Dockerfile that reuses the
backend entrypoint (which drops to ``appuser`` via ``gosu``) is forced to run
as a non-root user.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import yaml  # type: ignore[import-untyped]

REPO_ROOT = Path(__file__).resolve().parents[2]


def _dockerfile_final_user(dockerfile: Path) -> str | None:
    """Return the last USER directive value in a Dockerfile, if any."""
    final_user: str | None = None
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("USER "):
            final_user = stripped.split(None, 1)[1].strip()
    return final_user


def _dockerfile_uses_backend_entrypoint(dockerfile: Path) -> bool:
    """True if the Dockerfile's ENTRYPOINT is the backend privilege-drop script."""
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        stripped = line.strip().upper()
        if stripped.startswith("ENTRYPOINT") and "/ENTRYPOINT.SH" in stripped:
            return True
    return False


def test_compose_worker_commands_have_console_scripts() -> None:
    """Every ``tomorrowland-*`` command referenced in Compose is in pyproject.toml."""
    pyproject_path = REPO_ROOT / "pyproject.toml"
    compose_path = REPO_ROOT / "docker-compose.yml"

    with pyproject_path.open("rb") as f:
        pyproject = tomllib.load(f)

    scripts = set(pyproject.get("project", {}).get("scripts", {}))

    with compose_path.open(encoding="utf-8") as f:
        compose = yaml.safe_load(f)

    services = compose.get("services", {})
    referenced: set[str] = set()
    for service_config in services.values():
        command = service_config.get("command")
        if isinstance(command, list) and command and command[0].startswith("tomorrowland-"):
            referenced.add(command[0])

    missing = referenced - scripts
    assert not missing, (
        f"Compose references commands missing from [project.scripts]: {sorted(missing)}"
    )


def test_backend_entrypoint_images_run_as_root() -> None:
    """Images using the backend entrypoint must start as root so ``gosu`` works."""
    for dockerfile in (REPO_ROOT / "docker").glob("*.Dockerfile"):
        if not _dockerfile_uses_backend_entrypoint(dockerfile):
            continue
        final_user = _dockerfile_final_user(dockerfile)
        assert final_user in (None, "root"), (
            f"{dockerfile.name} uses /entrypoint.sh but final USER is {final_user!r}; "
            "gosu cannot drop privileges from a non-root user. Remove USER or keep it as root."
        )

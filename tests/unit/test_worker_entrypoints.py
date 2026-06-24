"""Regression tests for worker console-script entry points.

These guard against a class of bug where a Docker Compose service is launched
via a ``tomorrowland-*`` console script that was never registered in
``[project.scripts]`` (or points at a missing module/function). Such a service
builds fine but crash-loops at runtime with::

    error: exec: "tomorrowland-preview-worker": executable file not found in $PATH

which the lightweight container CI (compose ``config`` + image build only) does
not catch. Validating the wiring here keeps it in the fast unit job.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
PYPROJECT_FILE = REPO_ROOT / "pyproject.toml"
SRC_ROOT = REPO_ROOT / "src"

SCRIPT_PREFIX = "tomorrowland-"


def _compose_worker_commands() -> dict[str, str]:
    """Map service name -> console-script command for tomorrowland workers."""
    data = yaml.safe_load(COMPOSE_FILE.read_text())
    commands: dict[str, str] = {}
    for name, service in (data.get("services") or {}).items():
        command = service.get("command")
        if (
            isinstance(command, list)
            and command
            and isinstance(command[0], str)
            and command[0].startswith(SCRIPT_PREFIX)
        ):
            commands[name] = command[0]
    return commands


def _project_scripts() -> dict[str, str]:
    data = tomllib.loads(PYPROJECT_FILE.read_text())
    return dict(data.get("project", {}).get("scripts", {}))


def test_every_worker_command_has_a_registered_script() -> None:
    """Each tomorrowland-* compose command must exist in [project.scripts]."""
    scripts = _project_scripts()
    missing = {
        service: command
        for service, command in _compose_worker_commands().items()
        if command not in scripts
    }
    assert not missing, (
        "Docker Compose launches console scripts that are not registered in "
        f"pyproject [project.scripts]: {missing}. Add the entry point or the "
        "container will crash-loop at runtime."
    )


def test_registered_scripts_point_at_real_module_functions() -> None:
    """Every tomorrowland-* script target must resolve to a defined function.

    Uses AST parsing rather than importing, so the check stays fast and does
    not depend on the worker's runtime imports being installed.
    """
    failures: list[str] = []
    for name, target in _project_scripts().items():
        if not name.startswith(SCRIPT_PREFIX):
            continue
        module_path, _, func = target.partition(":")
        assert func, f"{name} -> {target!r} is missing a ':function' suffix"

        module_file = SRC_ROOT.joinpath(*module_path.split(".")).with_suffix(".py")
        if not module_file.exists():
            failures.append(f"{name}: module file {module_file} does not exist")
            continue

        tree = ast.parse(module_file.read_text())
        defined = {
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        if func not in defined:
            failures.append(f"{name}: {module_path} has no top-level def {func}()")

    assert not failures, "Broken console-script targets: " + "; ".join(failures)

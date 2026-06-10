"""Pytest plugin for offline retrieval and citation quality evaluation.

Usage:
    pytest tests/eval/ --eval                          # run all eval cases
    pytest tests/eval/ --eval --eval-config reranker   # compare a named config
    pytest tests/eval/ --eval --eval-output results.json

The --eval flag is required so that eval tests are skipped in the normal CI
suite (they require live Qdrant + Ollama services and take longer to run).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("eval", "offline evaluation harness")
    group.addoption(
        "--eval",
        action="store_true",
        default=False,
        help="Run offline retrieval/citation quality evaluations.",
    )
    group.addoption(
        "--eval-config",
        default="default",
        help="Named configuration to evaluate (e.g. 'reranker', 'no-reranker').",
    )
    group.addoption(
        "--eval-output",
        default=None,
        help="Path to write machine-readable JSON results.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "eval: mark test as an offline evaluation case (requires --eval to run)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    if config.getoption("--eval"):
        return
    skip_eval = pytest.mark.skip(reason="pass --eval to run offline evaluation tests")
    for item in items:
        if "eval" in item.keywords:
            item.add_marker(skip_eval)


@pytest.fixture(scope="session")
def eval_config(request: pytest.FixtureRequest) -> str:
    return str(request.config.getoption("--eval-config", default="default"))


@pytest.fixture(scope="session")
def eval_results_collector() -> list[dict]:
    return []


@pytest.fixture(scope="session", autouse=True)
def _write_eval_results(
    request: pytest.FixtureRequest,
    eval_results_collector: list[dict],
) -> None:
    yield
    output_path = request.config.getoption("--eval-output")
    if output_path and eval_results_collector:
        Path(output_path).write_text(json.dumps({"results": eval_results_collector}, indent=2))

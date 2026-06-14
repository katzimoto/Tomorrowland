"""Admin endpoints for Quality Lab — eval run management and trends (#714)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from services.api.main import current_user
from services.api.routers.admin.quality_lab_service import QualityLabService
from services.auth.models import TokenPayload
from services.permissions.enforcer import require_admin

router = APIRouter(tags=["admin"])


@router.post("/admin/quality-lab/runs")
def upload_quality_lab_run(
    payload: dict[str, Any],
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    """Upload eval results JSON from an offline/nightly eval run.

    Expected payload shape:
        {"eval_config": "default", "git_commit": "abc1234",
         "results": [{... per-case result dicts ...}]}

    The ``results`` field should be a list of per-case result dicts
    as emitted by ``tests/eval/test_retrieval.py``.
    """
    require_admin(user)

    results: list[dict[str, Any]] = payload.get("results", [])
    if not results or not isinstance(results, list):
        raise HTTPException(status_code=422, detail="results must be a non-empty list")

    eval_config = payload.get("eval_config", "default")
    if not isinstance(eval_config, str):
        raise HTTPException(status_code=422, detail="eval_config must be a string")

    git_commit = payload.get("git_commit")
    if git_commit is not None and not isinstance(git_commit, str):
        raise HTTPException(status_code=422, detail="git_commit must be a string or null")

    with request.app.state.engine.begin() as connection:
        service = QualityLabService(connection)
        result = service.upload_run(
            results=results,
            eval_config=eval_config,
            git_commit=git_commit,
            created_by=str(user.sub),
        )
        return result


@router.get("/admin/quality-lab/runs")
def list_quality_lab_runs(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List recent eval runs with summary metrics."""
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        service = QualityLabService(connection)
        return service.list_runs(limit=limit, offset=offset)


@router.get("/admin/quality-lab/runs/{run_id}")
def get_quality_lab_run(
    run_id: str,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    """Get a single eval run with all per-case results."""
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        service = QualityLabService(connection)
        run = service.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return run


@router.get("/admin/quality-lab/trends")
def get_quality_lab_trends(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    limit: int = 20,
    metric: str = "pass_rate",
) -> list[dict[str, Any]]:
    """Return trend data points for a metric across recent runs.

    Supported metrics: pass_rate, mrr, citation_accuracy,
    anchor_accuracy, expansion_coverage, no_answer_accuracy,
    unauthorized_leakage_count.
    """
    require_admin(user)
    allowed_metrics = {
        "pass_rate",
        "mrr",
        "citation_accuracy",
        "no_answer_accuracy",
        "anchor_accuracy",
        "expansion_coverage",
        "unauthorized_leakage_count",
    }
    if metric not in allowed_metrics:
        raise HTTPException(
            status_code=422,
            detail=f"metric must be one of: {', '.join(sorted(allowed_metrics))}",
        )

    with request.app.state.engine.begin() as connection:
        service = QualityLabService(connection)
        return service.get_trends(limit=limit, metric=metric)


@router.delete("/admin/quality-lab/runs/{run_id}")
def delete_quality_lab_run(
    run_id: str,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, str]:
    """Delete an eval run and all its per-case results."""
    require_admin(user)
    with request.app.state.engine.begin() as connection:
        service = QualityLabService(connection)
        found = service.delete_run(run_id)
        if not found:
            raise HTTPException(status_code=404, detail="Run not found")
        return {"status": "deleted"}

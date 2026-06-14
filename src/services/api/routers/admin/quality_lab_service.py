"""Quality Lab service \u2014 stores and queries historical eval runs for #714."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection

# ---- Inline aggregate metrics ----
# (moved from tests/eval/metrics.py to avoid src → tests dependency)
# ----


@dataclass
class _RetrievalMetrics:
    recall_at_k: dict[int, float] = field(default_factory=dict)
    mrr: float = 0.0
    citation_accuracy: float = 0.0
    no_answer_accuracy: float = 0.0
    unauthorized_leakage_count: int = 0
    latency_ms_by_stage: dict[str, list[float]] = field(default_factory=dict)
    total_cases: int = 0
    passed_cases: int = 0
    anchor_accuracy: float = 1.0
    anchor_cases_total: int = 0
    anchor_cases_passed: int = 0
    expansion_coverage: float = 0.0
    expansion_cases_total: int = 0
    expansion_cases_passed: int = 0

    @property
    def pass_rate(self) -> float:
        if self.total_cases == 0:
            return 0.0
        return self.passed_cases / self.total_cases


def _recall_at_k(retrieved_ids: list[str], gold_ids: set[str], k: int) -> float:
    if not gold_ids:
        return 1.0
    top_k = set(retrieved_ids[:k])
    return len(top_k & gold_ids) / len(gold_ids)


def _mean_reciprocal_rank(retrieved_ids: list[str], gold_ids: set[str]) -> float:
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in gold_ids:
            return 1.0 / rank
    return 0.0


def _citation_accuracy(
    cited_doc_ids: list[str],
    gold_ids: set[str],
    *,
    require_all: bool = False,
) -> float:
    if not gold_ids:
        return 1.0
    cited = set(cited_doc_ids)
    if require_all:
        return 1.0 if gold_ids <= cited else 0.0
    overlap = cited & gold_ids
    return len(overlap) / len(gold_ids)


def _aggregate_metrics(case_results: list[dict[str, object]]) -> _RetrievalMetrics:
    metrics = _RetrievalMetrics(total_cases=len(case_results))
    ks = [1, 3, 5, 10]
    recall_sums: dict[int, float] = dict.fromkeys(ks, 0.0)
    mrr_sum = 0.0
    citation_acc_sum = 0.0
    citation_cases = 0
    no_answer_correct = 0
    no_answer_cases = 0
    latency_accumulator: dict[str, list[float]] = {}
    anchor_total = 0
    anchor_passed = 0
    expansion_total = 0
    expansion_passed = 0

    for case in case_results:
        retrieved_raw = case.get("retrieved_ids", [])
        retrieved: list[str] = retrieved_raw  # type: ignore[assignment]
        gold_raw = case.get("gold_ids", [])
        gold: set[str] = set(gold_raw)  # type: ignore[call-overload]
        cited_raw = case.get("cited_ids", [])
        cited: list[str] = cited_raw  # type: ignore[assignment]

        if gold:
            for k in ks:
                recall_sums[k] += _recall_at_k(retrieved, gold, k)
            mrr_sum += _mean_reciprocal_rank(retrieved, gold)
            citation_acc_sum += _citation_accuracy(cited, gold)
            citation_cases += 1

        if case.get("expected_no_answer"):
            no_answer_cases += 1
            if not case.get("has_answer"):
                no_answer_correct += 1

        metrics.unauthorized_leakage_count += len(
            case.get("unauthorized_docs_cited", [])  # type: ignore[arg-type]
        )

        for stage, ms in case.get("latency_by_stage", {}).items():  # type: ignore[attr-defined]
            latency_accumulator.setdefault(stage, []).append(ms)

        if case.get("passed"):
            metrics.passed_cases += 1

        anchor_matched = case.get("anchor_matched")
        if anchor_matched is not None:
            anchor_total += 1
            if anchor_matched:
                anchor_passed += 1

        if case.get("expansion_eligible"):
            expansion_total += 1
            if case.get("expansion_applied"):
                expansion_passed += 1

    n = len(case_results) or 1
    c = citation_cases or 1
    na = no_answer_cases or 1

    metrics.recall_at_k = {k: recall_sums[k] / n for k in ks}
    metrics.mrr = mrr_sum / n
    metrics.citation_accuracy = citation_acc_sum / c
    metrics.no_answer_accuracy = no_answer_correct / na
    metrics.latency_ms_by_stage = latency_accumulator
    metrics.anchor_cases_total = anchor_total
    metrics.anchor_cases_passed = anchor_passed
    metrics.anchor_accuracy = anchor_passed / anchor_total if anchor_total else 1.0
    metrics.expansion_cases_total = expansion_total
    metrics.expansion_cases_passed = expansion_passed
    metrics.expansion_coverage = expansion_passed / expansion_total if expansion_total else 0.0

    return metrics


# ---- Service ----


class QualityLabService:
    """Stores eval run results and provides trend/run queries."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def upload_run(
        self,
        *,
        results: list[dict[str, Any]],
        eval_config: str,
        git_commit: str | None = None,
        created_by: str | None = None,
    ) -> dict[str, Any]:
        """Store an eval run and its per-case results."""
        metrics = _aggregate_metrics(results)

        run_id = uuid.uuid4()
        self._connection.execute(
            sa.text(
                """\
                INSERT INTO quality_lab_runs
                    (id, eval_config, git_commit, summary, case_count,
                     passed_count, pass_rate, created_by)
                VALUES
                    (:id, :eval_config, :git_commit, :summary, :case_count,
                     :passed_count, :pass_rate, :created_by)
                """
            ),
            {
                "id": run_id.hex,
                "eval_config": eval_config,
                "git_commit": git_commit,
                "summary": {
                    "total_cases": metrics.total_cases,
                    "passed_cases": metrics.passed_cases,
                    "pass_rate": metrics.pass_rate,
                    "recall_at_k": metrics.recall_at_k,
                    "mrr": metrics.mrr,
                    "citation_accuracy": metrics.citation_accuracy,
                    "no_answer_accuracy": metrics.no_answer_accuracy,
                    "unauthorized_leakage_count": metrics.unauthorized_leakage_count,
                    "anchor_accuracy": metrics.anchor_accuracy,
                    "anchor_cases_total": metrics.anchor_cases_total,
                    "anchor_cases_passed": metrics.anchor_cases_passed,
                    "expansion_coverage": metrics.expansion_coverage,
                    "expansion_cases_total": metrics.expansion_cases_total,
                    "expansion_cases_passed": metrics.expansion_cases_passed,
                },
                "case_count": metrics.total_cases,
                "passed_count": metrics.passed_cases,
                "pass_rate": metrics.pass_rate,
                "created_by": created_by,
            },
        )

        for case in results:
            self._connection.execute(
                sa.text(
                    """\
                    INSERT INTO quality_lab_results
                        (id, run_id, case_id, category, passed, result_json)
                    VALUES
                        (:id, :run_id, :case_id, :category, :passed, :result_json)
                    """
                ),
                {
                    "id": uuid.uuid4().hex,
                    "run_id": run_id.hex,
                    "case_id": case.get("id", ""),
                    "category": case.get("category", ""),
                    "passed": bool(case.get("passed", False)),
                    "result_json": case,
                },
            )

        return {"run_id": str(run_id), "case_count": metrics.total_cases}

    def list_runs(
        self,
        *,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List recent eval runs with summary metrics."""
        rows = self._connection.execute(
            sa.text(
                """\
                SELECT id, eval_config, git_commit, summary, case_count,
                       passed_count, pass_rate, created_by,
                       created_at
                FROM quality_lab_runs
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"limit": limit, "offset": offset},
        ).mappings()

        return [
            {
                "id": str(row["id"]),
                "eval_config": row["eval_config"],
                "git_commit": row["git_commit"],
                "summary": row["summary"],
                "case_count": row["case_count"],
                "passed_count": row["passed_count"],
                "pass_rate": row["pass_rate"],
                "created_by": row["created_by"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ]

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        """Get a single run with its per-case results."""
        run_row = (
            self._connection.execute(
                sa.text(
                    """\
                SELECT id, eval_config, git_commit, summary, case_count,
                       passed_count, pass_rate, created_by,
                       created_at
                FROM quality_lab_runs
                WHERE id = :run_id
                """
                ),
                {"run_id": run_id},
            )
            .mappings()
            .first()
        )

        if run_row is None:
            return None

        result_rows = self._connection.execute(
            sa.text(
                """\
                SELECT id, case_id, category, passed, result_json
                FROM quality_lab_results
                WHERE run_id = :run_id
                ORDER BY category, case_id
                """
            ),
            {"run_id": run_id},
        ).mappings()

        return {
            "id": str(run_row["id"]),
            "eval_config": run_row["eval_config"],
            "git_commit": run_row["git_commit"],
            "summary": run_row["summary"],
            "case_count": run_row["case_count"],
            "passed_count": run_row["passed_count"],
            "pass_rate": run_row["pass_rate"],
            "created_by": run_row["created_by"],
            "created_at": run_row["created_at"].isoformat() if run_row["created_at"] else None,
            "results": [
                {
                    "id": str(row["id"]),
                    "case_id": row["case_id"],
                    "category": row["category"],
                    "passed": row["passed"],
                    "result_json": row["result_json"],
                }
                for row in result_rows
            ],
        }

    def get_trends(
        self,
        *,
        limit: int = 20,
        metric: str = "pass_rate",
    ) -> list[dict[str, Any]]:
        """Return trend data points for plotting run metrics over time.

        Args:
            limit: Max number of recent runs to include.
            metric: Which summary metric to extract (pass_rate, mrr,
                    citation_accuracy, anchor_accuracy, expansion_coverage,
                    no_answer_accuracy).
        """
        rows = self._connection.execute(
            sa.text(
                """\
                SELECT id, eval_config, created_at, summary
                FROM quality_lab_runs
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings()

        points: list[dict[str, Any]] = []
        for row in rows:
            summary = row["summary"] or {}
            value = summary.get(metric, 0.0)
            points.append(
                {
                    "run_id": str(row["id"]),
                    "eval_config": row["eval_config"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "metric": metric,
                    "value": value,
                }
            )
        # Reverse so oldest comes first for charts
        points.reverse()
        return points

    def delete_run(self, run_id: str) -> bool:
        """Delete a run and its cascade-deleted results. Returns True if found."""
        result = self._connection.execute(
            sa.text("DELETE FROM quality_lab_runs WHERE id = :run_id"),
            {"run_id": run_id},
        )
        return result.rowcount > 0

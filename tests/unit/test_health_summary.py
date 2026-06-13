from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from services.intelligence.health_summary import compute_health_summary
from services.intelligence.source_qa_repository import SourceQACheck


def _check(*, failed_documents: int = 0, **overrides: int) -> SourceQACheck:
    return SourceQACheck(
        source_id=uuid4(),
        checked_at=datetime.now(UTC),
        total_documents=100,
        indexed_documents=90,
        pending_documents=5,
        failed_documents=failed_documents,
        **overrides,
    )


class TestComputeHealthSummaryNone:
    def test_none_check_returns_unknown(self) -> None:
        result = compute_health_summary(None)
        assert result["status"] == "unknown"
        assert result["severity"] is None
        assert result["issue_count"] == 0
        assert result["issues"] == []
        assert result["latest_check_at"] is None

    def test_none_check_admin_still_unknown(self) -> None:
        result = compute_health_summary(None, admin=True)
        assert result["status"] == "unknown"


class TestComputeHealthSummaryHealthy:
    def test_healthy_source(self) -> None:
        result = compute_health_summary(_check(failed_documents=0))
        assert result["status"] == "healthy"
        assert result["severity"] == "info"
        assert result["issue_count"] == 0
        assert result["issues"] == []

    def test_healthy_source_has_check_timestamp(self) -> None:
        check = _check(failed_documents=0)
        result = compute_health_summary(check)
        assert result["latest_check_at"] is not None


class TestComputeHealthSummaryDegraded:
    def test_degraded_from_issues(self) -> None:
        check = _check(failed_documents=0, empty_chunks=3, ocr_maybe_needed=5)
        result = compute_health_summary(check)
        assert result["status"] == "degraded"
        assert result["severity"] == "warning"
        assert result["issue_count"] == 2

    def test_degraded_issues_list_nonadmin_safe(self) -> None:
        check = _check(failed_documents=0, empty_chunks=3)
        result = compute_health_summary(check, admin=False)
        assert len(result["issues"]) == 1
        issue = result["issues"][0]
        assert issue["code"] == "empty_chunks"
        assert issue["severity"] == "warning"
        assert issue["safe_message"] is not None
        assert "3" not in issue["label"]  # non-admin — no exact counts
        assert issue["label"] == issue["safe_message"]

    def test_degraded_issues_list_admin_detailed(self) -> None:
        check = _check(failed_documents=0, missing_title=2)
        result = compute_health_summary(check, admin=True)
        issue = result["issues"][0]
        assert "2" in issue["label"]  # admin — includes counts
        assert issue["code"] == "missing_title"

    def test_degraded_empty_chunks(self) -> None:
        check = _check(failed_documents=0, empty_chunks=5)
        result = compute_health_summary(check)
        codes = {i["code"] for i in result["issues"]}
        assert "empty_chunks" in codes

    def test_degraded_missing_content(self) -> None:
        check = _check(failed_documents=0, missing_content=3)
        result = compute_health_summary(check)
        codes = {i["code"] for i in result["issues"]}
        assert "missing_content" in codes

    def test_degraded_missing_metadata(self) -> None:
        check = _check(failed_documents=0, missing_metadata=4)
        result = compute_health_summary(check)
        codes = {i["code"] for i in result["issues"]}
        assert "missing_metadata" in codes

    def test_degraded_missing_title(self) -> None:
        check = _check(failed_documents=0, missing_title=2)
        result = compute_health_summary(check)
        codes = {i["code"] for i in result["issues"]}
        assert "missing_title" in codes

    def test_degraded_ocr_maybe_needed(self) -> None:
        check = _check(failed_documents=0, ocr_maybe_needed=7)
        result = compute_health_summary(check)
        codes = {i["code"] for i in result["issues"]}
        assert "ocr_maybe_needed" in codes

    def test_degraded_index_lag(self) -> None:
        check = _check(failed_documents=0, index_lag_count=3)
        result = compute_health_summary(check)
        codes = {i["code"] for i in result["issues"]}
        assert "index_lag" in codes


class TestComputeHealthSummaryFailed:
    def test_failed_from_failed_documents(self) -> None:
        check = _check(failed_documents=5, empty_chunks=2)
        result = compute_health_summary(check)
        assert result["status"] == "failed"
        assert result["severity"] == "critical"

    def test_failed_also_includes_other_issues(self) -> None:
        check = _check(failed_documents=3, missing_content=1, ocr_maybe_needed=2)
        result = compute_health_summary(check)
        codes = {i["code"] for i in result["issues"]}
        assert "missing_content" in codes
        assert "ocr_maybe_needed" in codes

    def test_failed_has_issue_count(self) -> None:
        check = _check(failed_documents=1, empty_chunks=2, missing_title=1, index_lag_count=4)
        result = compute_health_summary(check)
        assert result["issue_count"] == 3

"""Map SourceQACheck to the EvidenceHealthSummary shape.

This produces a safe, user-facing health summary for display in
Evidence Inspector and retrieval diagnostics.  Missing health data
is returned as ``unknown``, never as ``healthy``.
"""

from __future__ import annotations

from typing import Any

from services.intelligence.source_qa_repository import SourceQACheck


def compute_health_summary(
    check: SourceQACheck | None,
    *,
    admin: bool = False,
) -> dict[str, Any]:
    """Map a *SourceQACheck* (or ``None``) to an EvidenceHealthSummary dict.

    When *check* is ``None`` the result status is ``"unknown"`` and the
    issues list is empty.  If *admin* is ``True`` issue records include
    a ``severity`` discriminator; non-admin callers only see safe labels.
    """
    if check is None:
        return {
            "status": "unknown",
            "severity": None,
            "issue_count": 0,
            "issues": [],
            "latest_check_at": None,
        }

    failed_docs = check.failed_documents
    issues = _build_issues(check, admin=admin)
    issue_count = len(issues)

    if failed_docs > 0:
        status = "failed"
        severity = "critical"
    elif issue_count > 0:
        status = "degraded"
        severity = "warning"
    else:
        status = "healthy"
        severity = "info"

    return {
        "status": status,
        "severity": severity,
        "issue_count": issue_count,
        "issues": issues,
        "latest_check_at": check.checked_at.isoformat() if check.checked_at else None,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SAFE_ISSUE_MAP: dict[str, str] = {
    "empty_chunks": "Some indexed documents have empty content text",
    "missing_content": "Some documents are missing content payloads",
    "missing_metadata": "Some documents have missing metadata",
    "missing_title": "Some documents have no title",
    "ocr_maybe_needed": "Some PDFs may need OCR processing",
    "index_lag": "Some documents are stuck pending (possible index lag)",
}


def _build_issues(check: SourceQACheck, *, admin: bool) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []

    def add(code: str, label: str, severity: str, safe_message: str) -> None:
        issues.append(
            {
                "code": code,
                "label": label if admin else safe_message,
                "severity": severity,
                "safe_message": safe_message,
            }
        )

    if check.empty_chunks > 0:
        add(
            "empty_chunks",
            f"{check.empty_chunks} indexed document(s) with empty content text",
            "warning",
            _SAFE_ISSUE_MAP["empty_chunks"],
        )
    if check.missing_content > 0:
        add(
            "missing_content",
            f"{check.missing_content} document(s) with no content payload",
            "warning",
            _SAFE_ISSUE_MAP["missing_content"],
        )
    if check.missing_metadata > 0:
        add(
            "missing_metadata",
            f"{check.missing_metadata} document(s) with missing/empty metadata",
            "warning",
            _SAFE_ISSUE_MAP["missing_metadata"],
        )
    if check.missing_title > 0:
        add(
            "missing_title",
            f"{check.missing_title} document(s) with no title",
            "warning",
            _SAFE_ISSUE_MAP["missing_title"],
        )
    if check.ocr_maybe_needed > 0:
        add(
            "ocr_maybe_needed",
            f"{check.ocr_maybe_needed} PDF(s) with empty text may need OCR",
            "warning",
            _SAFE_ISSUE_MAP["ocr_maybe_needed"],
        )
    if check.index_lag_count > 0:
        add(
            "index_lag",
            f"{check.index_lag_count} pending document(s) over threshold",
            "warning",
            _SAFE_ISSUE_MAP["index_lag"],
        )

    return issues

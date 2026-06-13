"""Unit tests for eval metrics — including v2 anchor accuracy (#754)."""

from __future__ import annotations

import pytest

from tests.eval.metrics import (
    RetrievalMetrics,
    aggregate_metrics,
    citation_accuracy,
    citation_anchor_success,
    mean_reciprocal_rank,
    recall_at_k,
)


# ── recall_at_k ─────────────────────────────────────────────────────


def test_recall_at_k_perfect():
    assert recall_at_k(["doc-1", "doc-2"], {"doc-1"}, k=1) == 1.0


def test_recall_at_k_miss():
    assert recall_at_k(["doc-2", "doc-3"], {"doc-1"}, k=5) == 0.0


def test_recall_at_k_empty_gold():
    assert recall_at_k(["doc-1"], set(), k=5) == 1.0


def test_recall_at_k_partial():
    result = recall_at_k(["doc-1", "doc-3"], {"doc-1", "doc-2"}, k=5)
    assert result == pytest.approx(0.5)


# ── mean_reciprocal_rank ─────────────────────────────────────────────


def test_mrr_first_result():
    assert mean_reciprocal_rank(["doc-1", "doc-2"], {"doc-1"}) == pytest.approx(1.0)


def test_mrr_second_result():
    assert mean_reciprocal_rank(["doc-2", "doc-1"], {"doc-1"}) == pytest.approx(0.5)


def test_mrr_no_match():
    assert mean_reciprocal_rank(["doc-2", "doc-3"], {"doc-1"}) == pytest.approx(0.0)


# ── citation_accuracy ────────────────────────────────────────────────


def test_citation_accuracy_full():
    assert citation_accuracy(["doc-1", "doc-2"], {"doc-1", "doc-2"}) == pytest.approx(1.0)


def test_citation_accuracy_partial():
    result = citation_accuracy(["doc-1"], {"doc-1", "doc-2"})
    assert result == pytest.approx(0.5)


def test_citation_accuracy_empty_gold():
    assert citation_accuracy(["doc-x"], set()) == pytest.approx(1.0)


def test_citation_accuracy_require_all_pass():
    assert citation_accuracy(["doc-1", "doc-2"], {"doc-1", "doc-2"}, require_all=True) == pytest.approx(1.0)


def test_citation_accuracy_require_all_fail():
    assert citation_accuracy(["doc-1"], {"doc-1", "doc-2"}, require_all=True) == pytest.approx(0.0)


# ── citation_anchor_success ──────────────────────────────────────────


def test_anchor_success_page_match():
    result = citation_anchor_success([3, 7], [], expected_page=3, expected_sheet_name=None)
    assert result is True


def test_anchor_success_page_miss():
    result = citation_anchor_success([5, 6], [], expected_page=3, expected_sheet_name=None)
    assert result is False


def test_anchor_success_sheet_match():
    result = citation_anchor_success([], ["Summary", "Details"], expected_page=None, expected_sheet_name="Summary")
    assert result is True


def test_anchor_success_sheet_miss():
    result = citation_anchor_success([], ["Details"], expected_page=None, expected_sheet_name="Summary")
    assert result is False


def test_anchor_success_no_expectation_returns_none():
    result = citation_anchor_success([1, 2], ["Sheet1"], expected_page=None, expected_sheet_name=None)
    assert result is None


def test_anchor_success_page_takes_precedence_over_sheet():
    # expected_page is checked first; expected_sheet_name is ignored when page set
    result = citation_anchor_success([5], ["Summary"], expected_page=5, expected_sheet_name="Missing")
    assert result is True


# ── aggregate_metrics ────────────────────────────────────────────────


def _make_case_result(**kwargs) -> dict:
    defaults: dict = {
        "retrieved_ids": [],
        "gold_ids": [],
        "cited_ids": [],
        "expected_no_answer": False,
        "has_answer": True,
        "unauthorized_docs_cited": [],
        "latency_by_stage": {},
        "passed": True,
        "anchor_matched": None,
    }
    defaults.update(kwargs)
    return defaults


def test_aggregate_zero_leakage():
    results = [_make_case_result(unauthorized_docs_cited=[])]
    m = aggregate_metrics(results)
    assert m.unauthorized_leakage_count == 0


def test_aggregate_leakage_counted():
    results = [_make_case_result(unauthorized_docs_cited=["secret-doc"])]
    m = aggregate_metrics(results)
    assert m.unauthorized_leakage_count == 1


def test_aggregate_pass_rate():
    results = [
        _make_case_result(passed=True),
        _make_case_result(passed=True),
        _make_case_result(passed=False),
    ]
    m = aggregate_metrics(results)
    assert m.pass_rate == pytest.approx(2 / 3)


def test_aggregate_no_answer_accuracy():
    results = [
        _make_case_result(expected_no_answer=True, has_answer=False),  # correct
        _make_case_result(expected_no_answer=True, has_answer=True),   # wrong
    ]
    m = aggregate_metrics(results)
    assert m.no_answer_accuracy == pytest.approx(0.5)


def test_aggregate_anchor_accuracy_all_pass():
    results = [
        _make_case_result(anchor_matched=True),
        _make_case_result(anchor_matched=True),
    ]
    m = aggregate_metrics(results)
    assert m.anchor_accuracy == pytest.approx(1.0)
    assert m.anchor_cases_total == 2
    assert m.anchor_cases_passed == 2


def test_aggregate_anchor_accuracy_partial():
    results = [
        _make_case_result(anchor_matched=True),
        _make_case_result(anchor_matched=False),
        _make_case_result(anchor_matched=None),  # not evaluated
    ]
    m = aggregate_metrics(results)
    assert m.anchor_cases_total == 2
    assert m.anchor_cases_passed == 1
    assert m.anchor_accuracy == pytest.approx(0.5)


def test_aggregate_anchor_accuracy_no_anchor_cases():
    results = [_make_case_result(anchor_matched=None)]
    m = aggregate_metrics(results)
    assert m.anchor_cases_total == 0
    assert m.anchor_accuracy == pytest.approx(1.0)


def test_aggregate_distinguishes_doc_recall_from_anchor():
    """Document-level recall can be 0 while anchor_accuracy is 1.0 (no expectations set)."""
    results = [
        _make_case_result(
            gold_ids=["doc-missing"],
            retrieved_ids=["doc-other"],
            cited_ids=["doc-other"],
            anchor_matched=None,
        )
    ]
    m = aggregate_metrics(results)
    assert m.recall_at_k[1] == pytest.approx(0.0)
    assert m.anchor_accuracy == pytest.approx(1.0)


# ── RetrievalMetrics properties ──────────────────────────────────────


def test_pass_rate_zero_cases():
    m = RetrievalMetrics()
    assert m.pass_rate == 0.0


def test_pass_rate_nonzero():
    m = RetrievalMetrics(total_cases=4, passed_cases=3)
    assert m.pass_rate == pytest.approx(0.75)

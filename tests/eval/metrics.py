"""Retrieval and citation quality metrics for offline evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetrievalMetrics:
    """Aggregate metrics for a batch of retrieval eval cases.

    ``recall_at_k``, ``mrr``, and ``citation_accuracy`` measure document-level
    retrieval quality.  ``anchor_accuracy`` measures citation-anchor quality
    separately — a citation can point to the right document but the wrong
    page/sheet, so the two metrics may diverge.
    """

    recall_at_k: dict[int, float] = field(default_factory=dict)
    mrr: float = 0.0
    citation_accuracy: float = 0.0
    no_answer_accuracy: float = 0.0
    unauthorized_leakage_count: int = 0
    latency_ms_by_stage: dict[str, list[float]] = field(default_factory=dict)
    total_cases: int = 0
    passed_cases: int = 0
    # Anchor metrics (v2, #754)
    anchor_accuracy: float = 1.0
    anchor_cases_total: int = 0
    anchor_cases_passed: int = 0

    @property
    def pass_rate(self) -> float:
        if self.total_cases == 0:
            return 0.0
        return self.passed_cases / self.total_cases


def recall_at_k(retrieved_ids: list[str], gold_ids: set[str], k: int) -> float:
    """Recall@k: fraction of gold documents found in the top-k results."""
    if not gold_ids:
        return 1.0
    top_k = set(retrieved_ids[:k])
    return len(top_k & gold_ids) / len(gold_ids)


def mean_reciprocal_rank(retrieved_ids: list[str], gold_ids: set[str]) -> float:
    """MRR: reciprocal rank of the first gold document in the results."""
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in gold_ids:
            return 1.0 / rank
    return 0.0


def citation_accuracy(
    cited_doc_ids: list[str],
    gold_ids: set[str],
    *,
    require_all: bool = False,
) -> float:
    """Fraction of citations pointing to gold documents.

    When *require_all* is True the score is 1.0 only if all gold documents
    are cited; otherwise any overlap counts.
    """
    if not gold_ids:
        return 1.0
    cited = set(cited_doc_ids)
    if require_all:
        return 1.0 if gold_ids <= cited else 0.0
    overlap = cited & gold_ids
    return len(overlap) / len(gold_ids)


def citation_anchor_success(
    cited_page_numbers: list[int],
    cited_section_headings: list[str],
    expected_page: int | None,
    expected_sheet_name: str | None,
) -> bool | None:
    """Check whether any citation anchor matches the expected target.

    Returns ``True`` or ``False`` when an expectation is set, or ``None``
    when neither ``expected_page`` nor ``expected_sheet_name`` is specified
    (no anchor assertion for this case).
    """
    if expected_page is not None:
        return expected_page in cited_page_numbers
    if expected_sheet_name is not None:
        return expected_sheet_name in cited_section_headings
    return None


def aggregate_metrics(case_results: list[dict]) -> RetrievalMetrics:
    """Compute aggregate metrics from a list of per-case result dicts.

    Each case dict should have:
        retrieved_ids: list[str]
        gold_ids: list[str]
        cited_ids: list[str]
        expected_no_answer: bool
        has_answer: bool
        unauthorized_docs_cited: list[str]
        latency_by_stage: dict[str, float]
        passed: bool
        anchor_matched: bool | None  (optional, v2)
    """
    metrics = RetrievalMetrics(total_cases=len(case_results))
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

    for case in case_results:
        retrieved = case.get("retrieved_ids", [])
        gold = set(case.get("gold_ids", []))
        cited = case.get("cited_ids", [])

        if gold:
            for k in ks:
                recall_sums[k] += recall_at_k(retrieved, gold, k)
            mrr_sum += mean_reciprocal_rank(retrieved, gold)
            citation_acc_sum += citation_accuracy(cited, gold)
            citation_cases += 1

        if case.get("expected_no_answer"):
            no_answer_cases += 1
            if not case.get("has_answer"):
                no_answer_correct += 1

        metrics.unauthorized_leakage_count += len(case.get("unauthorized_docs_cited", []))

        for stage, ms in case.get("latency_by_stage", {}).items():
            latency_accumulator.setdefault(stage, []).append(ms)

        if case.get("passed"):
            metrics.passed_cases += 1

        anchor_matched = case.get("anchor_matched")
        if anchor_matched is not None:
            anchor_total += 1
            if anchor_matched:
                anchor_passed += 1

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

    return metrics

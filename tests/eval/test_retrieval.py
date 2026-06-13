"""Offline retrieval and citation quality evaluation harness.

Run with:
    pytest tests/eval/ --eval
    pytest tests/eval/ --eval --eval-config reranker --eval-output results.json

Two configurations can be compared by running the suite twice with different
--eval-config values and diffing the JSON output files.

These tests require live Qdrant + Ollama services and are skipped in normal CI.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import pytest

from tests.eval.fixtures import EVAL_CASES
from tests.eval.metrics import aggregate_metrics


def _rag_service() -> Any:
    """Build a RagService for eval using env-configured settings."""
    from services.rag.reranker import CrossEncoderReranker, NoOpReranker
    from services.rag.service import RagService
    from services.search.factory import build_encoder
    from services.search.qdrant import QdrantSearchClient
    from shared.config import Settings

    settings = Settings()
    encoder = build_encoder(settings)
    qdrant = QdrantSearchClient(url=settings.qdrant_url, dimension=encoder.dimension)

    class _FakeLLM:
        model = "eval-stub"

        def generate(self, prompt: str, **_: Any) -> str:
            return "I don't have enough information to answer that question."

        def generate_stream(self, prompt: str, **_: Any):  # type: ignore[override]
            yield self.generate(prompt)

    llm = _FakeLLM()

    reranker_config = os.environ.get("EVAL_RERANKER", "noop")
    if reranker_config == "cross-encoder":
        reranker = CrossEncoderReranker(
            ollama_client=llm,
            min_score=3.0,
            top_n=8,
            model=settings.effective_reranker_model,
        )
    else:
        reranker = NoOpReranker()

    import sqlalchemy as sa

    engine = sa.create_engine(settings.postgres_url)
    connection = engine.connect()

    return RagService(
        qdrant_client=qdrant,
        encoder=encoder,
        ollama_client=llm,
        connection=connection,
        max_chunks=settings.rag_max_chunks,
        max_tokens_context=settings.rag_max_tokens_context,
        score_threshold=settings.rag_score_threshold,
        reranker=reranker,
    ), connection


@pytest.mark.eval
@pytest.mark.parametrize("case", EVAL_CASES, ids=[c["id"] for c in EVAL_CASES])
def test_retrieval_case(
    case: dict,
    eval_config: str,
    eval_results_collector: list[dict],
) -> None:
    """Run a single eval case and record the result."""
    rag, connection = _rag_service()
    start = time.perf_counter()

    try:
        result = rag.answer(
            question=case["question"],
            group_ids=[],
            allow_all=True,
        )
    finally:
        connection.close()

    elapsed_ms = (time.perf_counter() - start) * 1000

    retrieved_ids = [c.document_id for c in result.citations]
    cited_ids = retrieved_ids
    gold_ids = set(case.get("gold_ids", []))
    expected_no_answer = case.get("expected_no_answer", False)

    # Heuristic: "no answer" if the system answer contains typical hedging phrases
    _no_answer_phrases = [
        "don't have",
        "cannot find",
        "could not find",
        "no relevant",
        "not enough information",
        "i couldn't find",
        "unable to find",
    ]
    has_answer = not any(p in result.answer.lower() for p in _no_answer_phrases)

    trace = result.retrieval_trace
    latency_by_stage: dict[str, float] = {}
    if trace:
        for stage in trace.stages:
            latency_by_stage[stage.stage] = stage.timing_ms

    passed = True
    if expected_no_answer and has_answer:
        passed = False
    if gold_ids and not (gold_ids & set(retrieved_ids)):
        passed = False

    case_result = {
        "id": case["id"],
        "category": case["category"],
        "eval_config": eval_config,
        "question": case["question"],
        "language": case.get("language", "en"),
        "gold_ids": list(gold_ids),
        "retrieved_ids": retrieved_ids,
        "cited_ids": cited_ids,
        "expected_no_answer": expected_no_answer,
        "has_answer": has_answer,
        "unauthorized_docs_cited": [],
        "latency_total_ms": elapsed_ms,
        "latency_by_stage": latency_by_stage,
        "reranker_enabled": trace.reranker_enabled if trace else False,
        "passed": passed,
        "answer_excerpt": result.answer[:200],
    }

    eval_results_collector.append(case_result)

    if not passed:
        pytest.fail(
            f"Eval case {case['id']} failed: "
            f"expected_no_answer={expected_no_answer}, "
            f"has_answer={has_answer}, "
            f"gold_ids={gold_ids}, "
            f"retrieved={retrieved_ids[:5]}"
        )


@pytest.mark.eval
def test_aggregate_metrics(eval_results_collector: list[dict]) -> None:
    """Print aggregate metrics after all cases have run."""
    if not eval_results_collector:
        pytest.skip("No eval cases ran")

    metrics = aggregate_metrics(eval_results_collector)
    report = {
        "total_cases": metrics.total_cases,
        "passed_cases": metrics.passed_cases,
        "pass_rate": metrics.pass_rate,
        "recall_at_k": metrics.recall_at_k,
        "mrr": metrics.mrr,
        "citation_accuracy": metrics.citation_accuracy,
        "no_answer_accuracy": metrics.no_answer_accuracy,
        "unauthorized_leakage_count": metrics.unauthorized_leakage_count,
    }
    print("\n\n=== Eval Aggregate Metrics ===")
    print(json.dumps(report, indent=2))
    print("==============================\n")

    assert metrics.unauthorized_leakage_count == 0, (
        f"Permission boundary violated: {metrics.unauthorized_leakage_count} "
        "unauthorized documents cited"
    )

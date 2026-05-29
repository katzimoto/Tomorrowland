"""Unit tests for expertise() signal_details explanation fields (C2 #400)."""

from __future__ import annotations

from unittest.mock import MagicMock

from services.related.service import (
    SIGNAL_WEIGHTS,
    RelatedService,
    _expertise_response,
    _ExpertiseAggregate,
)


def _make_aggregate(
    *,
    view_count: int = 0,
    comment_count: int = 0,
    annotation_count: int = 0,
    subscription_count: int = 0,
    view_contribution: float = 0.0,
    comment_contribution: float = 0.0,
    annotation_contribution: float = 0.0,
    subscription_contribution: float = 0.0,
    docs: dict | None = None,
) -> _ExpertiseAggregate:
    score = (
        view_contribution
        + comment_contribution
        + annotation_contribution
        + subscription_contribution
    )
    return _ExpertiseAggregate(
        user_id="user-1",
        display_name="Alice",
        score=score,
        view_count=view_count,
        comment_count=comment_count,
        annotation_count=annotation_count,
        subscription_count=subscription_count,
        view_contribution=view_contribution,
        comment_contribution=comment_contribution,
        annotation_contribution=annotation_contribution,
        subscription_contribution=subscription_contribution,
        docs=docs or {},
    )


def test_signal_details_present_in_response() -> None:
    agg = _make_aggregate(view_count=2, view_contribution=6.0)
    result = _expertise_response(agg)
    assert "signal_details" in result


def test_signal_details_has_all_four_signals() -> None:
    agg = _make_aggregate()
    details = _expertise_response(agg)["signal_details"]
    assert set(details.keys()) == {"views", "comments", "annotations", "subscriptions"}


def test_signal_details_weight_matches_signal_weights_constant() -> None:
    agg = _make_aggregate()
    details = _expertise_response(agg)["signal_details"]
    assert details["views"]["weight"] == SIGNAL_WEIGHTS["view"]
    assert details["comments"]["weight"] == SIGNAL_WEIGHTS["comment"]
    assert details["annotations"]["weight"] == SIGNAL_WEIGHTS["annotation"]
    assert details["subscriptions"]["weight"] == SIGNAL_WEIGHTS["subscription"]


def test_signal_details_count_matches_signals_field() -> None:
    """signal_details[x]['count'] must equal the backward-compat signals[x] value."""
    agg = _make_aggregate(
        view_count=3,
        comment_count=1,
        annotation_count=2,
        subscription_count=1,
        view_contribution=9.0,
        comment_contribution=2.0,
        annotation_contribution=4.0,
        subscription_contribution=0.9,
    )
    result = _expertise_response(agg)
    for key, compat_key in [
        ("views", "views"),
        ("comments", "comments"),
        ("annotations", "annotations"),
        ("subscriptions", "subscriptions"),
    ]:
        assert result["signal_details"][key]["count"] == result["signals"][compat_key]


def test_signal_details_contribution_is_rounded() -> None:
    agg = _make_aggregate(view_count=1, view_contribution=3.123456789)
    details = _expertise_response(agg)["signal_details"]
    assert details["views"]["contribution"] == round(3.123456789, 4)


def test_existing_signals_field_unchanged() -> None:
    """Backward compat: signals.views is still an integer count."""
    agg = _make_aggregate(view_count=5, view_contribution=15.0)
    result = _expertise_response(agg)
    assert result["signals"]["views"] == 5
    assert isinstance(result["signals"]["views"], int)


def test_zero_signals_produce_zero_contributions() -> None:
    agg = _make_aggregate()
    details = _expertise_response(agg)["signal_details"]
    for signal in details.values():
        assert signal["count"] == 0
        assert signal["contribution"] == 0.0


def test_top_docs_only_includes_docs_from_aggregate() -> None:
    """top_docs comes from aggregate.docs which is group-filtered by expertise_signals()."""
    docs = {
        "doc-a": {"document_id": "doc-a", "title": "Alpha", "score": 0.9},
        "doc-b": {"document_id": "doc-b", "title": "Beta", "score": 0.7},
    }
    agg = _make_aggregate(view_count=1, view_contribution=2.7, docs=docs)
    result = _expertise_response(agg)
    returned_ids = {d["document_id"] for d in result["top_docs"]}
    assert returned_ids == {"doc-a", "doc-b"}


def test_top_docs_capped_at_five() -> None:
    docs = {
        f"doc-{i}": {"document_id": f"doc-{i}", "title": f"Doc {i}", "score": float(i) / 10}
        for i in range(8)
    }
    agg = _make_aggregate(docs=docs)
    result = _expertise_response(agg)
    assert len(result["top_docs"]) <= 5


def test_expertise_returns_signal_details_end_to_end() -> None:
    """Smoke-test that expertise() produces signal_details in the response dict."""
    mock_repo = MagicMock()
    mock_repo.expertise_signals.return_value = [
        {
            "user_id": "user-1",
            "display_name": "Alice",
            "document_id": "doc-1",
            "signal_type": "view",
            "doc_title": "Report",
        },
        {
            "user_id": "user-1",
            "display_name": "Alice",
            "document_id": "doc-1",
            "signal_type": "comment",
            "doc_title": "Report",
        },
    ]
    mock_repo.active_subscriptions.return_value = []

    mock_qdrant = MagicMock()
    mock_qdrant.search.return_value = [
        MagicMock(document_id="doc-1", score=0.95),
    ]

    mock_encoder = MagicMock()
    mock_encoder.encode.return_value = [0.1] * 384

    service = RelatedService(
        repository=mock_repo,
        qdrant_client=mock_qdrant,
        encoder=mock_encoder,
        job_repo=MagicMock(),
    )

    results = service.expertise(topic="budget", group_ids=["group-a"])

    assert len(results) == 1
    expert = results[0]
    assert "signal_details" in expert
    assert expert["signal_details"]["views"]["count"] == 1
    assert expert["signal_details"]["views"]["weight"] == SIGNAL_WEIGHTS["view"]
    assert expert["signal_details"]["views"]["contribution"] > 0
    assert expert["signal_details"]["comments"]["count"] == 1
    assert expert["signals"]["views"] == 1

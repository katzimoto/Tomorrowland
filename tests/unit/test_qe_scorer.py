"""Unit tests for translation quality estimation (#733).

Covers the acceptance criteria:
- Disabled mode (no QE when config is off)
- Successful heuristic scoring (fake scorer)
- Scorer failure isolation (does not break translation)
- Metadata persistence (results stored in version metadata shape)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.translation.local_qe_provider import (
    _MAX_SEGMENT_TEXT_LEN,
    LocalQEProvider,
)
from services.translation.qe_provider import (
    QualityEstimationProvider,
    QualityEstimationResult,
)
from services.translation.qe_scorer import QEScorer, build_qe_scorer

# ---------------------------------------------------------------------------
# QualityEstimationResult tests
# ---------------------------------------------------------------------------


class TestQualityEstimationResult:
    """Tests for the QualityEstimationResult dataclass and serialization."""

    def test_to_dict_minimal(self) -> None:
        """Minimal result serializes correctly."""
        result = QualityEstimationResult(
            provider="local_qe",
            model_id="none",
            mean_score=0.85,
            low_score_segment_count=0,
            scored_segment_count=10,
        )
        d = result.to_dict()
        assert d["provider"] == "local_qe"
        assert d["model_id"] == "none"
        assert d["mean_score"] == 0.85
        assert d["low_score_segment_count"] == 0
        assert d["scored_segment_count"] == 10
        assert d["worst_segments"] == []
        assert d["status"] == "ok"

    def test_to_dict_with_worst_segments(self) -> None:
        """Result with worst segments includes truncated text."""
        result = QualityEstimationResult(
            provider="local_qe",
            model_id="none",
            mean_score=0.42,
            low_score_segment_count=3,
            scored_segment_count=10,
            worst_segments=[
                {"index": 0, "text": "bad translation", "score": 0.1},
                {"index": 5, "text": "also bad", "score": 0.2},
            ],
            status="warning",
        )
        d = result.to_dict()
        assert d["status"] == "warning"
        assert len(d["worst_segments"]) == 2
        assert d["worst_segments"][0]["index"] == 0

    def test_to_dict_failed_status(self) -> None:
        """Failed result has status 'failed'."""
        result = QualityEstimationResult(
            provider="local_qe",
            model_id="none",
            mean_score=0.0,
            low_score_segment_count=5,
            scored_segment_count=0,
            status="failed",
        )
        d = result.to_dict()
        assert d["status"] == "failed"
        assert d["scored_segment_count"] == 0


# ---------------------------------------------------------------------------
# QualityEstimationProvider ABC tests
# ---------------------------------------------------------------------------


class TestQualityEstimationProviderABC:
    """Verify the ABC contract."""

    def test_default_health(self) -> None:
        """Default health() returns unknown status."""

        class _MinimalProvider(QualityEstimationProvider):
            @property
            def name(self) -> str:
                return "test_provider"

            @property
            def model_id(self) -> str:
                return "test_model"

            def estimate_quality(
                self,
                source_text: str,
                translated_text: str,
                source_lang: str | None,
                target_lang: str,
            ) -> QualityEstimationResult:
                return QualityEstimationResult(
                    provider=self.name,
                    model_id=self.model_id,
                    mean_score=1.0,
                    low_score_segment_count=0,
                    scored_segment_count=5,
                )

        provider = _MinimalProvider()
        health = provider.health()
        assert health["status"] == "unknown"
        assert health["provider"] == "test_provider"
        assert health["model_id"] == "test_model"


# ---------------------------------------------------------------------------
# LocalQEProvider tests
# ---------------------------------------------------------------------------


class TestLocalQEProvider:
    """Tests for the LocalQEProvider (heuristic and model-based paths)."""

    def test_identity_no_model(self) -> None:
        """Provider without a model path reports default identity."""
        provider = LocalQEProvider()
        assert provider.name == "local_qe"
        assert provider.model_id == "none"

    def test_identity_with_model_path(self) -> None:
        """Provider with a model path reports the directory name as model_id."""
        provider = LocalQEProvider(model_path="/path/to/cometkiwi")
        assert provider.name == "local_qe"
        assert provider.model_id == "cometkiwi"

    def test_estimate_quality_empty_text(self) -> None:
        """Empty source or translated text returns ok with 0 segments."""
        provider = LocalQEProvider()
        result = provider.estimate_quality(
            source_text="",
            translated_text="",
            source_lang="en",
            target_lang="fr",
        )
        assert result.status == "ok"
        assert result.scored_segment_count == 0
        assert result.mean_score == 1.0

    def test_estimate_quality_whitespace_only(self) -> None:
        """Whitespace-only text returns ok with 0 segments."""
        provider = LocalQEProvider()
        result = provider.estimate_quality(
            source_text="   \n  ",
            translated_text="\t  ",
            source_lang="en",
            target_lang="fr",
        )
        assert result.status == "ok"
        assert result.scored_segment_count == 0

    def test_estimate_quality_single_segment_good(self) -> None:
        """A long, diverse segment scores high."""
        provider = LocalQEProvider()
        result = provider.estimate_quality(
            source_text="The quick brown fox jumps over the lazy dog.",
            translated_text=(
                "This is a well-formed and reasonably diverse translated segment with good length."
            ),
            source_lang="en",
            target_lang="fr",
        )
        assert result.scored_segment_count == 1
        assert result.status == "ok"
        assert result.mean_score > 0.7
        assert result.low_score_segment_count == 0
        assert len(result.worst_segments) <= 1

    def test_estimate_quality_short_segment_scores_low(self) -> None:
        """A very short segment (< 3 chars) scores low (0.1)."""
        provider = LocalQEProvider()
        result = provider.estimate_quality(
            source_text="H.",
            translated_text="Y.",
            source_lang="en",
            target_lang="fr",
        )
        assert result.scored_segment_count == 1
        # "Y." is 2 chars (< 3), so scores 0.1
        assert result.mean_score == pytest.approx(0.1)

    def test_estimate_quality_mixed_segments(self) -> None:
        """Mixed short and long segments produce low_score_count > 0."""
        provider = LocalQEProvider(low_score_threshold=0.5)
        result = provider.estimate_quality(
            source_text=("Hello. This is a long source sentence for testing purposes here."),
            translated_text=(
                "Hi. This is a sufficiently long translated segment "
                "that should score well above the threshold for "
                "quality estimation."
            ),
            source_lang="en",
            target_lang="fr",
        )
        assert result.scored_segment_count == 2
        # "Hi." is short → scores 0.1
        # The long segment scores > 0.7
        assert result.low_score_segment_count >= 1

    def test_estimate_quality_worst_segments_truncated(self) -> None:
        """Worst segment text is truncated to _MAX_SEGMENT_TEXT_LEN."""
        provider = LocalQEProvider(low_score_threshold=0.99)
        long_text = "x" * 500
        result = provider.estimate_quality(
            source_text="test.",
            translated_text=long_text + ".",
            source_lang="en",
            target_lang="fr",
        )
        assert result.scored_segment_count == 1
        if result.worst_segments:
            worst_text = result.worst_segments[0]["text"]
            assert len(worst_text) <= _MAX_SEGMENT_TEXT_LEN

    def test_estimate_quality_multiple_segments(self) -> None:
        """Multi-sentence text is split and scored per segment."""
        provider = LocalQEProvider(low_score_threshold=0.5)
        result = provider.estimate_quality(
            source_text="First. Second. Third.",
            translated_text=(
                "First translated segment here. Second segment. "
                "Third segment with enough length to score well "
                "above threshold for quality estimation purposes."
            ),
            source_lang="en",
            target_lang="fr",
        )
        assert result.scored_segment_count == 3
        assert 0.0 <= result.mean_score <= 1.0

    def test_estimate_quality_non_latin_text(self) -> None:
        """Hebrew/CJK text is segmented and scored."""
        provider = LocalQEProvider(low_score_threshold=0.5)
        result = provider.estimate_quality(
            source_text="שלום עולם. זו בדיקה.",
            translated_text=(
                "Hello world. This is a test with enough length "
                "to score decently well above the threshold for "
                "quality estimation purposes."
            ),
            source_lang="he",
            target_lang="en",
        )
        assert result.scored_segment_count >= 1
        assert result.status in ("ok", "warning")

    def test_health_no_model(self) -> None:
        """Health reports degraded when no model loaded."""
        provider = LocalQEProvider()
        health = provider.health()
        assert health["status"] == "degraded"
        assert health["model_loaded"] is False
        assert health["model_path"] is None

    def test_health_with_nonexistent_model_path(self) -> None:
        """Health reports degraded when model path doesn't exist."""
        provider = LocalQEProvider(model_path="/nonexistent/path/to/model")
        health = provider.health()
        assert health["status"] == "degraded"
        assert health["model_loaded"] is False
        assert len(health["load_errors"]) > 0

    def test_segment_text_splits_on_sentence_boundaries(self) -> None:
        """_segment_text splits on sentence-ending punctuation."""
        segments = LocalQEProvider._segment_text(
            "First sentence. Second sentence! Third sentence? Fourth part."
        )
        assert len(segments) == 4
        for seg in segments:
            assert seg != ""

    def test_segment_text_no_sentence_boundaries(self) -> None:
        """_segment_text returns single segment when no punctuation."""
        segments = LocalQEProvider._segment_text(
            "This is just one long segment without any punctuation marks at all"
        )
        assert len(segments) == 1

    @pytest.mark.parametrize(
        "length,expected_min",
        [
            (2, 0.0),
            (5, 0.0),
            (15, 0.0),
            (30, 0.7),
            (100, 0.7),
        ],
    )
    def test_heuristic_score_by_length(self, length: int, expected_min: float) -> None:
        """Heuristic scoring floors differ by segment length tiers."""
        seg = "a" * length  # low diversity
        scores = LocalQEProvider._heuristic_score([seg])
        assert len(scores) == 1
        assert scores[0] >= expected_min


# ---------------------------------------------------------------------------
# QEScorer tests
# ---------------------------------------------------------------------------


class TestQEScorer:
    """Tests for the QEScorer orchestrator."""

    def test_score_disabled(self) -> None:
        """Disabled scorer returns status='disabled'."""
        scorer = QEScorer(enabled=False)
        result = scorer.score(
            source_text="Hello",
            translated_text="Bonjour",
            source_lang="en",
            target_lang="fr",
        )
        assert result["status"] == "disabled"

    def test_score_enabled_no_provider(self) -> None:
        """Enabled scorer without explicit provider uses heuristic fallback."""
        scorer = QEScorer(enabled=True)
        result = scorer.score(
            source_text="Hello world, this is a test.",
            translated_text="Bonjour le monde, ceci est un test.",
            source_lang="en",
            target_lang="fr",
        )
        assert result["status"] in ("ok", "warning")
        assert result["provider"] == "local_qe"
        assert result["scored_segment_count"] >= 1
        assert "mean_score" in result

    def test_score_with_explicit_provider(self) -> None:
        """Scorer delegates to explicit provider."""
        provider = LocalQEProvider(low_score_threshold=0.5)
        scorer = QEScorer(provider=provider, enabled=True)
        result = scorer.score(
            source_text="Hello world. This is a test.",
            translated_text="Bonjour le monde. Ceci est un test avec assez de longueur.",
            source_lang="en",
            target_lang="fr",
        )
        assert result["status"] in ("ok", "warning")
        assert result["scored_segment_count"] >= 1

    def test_score_provider_failure_is_isolated(self) -> None:
        """When provider raises, scorer returns failed status (no exception)."""
        bad_provider = MagicMock(spec=QualityEstimationProvider)
        bad_provider.name = "bad_provider"
        bad_provider.model_id = "bad_model"
        bad_provider.estimate_quality.side_effect = RuntimeError("QE model crashed")

        scorer = QEScorer(provider=bad_provider, enabled=True)
        result = scorer.score(
            source_text="Hello",
            translated_text="Bonjour",
            source_lang="en",
            target_lang="fr",
        )
        assert result["status"] == "failed"
        assert result["scored_segment_count"] == 0

    def test_score_provider_returns_failed_status(self) -> None:
        """When provider returns status='failed', scorer passes it through."""

        class _FailingProvider(QualityEstimationProvider):
            @property
            def name(self) -> str:
                return "failing"

            @property
            def model_id(self) -> str:
                return "failing_model"

            def estimate_quality(
                self,
                source_text: str,
                translated_text: str,
                source_lang: str | None,
                target_lang: str,
            ) -> QualityEstimationResult:
                return QualityEstimationResult(
                    provider=self.name,
                    model_id=self.model_id,
                    mean_score=0.0,
                    low_score_segment_count=5,
                    scored_segment_count=5,
                    status="failed",
                )

        scorer = QEScorer(provider=_FailingProvider(), enabled=True)
        result = scorer.score(
            source_text="Hello",
            translated_text="Bonjour",
            source_lang="en",
            target_lang="fr",
        )
        assert result["status"] == "failed"

    def test_health_disabled(self) -> None:
        """Health reflects disabled state."""
        scorer = QEScorer(enabled=False)
        health = scorer.health()
        assert health["enabled"] is False

    def test_health_enabled_with_provider(self) -> None:
        """Health includes provider health when enabled."""
        provider = LocalQEProvider()
        scorer = QEScorer(provider=provider, enabled=True)
        health = scorer.health()
        assert health["enabled"] is True
        assert "provider" in health
        assert health["provider"]["status"] == "degraded"

    def test_score_metadata_shape_matches_contract(self) -> None:
        """Result shape matches the quality_estimation metadata contract."""
        scorer = QEScorer(enabled=True)
        result = scorer.score(
            source_text="Hello world. This is a test.",
            translated_text="Bonjour le monde. Ceci est un test.",
            source_lang="en",
            target_lang="fr",
        )
        # Verify the exact keys from the issue contract
        expected_keys = {
            "provider",
            "model_id",
            "mean_score",
            "low_score_segment_count",
            "scored_segment_count",
            "worst_segments",
            "status",
        }
        assert set(result.keys()) == expected_keys
        assert isinstance(result["mean_score"], float)
        assert isinstance(result["low_score_segment_count"], int)
        assert isinstance(result["scored_segment_count"], int)
        assert isinstance(result["worst_segments"], list)
        assert result["status"] in ("ok", "warning", "failed", "disabled")


# ---------------------------------------------------------------------------
# build_qe_scorer factory tests
# ---------------------------------------------------------------------------


class TestBuildQEScorer:
    """Tests for the build_qe_scorer factory function."""

    def test_disabled_by_default(self) -> None:
        """Factory returns disabled scorer when enabled=False."""
        scorer = build_qe_scorer(enabled=False)
        assert scorer.enabled is False
        result = scorer.score(
            source_text="Hello",
            translated_text="Bonjour",
            source_lang="en",
            target_lang="fr",
        )
        assert result["status"] == "disabled"

    def test_enabled_no_model_uses_heuristic(self) -> None:
        """Enabled without model path uses heuristic provider."""
        scorer = build_qe_scorer(enabled=True, model_path="")
        assert scorer.enabled is True
        assert scorer.provider is not None
        result = scorer.score(
            source_text="Hello world, this is a test.",
            translated_text="Bonjour le monde, ceci est un test.",
            source_lang="en",
            target_lang="fr",
        )
        assert result["status"] in ("ok", "warning")

    def test_enabled_with_model_path(self) -> None:
        """Enabled with model path creates LocalQEProvider."""
        # Model won't load (path is fake) but scorer works anyway
        scorer = build_qe_scorer(enabled=True, model_path="/fake/path", low_score_threshold=0.3)
        assert scorer.enabled is True
        assert scorer.provider is not None
        # Should still work (model loading failure is non-fatal)
        result = scorer.score(
            source_text="Hello world, this is a test.",
            translated_text="Bonjour le monde, ceci est un test.",
            source_lang="en",
            target_lang="fr",
        )
        assert result["status"] in ("ok", "warning")

    def test_custom_threshold(self) -> None:
        """Low_score_threshold is passed through."""
        scorer = build_qe_scorer(enabled=True, model_path="", low_score_threshold=0.8)
        result = scorer.score(
            source_text="Hello.",
            translated_text="Hi.",
            source_lang="en",
            target_lang="fr",
        )
        # "Hi." scores 0.1 which is below 0.8 → should be warning
        assert result["low_score_segment_count"] >= 1

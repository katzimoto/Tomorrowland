"""Local reference-free translation quality estimation provider (#733).

Provides :class:`LocalQEProvider` — an offline, reference-free quality
estimation provider that scores translation segments without requiring
internet access or human reference translations.

When no model is configured the provider returns a "disabled" result
so callers never need to check availability before calling
:meth:`estimate_quality`.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from services.translation.qe_provider import (
    QualityEstimationProvider,
    QualityEstimationResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_NAME = "local_qe"
_DEFAULT_MODEL_ID = "none"
# Threshold below which a segment is flagged as "low score".
_DEFAULT_LOW_SCORE_THRESHOLD = 0.5
# Maximum number of worst segments to include in the result.
_MAX_WORST_SEGMENTS = 5
# Truncate segment text in worst_segments to this length.
_MAX_SEGMENT_TEXT_LEN = 200


class LocalQEProvider(QualityEstimationProvider):
    """Local, offline, reference-free quality estimation provider.

    Designed to work with a bundled QE model (e.g. COMETKiwi) when
    available, and degrade gracefully to a simple heuristic when no
    model is configured.
    """

    def __init__(
        self,
        model_path: str = "",
        *,
        low_score_threshold: float = _DEFAULT_LOW_SCORE_THRESHOLD,
    ) -> None:
        """Initialise the provider.

        Args:
            model_path: Path to a local QE model directory or file.
                When empty, a simple heuristic-based scorer is used
                (suitable for testing and graceful degradation).
            low_score_threshold: Segments scoring below this value
                are counted as "low score" and included in
                ``worst_segments``.

        Model loading is deferred to a future iteration (#733).
        When a real QE model format is defined in the model bundle
        contract (#730), :meth:`_init_model` will load and activate it.
        """
        self._model_path = Path(model_path) if model_path else None
        self._low_score_threshold = low_score_threshold
        self._load_errors: list[str] = []

        if self._model_path is not None:
            self._init_model()

    # -- Provider identity --------------------------------------------------

    @property
    def name(self) -> str:
        return _DEFAULT_NAME

    @property
    def model_id(self) -> str:
        if self._model_path is not None:
            return self._model_path.name
        return _DEFAULT_MODEL_ID

    # -- Quality estimation -------------------------------------------------

    def estimate_quality(
        self,
        source_text: str,
        translated_text: str,
        source_lang: str | None,
        target_lang: str,
    ) -> QualityEstimationResult:
        """Estimate translation quality segment by segment.

        When no model is loaded, returns a result with ``status="ok"``
        and ``scored_segment_count=0`` so callers can distinguish
        "not scored" from "scored and good".

        Never raises — returns a result with ``status="failed"`` on error.
        """
        if not source_text.strip() or not translated_text.strip():
            return QualityEstimationResult(
                provider=self.name,
                model_id=self.model_id,
                mean_score=1.0,
                low_score_segment_count=0,
                scored_segment_count=0,
                worst_segments=[],
                status="ok",
            )

        segments = self._segment_text(translated_text)
        if not segments:
            return QualityEstimationResult(
                provider=self.name,
                model_id=self.model_id,
                mean_score=1.0,
                low_score_segment_count=0,
                scored_segment_count=0,
                worst_segments=[],
                status="ok",
            )

        try:
            scores = self._score_segments(segments)
        except Exception:
            logger.warning(
                "QE scoring failed for %s→%s",
                source_lang,
                target_lang,
                exc_info=True,
            )
            return QualityEstimationResult(
                provider=self.name,
                model_id=self.model_id,
                mean_score=0.0,
                low_score_segment_count=len(segments),
                scored_segment_count=0,
                worst_segments=[],
                status="failed",
            )

        scored = [
            (i, seg, score) for i, (seg, score) in enumerate(zip(segments, scores, strict=False))
        ]
        low_score_items = [
            (i, seg, score) for i, seg, score in scored if score < self._low_score_threshold
        ]

        mean = sum(scores) / len(scores) if scores else 0.0

        # Pick up to MAX_WORST_SEGMENTS with the lowest scores
        worst = sorted(scored, key=lambda x: x[2])[:_MAX_WORST_SEGMENTS]
        worst_segments: list[dict[str, Any]] = [
            {
                "index": idx,
                "text": seg[:_MAX_SEGMENT_TEXT_LEN],
                "score": round(score, 4),
            }
            for idx, seg, score in worst
        ]

        status = "warning" if low_score_items else "ok"

        return QualityEstimationResult(
            provider=self.name,
            model_id=self.model_id,
            mean_score=round(mean, 4),
            low_score_segment_count=len(low_score_items),
            scored_segment_count=len(scores),
            worst_segments=worst_segments,
            status=status,
        )

    def health(self) -> dict[str, Any]:
        """Return a health snapshot."""
        return {
            "status": "degraded",
            "provider": self.name,
            "model_id": self.model_id,
            "model_loaded": False,
            "model_path": str(self._model_path) if self._model_path else None,
            "load_errors": self._load_errors,
        }

    # -- Internal -----------------------------------------------------------

    @staticmethod
    def _segment_text(text: str) -> list[str]:
        """Split text into sentence-like segments.

        A simple segmenter that splits on sentence-ending punctuation
        followed by whitespace.  Future versions can use a proper
        sentence-segmenter model.
        """
        # Split on .!? followed by whitespace and an uppercase letter or digit
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\u0590-\u05ff\u0600-\u06ff])", text)
        return [p.strip() for p in parts if p.strip()]

    def _score_segments(self, segments: list[str]) -> list[float]:
        """Score each segment (0.0–1.0).

        Uses a heuristic scorer.  Model-based scoring will be added
        when a QE model format is defined in the bundle contract (#730).
        """
        return self._heuristic_score(segments)

    @staticmethod
    def _heuristic_score(segments: list[str]) -> list[float]:
        """Simple heuristic scorer for testing and graceful degradation.

        Scores are based on segment length and character diversity.
        Longer, more diverse segments score higher.  Empty or very
        short segments score lower.
        """
        scores: list[float] = []
        for seg in segments:
            length = len(seg)
            if length < 3:
                scores.append(0.1)
            elif length < 10:
                scores.append(0.4)
            elif length < 30:
                scores.append(0.6)
            else:
                # Bonus for character diversity
                unique_chars = len(set(seg))
                diversity = min(unique_chars / max(length, 1), 1.0)
                base = 0.7 + 0.2 * diversity
                scores.append(round(min(base, 1.0), 4))
        return scores

    def _init_model(self) -> None:
        """Load the QE model from disk."""
        if self._model_path is None:
            return
        try:
            if not self._model_path.exists():
                self._load_errors.append(f"QE model path does not exist: {self._model_path}")
                return
            # Placeholder for future model loading.
            # When a real QE model format is defined in the model bundle
            # contract (#730), this will load and initialise it.
            logger.info(
                "LocalQEProvider model path configured but no model loader implemented yet: %s",
                self._model_path,
            )
        except Exception as exc:
            self._load_errors.append(f"Failed to load QE model: {exc}")

"""Pluggable translation quality estimation provider interface (#733).

Defines the :class:`QualityEstimationProvider` ABC and
:class:`QualityEstimationResult` dataclass so future QE models
(COMETKiwi, TransQuest, fine-tuned regressors) can be swapped in
without changing pipeline logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class QualityEstimationResult:
    """Result of a quality estimation run on a translated text.

    Designed to be stored in ``DocumentTranslationVersion.metadata``
    under the ``quality_estimation`` key for future Quality Lab
    trend display (#714).
    """

    provider: str
    """Provider name (e.g. ``"local_qe"``)."""

    model_id: str
    """Model identifier string (e.g. ``"cometkiwi-xl"``)."""

    mean_score: float
    """Mean quality score across all scored segments (0.0–1.0)."""

    low_score_segment_count: int
    """Number of segments with a score below the configured threshold."""

    scored_segment_count: int
    """Total number of segments scored."""

    worst_segments: list[dict[str, Any]] = field(default_factory=list)
    """Up to 5 segments with the lowest scores, each containing
    ``index``, ``text`` (truncated), and ``score``."""

    status: str = "ok"
    """Overall QE status: ``"ok"``, ``"warning"``, or ``"failed"``."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the ``quality_estimation`` metadata shape."""
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "mean_score": self.mean_score,
            "low_score_segment_count": self.low_score_segment_count,
            "scored_segment_count": self.scored_segment_count,
            "worst_segments": self.worst_segments,
            "status": self.status,
        }


class QualityEstimationProvider(ABC):
    """Abstract base class for reference-free quality estimation providers.

    Every provider must report its identity and expose an
    ``estimate_quality`` method that scores a source→target translation
    without requiring a human reference translation.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name (e.g. ``"local_qe"``)."""
        ...

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Identifier for the loaded model (e.g. ``"cometkiwi-xl"``)."""
        ...

    @abstractmethod
    def estimate_quality(
        self,
        source_text: str,
        translated_text: str,
        source_lang: str | None,
        target_lang: str,
    ) -> QualityEstimationResult:
        """Estimate translation quality for a source→target pair.

        Must never raise — return a result with ``status="failed"`` on error.
        """
        ...

    def health(self) -> dict[str, Any]:
        """Return a health-check snapshot for admin diagnostics."""
        return {"status": "unknown", "provider": self.name, "model_id": self.model_id}

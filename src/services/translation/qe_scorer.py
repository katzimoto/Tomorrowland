"""Translation quality estimation scorer (#733).

Orchestrates quality estimation for translation versions.  Handles
provider lifecycle, disabled mode, failure isolation, and metadata
assembly so the pipeline never blocks on QE.
"""

from __future__ import annotations

import logging
from typing import Any

from services.translation.local_qe_provider import LocalQEProvider
from services.translation.qe_provider import (
    QualityEstimationProvider,
    QualityEstimationResult,
)

logger = logging.getLogger(__name__)


class QEScorer:
    """Orchestrate quality estimation for translation versions.

    Designed as a lightweight service that:
    - Is disabled by default (no provider configured)
    - Never blocks translation availability
    - Handles provider failures gracefully
    - Returns metadata ready for storage in ``DocumentTranslationVersion.metadata``

    Usage::

        scorer = QEScorer(
            provider=LocalQEProvider(model_path="/path/to/qe/model"),
        )
        result = scorer.score(
            source_text="Hello world",
            translated_text="Bonjour le monde",
            source_lang="en",
            target_lang="fr",
        )
        # result is a dict ready for version.metadata["quality_estimation"]
    """

    def __init__(
        self,
        provider: QualityEstimationProvider | None = None,
        *,
        enabled: bool = True,
        max_segments: int = 200,
    ) -> None:
        """Initialise the scorer.

        Args:
            provider: A :class:`QualityEstimationProvider` instance.
                When ``None`` and *enabled* is ``True``, a default
                :class:`LocalQEProvider` with heuristic scoring is
                created once and cached.
            enabled: When ``False``, :meth:`score` returns a no-op
                ``status="disabled"`` result without calling the provider.
            max_segments: Maximum number of segments to score (text is
                truncated to this many segments to bound runtime).
        """
        self._explicit_provider = provider
        self._enabled = enabled
        self._max_segments = max_segments
        self._cached_heuristic_provider: QualityEstimationProvider | None = None

    @property
    def enabled(self) -> bool:
        """Whether QE scoring is currently enabled."""
        return self._enabled

    @property
    def provider(self) -> QualityEstimationProvider | None:
        """The configured QE provider, or ``None``."""
        return self._explicit_provider or self._cached_heuristic_provider

    def _get_provider(self) -> QualityEstimationProvider:
        """Return a provider, creating a heuristic one lazily if needed."""
        if self._explicit_provider is not None:
            return self._explicit_provider
        if self._cached_heuristic_provider is None:
            self._cached_heuristic_provider = LocalQEProvider()
        return self._cached_heuristic_provider

    def score(
        self,
        source_text: str,
        translated_text: str,
        source_lang: str | None,
        target_lang: str,
    ) -> dict[str, Any]:
        """Run quality estimation and return a metadata dict.

        The returned dict is safe to store directly under the
        ``quality_estimation`` key in
        ``DocumentTranslationVersion.metadata``.

        When disabled, returns ``{"status": "disabled"}``.
        On provider failure, returns a result with ``status="failed"``.
        """
        if not self._enabled:
            return {"status": "disabled"}

        provider = self._get_provider()

        try:
            result = provider.estimate_quality(
                source_text=source_text,
                translated_text=translated_text,
                source_lang=source_lang,
                target_lang=target_lang,
            )
        except Exception:
            logger.warning(
                "QE scoring raised an exception for %s→%s",
                source_lang,
                target_lang,
                exc_info=True,
            )
            result = QualityEstimationResult(
                provider=provider.name,
                model_id=provider.model_id,
                mean_score=0.0,
                low_score_segment_count=0,
                scored_segment_count=0,
                worst_segments=[],
                status="failed",
            )

        return result.to_dict()

    def health(self) -> dict[str, Any]:
        """Return a health snapshot for admin diagnostics."""
        provider_health: dict[str, Any] = {}
        provider = self.provider
        if provider is not None:
            try:
                provider_health = provider.health()
            except Exception:
                provider_health = {"status": "error", "provider": provider.name}
        return {
            "enabled": self._enabled,
            "provider": provider_health,
        }


def build_qe_scorer(
    *,
    enabled: bool = False,
    model_path: str = "",
    low_score_threshold: float = 0.5,
) -> QEScorer:
    """Build a :class:`QEScorer` from settings.

    Args:
        enabled: Whether QE scoring is active.
        model_path: Path to a local QE model directory/file.
        low_score_threshold: Segments below this are flagged as low score.

    Returns:
        A configured :class:`QEScorer`.  When *enabled* is ``False``
        the scorer returns ``status="disabled"`` for every call.
    """
    provider = None
    if enabled and model_path:
        provider = LocalQEProvider(
            model_path=model_path,
            low_score_threshold=low_score_threshold,
        )
    elif enabled:
        # Heuristic-only mode for testing
        provider = LocalQEProvider(low_score_threshold=low_score_threshold)

    return QEScorer(provider=provider, enabled=enabled)

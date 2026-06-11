"""Parser router — selects, runs, and records extractions with fallback chains.

See docs/design/parser-router.md §4 for the integration design.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from services.extraction.base import ExtractionResult
from services.extraction.policy import ParserPolicyResolver
from services.extraction.registry import ExtractorRegistry, caps_from_extractor


def _confidence(result: ExtractionResult, quality_tier: str) -> float | None:
    """V1 heuristic: ratio of printable to total chars.

    When the parser is ``high`` tier and returned text, scores at least 0.8.
    The column exists so #674 can chart it; the scoring can improve later
    without a schema change.
    """
    if not result.text:
        return None
    printable = sum(1 for c in result.text if c.isprintable() or c in "\n\r\t")
    total = len(result.text)
    if total == 0:
        return None
    base = printable / total
    if quality_tier == "high":
        return max(base, 0.8)
    return base


@dataclass
class RoutedExtraction:
    """Result of a router-mediated extraction."""

    result: ExtractionResult
    parser_name: str
    parser_version: str
    duration_ms: int
    confidence: float | None
    warnings: list[str] = field(default_factory=list)
    attempts: list[str] = field(default_factory=list)


class ParserRouter:
    """Select the best parser for a document, run with fallback, record attempts."""

    def __init__(
        self,
        registry: ExtractorRegistry,
        resolver: ParserPolicyResolver,
    ) -> None:
        self._registry = registry
        self._resolver = resolver

    def route(
        self,
        path: Path,
        mime_type: str,
        source_id: UUID,
    ) -> RoutedExtraction:
        """Run the parser chain for *source_id* + *mime_type* on *path*.

        Returns the first non-empty result from the chain.  Falls back to the
        existing ``registry.extract()`` (with sniff-and-retry) when every
        parser in the chain fails.
        """
        chain = self._resolver.resolve(source_id, mime_type)
        warnings: list[str] = []
        attempts: list[str] = []

        for parser_name in chain:
            extractor = self._registry.get_by_name(parser_name)
            if extractor is None:
                continue

            caps = caps_from_extractor(extractor)
            try:
                file_size = path.stat().st_size
            except OSError:
                file_size = 0
            if caps.max_file_size and file_size > caps.max_file_size:
                warnings.append(f"{parser_name}: file exceeds max_file_size; skipped")
                continue

            attempts.append(parser_name)
            start = time.monotonic()
            result = extractor.extract(path)  # type: ignore[attr-defined]
            duration_ms = int((time.monotonic() - start) * 1000)

            if result.text.strip():
                return RoutedExtraction(
                    result=result,
                    parser_name=parser_name,
                    parser_version=caps.parser_version,
                    duration_ms=duration_ms,
                    confidence=_confidence(result, caps.quality_tier.value),
                    warnings=warnings,
                    attempts=attempts,
                )
            warnings.append(f"{parser_name}: produced empty text")

        # Whole chain failed → generic fallback, mirroring today's behaviour.
        start = time.monotonic()
        fallback_result = self._registry.extract(path, mime_type)
        duration_ms = int((time.monotonic() - start) * 1000)
        return RoutedExtraction(
            result=fallback_result,
            parser_name="generic",
            parser_version="1.0",
            duration_ms=duration_ms,
            confidence=_confidence(fallback_result, "basic"),
            warnings=warnings,
            attempts=attempts,
        )

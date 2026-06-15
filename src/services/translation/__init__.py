"""Translation package."""

from services.translation.client import LibreTranslateClient, build_translation_metadata
from services.translation.libretranslate_provider import LibreTranslateArgosProvider
from services.translation.provider import TranslationProvider
from services.translation.segment_pipeline import (
    PlaceholderMap,
    Segment,
    ValidationResult,
    build_segments,
    protect_placeholders,
    reassemble,
    restore_placeholders,
    run_segment_pipeline,
    validate_segments,
)

__all__ = [
    "LibreTranslateArgosProvider",
    "LibreTranslateClient",
    "PlaceholderMap",
    "Segment",
    "TranslationProvider",
    "ValidationResult",
    "build_segments",
    "build_translation_metadata",
    "protect_placeholders",
    "reassemble",
    "restore_placeholders",
    "run_segment_pipeline",
    "validate_segments",
]

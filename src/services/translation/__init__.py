"""Translation package."""

from services.translation.client import LibreTranslateClient, build_translation_metadata
from services.translation.ctranslate2_provider import CTranslate2OpusProvider
from services.translation.libretranslate_provider import LibreTranslateArgosProvider
from services.translation.model_bundle import (
    BundleIntegrityReport,
    BundleValidator,
    TranslationModelManifest,
    load_manifest_from_path,
    parse_manifest,
)
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
    "BundleIntegrityReport",
    "BundleValidator",
    "CTranslate2OpusProvider",
    "LibreTranslateArgosProvider",
    "LibreTranslateClient",
    "PlaceholderMap",
    "Segment",
    "TranslationModelManifest",
    "TranslationProvider",
    "ValidationResult",
    "build_segments",
    "build_translation_metadata",
    "load_manifest_from_path",
    "parse_manifest",
    "protect_placeholders",
    "reassemble",
    "restore_placeholders",
    "run_segment_pipeline",
    "validate_segments",
]

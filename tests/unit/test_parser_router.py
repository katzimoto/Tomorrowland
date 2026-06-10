"""Unit tests for ParserRouter — selection, fallback, and audit."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

from services.extraction.base import (
    BaseExtractor,
    ExtractionResult,
    ParserCapabilities,
    QualityTier,
)
from services.extraction.policy import ParserPolicyResolver
from services.extraction.registry import ExtractorRegistry
from services.extraction.router import ParserRouter, RoutedExtraction, _confidence


class TestConfidence:
    def test_empty_text_returns_none(self) -> None:
        result = ExtractionResult(text="")
        assert _confidence(result, "standard") is None

    def test_printable_ratio(self) -> None:
        result = ExtractionResult(text="hello world")
        c = _confidence(result, "standard")
        assert c is not None
        assert 0.9 <= c <= 1.0  # all printable

    def test_high_tier_floor(self) -> None:
        result = ExtractionResult(text="h\x00i")
        c = _confidence(result, "high")
        assert c is not None
        assert c >= 0.8

    def test_binary_text_low_confidence(self) -> None:
        result = ExtractionResult(text="\x00\x01\x02hello\x03\x04")
        c = _confidence(result, "standard")
        assert c is not None
        assert c < 0.8


class TestParserRouter:
    def test_route_happy_path(self) -> None:
        """Router selects the first parser in the chain that returns text."""
        registry = ExtractorRegistry()

        class FakeRepo:
            def match(self, *, source_id, mime_type):
                return None  # fall through to implicit chain

        resolver = ParserPolicyResolver(FakeRepo(), registry)
        router = ParserRouter(registry, resolver)

        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write("hello from router test")
            path = Path(f.name)

        try:
            routed = router.route(path, "text/plain", uuid4())
            assert isinstance(routed, RoutedExtraction)
            assert "hello from router test" in routed.result.text
            assert len(routed.attempts) > 0
            assert routed.parser_name != "generic"  # should find PlainExtractor
        finally:
            path.unlink(missing_ok=True)

    def test_route_fallback_to_generic(self) -> None:
        """When all parsers in the chain return empty, fall back to generic."""
        registry = ExtractorRegistry()

        class FakeRepo:
            def match(self, *, source_id, mime_type):
                return None

        resolver = ParserPolicyResolver(FakeRepo(), registry)
        router = ParserRouter(registry, resolver)

        # A binary file that no parser can extract meaningful text from
        path = Path(tempfile.mktemp(suffix=".bin"))
        path.write_bytes(b"\x00\x01\x02\x03\x04")

        try:
            routed = router.route(path, "application/octet-stream", uuid4())
            assert isinstance(routed, RoutedExtraction)
            assert routed.parser_name == "generic"
            assert len(routed.warnings) >= 0
        finally:
            path.unlink(missing_ok=True)

    def test_route_records_attempts(self) -> None:
        """Verify attempts list includes tried parsers."""
        registry = ExtractorRegistry()

        class FakeRepo:
            def match(self, *, source_id, mime_type):
                return None

        resolver = ParserPolicyResolver(FakeRepo(), registry)
        router = ParserRouter(registry, resolver)

        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            f.write("test")
            path = Path(f.name)

        try:
            routed = router.route(path, "text/plain", uuid4())
            assert len(routed.attempts) >= 1
        finally:
            path.unlink(missing_ok=True)

    def test_route_with_custom_chain(self) -> None:
        """Router uses policy chain when available."""
        registry = ExtractorRegistry()

        # Register a custom extractor
        class TestExtractor(BaseExtractor):
            _CAPS = ParserCapabilities(
                parser_name="test-parser",
                parser_version="1.0",
                supported_mime_types=("test/type",),
                quality_tier=QualityTier.STANDARD,
            )

            def extract(self, path: Path) -> ExtractionResult:
                return ExtractionResult(text="custom-extracted")

        test_ext = TestExtractor()
        registry.register("test/type", test_ext)

        class FakeRepo:
            def match(self, *, source_id, mime_type):
                return {"parser_chain": ["test-parser"]}

        resolver = ParserPolicyResolver(FakeRepo(), registry)
        router = ParserRouter(registry, resolver)

        with tempfile.NamedTemporaryFile(suffix=".test", mode="w", delete=False) as f:
            f.write("anything")
            path = Path(f.name)

        try:
            routed = router.route(path, "test/type", uuid4())
            assert routed.result.text == "custom-extracted"
            assert routed.parser_name == "test-parser"
            assert routed.parser_version == "1.0"
            assert routed.attempts == ["test-parser"]
        finally:
            path.unlink(missing_ok=True)

    def test_route_skips_max_file_size(self) -> None:
        """Router skips a parser when file exceeds max_file_size."""
        registry = ExtractorRegistry()

        class SmallParser(BaseExtractor):
            _CAPS = ParserCapabilities(
                parser_name="small-parser",
                parser_version="1.0",
                supported_mime_types=("test/small",),
                quality_tier=QualityTier.STANDARD,
                max_file_size=10,  # max 10 bytes
            )

            def extract(self, path: Path) -> ExtractionResult:
                return ExtractionResult(text="should-not-be-called")

        registry.register("test/small", SmallParser())

        class FakeRepo:
            def match(self, *, source_id, mime_type):
                return {"parser_chain": ["small-parser"]}

        resolver = ParserPolicyResolver(FakeRepo(), registry)
        router = ParserRouter(registry, resolver)

        # File is > 10 bytes
        path = Path(tempfile.mktemp(suffix=".small"))
        path.write_text("this file is way more than ten bytes long")

        try:
            routed = router.route(path, "test/small", uuid4())
            # Should fall back to generic since small-parser was skipped
            assert "small-parser: file exceeds max_file_size; skipped" in routed.warnings
            assert "small-parser" not in routed.attempts
        finally:
            path.unlink(missing_ok=True)

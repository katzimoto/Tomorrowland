"""Extractor registry mapping MIME types to extractors."""

from __future__ import annotations

import logging
from pathlib import Path

from services.extraction.base import (
    ExtractionResult,
    ParserCapabilities,
    QualityTier,
)
from services.extraction.docx import DocxExtractor
from services.extraction.eml import EmlExtractor
from services.extraction.epub import EpubExtractor
from services.extraction.generic import GenericExtractor
from services.extraction.html import HtmlExtractor
from services.extraction.json_extractor import JsonExtractor
from services.extraction.mime_detector import sniff_office_mime
from services.extraction.msg_extractor import MsgExtractor
from services.extraction.odt import OdtExtractor
from services.extraction.opendocument import OdpExtractor, OdsExtractor
from services.extraction.pdf import PdfExtractor
from services.extraction.plain import PlainExtractor
from services.extraction.pptx_extractor import PptxExtractor
from services.extraction.rtf import RtfExtractor
from services.extraction.tar_extractor import TarExtractor
from services.extraction.xls import XlsExtractor
from services.extraction.xlsx import XlsxExtractor
from services.extraction.xml_extractor import XmlExtractor
from services.extraction.zip_extractor import ZipExtractor

logger = logging.getLogger(__name__)

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_ODT_MIME = "application/vnd.oasis.opendocument.text"
_ODS_MIME = "application/vnd.oasis.opendocument.spreadsheet"
_ODP_MIME = "application/vnd.oasis.opendocument.presentation"

# Alias map: non-canonical MIME type → canonical registered type.
# Resolved in get() before the main extractor dict is consulted.
_ALIASES: dict[str, str] = {
    # ZIP variants
    "application/x-zip": "application/zip",
    "application/x-zip-compressed": "application/zip",
    # Gzip / tar
    "application/x-gzip": "application/gzip",
    # HTML
    "application/xhtml+xml": "text/html",
    # Images (common mis-spellings / vendor types)
    "image/jpg": "image/jpeg",
    "image/pjpeg": "image/jpeg",
    # Outlook MSG — libmagic returns compound-document types; mimetypes returns None for .msg
    "application/CDFV2": "application/vnd.ms-outlook",
    "application/x-ole-storage": "application/vnd.ms-outlook",
    # XLSX — libmagic may return the generic zip type for xlsx/xlsm files
    "application/vnd.ms-excel.sheet.macroEnabled.12": _XLSX_MIME,
    "application/vnd.ms-excel.sheet.binary.macroEnabled.12": _XLSX_MIME,
    # DOCX variants: macro-enabled (.docm) and template (.dotx / .dotm) share
    # the same ZIP+word/ structure and are handled by DocxExtractor.
    "application/vnd.ms-word.document.macroEnabled.12": _DOCX_MIME,
    "application/vnd.ms-word.template.macroEnabled.12": _DOCX_MIME,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.template": _DOCX_MIME,
    # Some APIs / connectors mislabel DOCX as the legacy binary Word type.
    "application/msword": _DOCX_MIME,
    # PPTX variants: macro-enabled (.pptm) and template (.potx / .potm)
    "application/vnd.ms-powerpoint.presentation.macroEnabled.12": _PPTX_MIME,
    "application/vnd.ms-powerpoint.template.macroEnabled.12": _PPTX_MIME,
    "application/vnd.openxmlformats-officedocument.presentationml.template": _PPTX_MIME,
    # XLSX template (.xltx / .xltm)
    "application/vnd.openxmlformats-officedocument.spreadsheetml.template": _XLSX_MIME,
    "application/vnd.ms-excel.template.macroEnabled.12": _XLSX_MIME,
    # Markdown / reStructuredText / log files → plain
    "text/x-markdown": "text/plain",
    # Python stdlib mimetypes maps .rst to text/prs.fallenstein.rst; libmagic uses text/x-rst
    "text/x-rst": "text/plain",
    "text/prs.fallenstein.rst": "text/plain",
    "text/x-log": "text/plain",
    # YAML — stdlib mimetypes returns application/yaml (RFC 9512);
    # older tools return x-yaml or text/yaml
    "application/yaml": "text/plain",
    "application/x-yaml": "text/plain",
    "text/yaml": "text/plain",
    # TOML / config → plain
    "application/toml": "text/plain",
    "text/x-toml": "text/plain",
    # Source code → plain (text-readable; enables extraction from code repositories)
    "text/x-python": "text/plain",
    "text/javascript": "text/plain",
    # mimetypes incorrectly maps .ts to Trolltech Linguist; treat as plain text
    "text/vnd.trolltech.linguist": "text/plain",
    "text/x-typescript": "text/plain",
}

_QUALITY_ORDER = {
    QualityTier.HIGH: 0,
    QualityTier.STANDARD: 1,
    QualityTier.BASIC: 2,
}


def caps_from_extractor(extractor: object) -> ParserCapabilities:
    """Return extractor.capabilities() if available, else a synthetic fallback."""
    try:
        return extractor.capabilities()  # type: ignore[attr-defined,no-any-return]
    except Exception:
        return ParserCapabilities(
            parser_name=type(extractor).__name__,
            parser_version="0",
            supported_mime_types=(),
            quality_tier=QualityTier.STANDARD,
        )


class ExtractorRegistry:
    """Map MIME types to concrete extractors.

    Each MIME type maps to an **ordered list** of extractors (the fallback
    chain candidates).  ``get()`` returns the first extractor for backward
    compatibility; ``candidates()`` returns the full chain ordered by quality
    tier.
    """

    def __init__(
        self,
        *,
        enable_ocr: bool = False,
        enable_legacy_office: bool = False,
        enable_markitdown: bool = False,
    ) -> None:
        pdf_extractor = PdfExtractor(ocr_fallback=enable_ocr)

        self._by_mime: dict[str, list[object]] = {}
        self._by_name: dict[str, object] = {}

        self._register("text/plain", PlainExtractor())
        self._register("text/markdown", PlainExtractor())
        self._register("text/csv", PlainExtractor())
        self._register("text/html", HtmlExtractor())
        self._register("text/xml", XmlExtractor())
        self._register("application/xml", XmlExtractor())
        self._register("application/xhtml+xml", HtmlExtractor())
        self._register("text/rtf", RtfExtractor())
        self._register("application/rtf", RtfExtractor())
        self._register("application/json", JsonExtractor())
        self._register("application/pdf", pdf_extractor)
        self._register(_DOCX_MIME, DocxExtractor())
        self._register(_PPTX_MIME, PptxExtractor())
        self._register(_XLSX_MIME, XlsxExtractor())
        self._register("application/vnd.ms-excel", XlsExtractor())
        self._register(_ODT_MIME, OdtExtractor())
        self._register(_ODS_MIME, OdsExtractor())
        self._register(_ODP_MIME, OdpExtractor())
        self._register("application/epub+zip", EpubExtractor())
        self._register("message/rfc822", EmlExtractor())
        self._register("application/vnd.ms-outlook", MsgExtractor())
        self._register("application/zip", ZipExtractor())
        self._register("application/x-tar", TarExtractor())
        self._register("application/gzip", TarExtractor())

        if enable_legacy_office:
            self._register_legacy_office()

        if enable_ocr:
            self._register_ocr()

        # MarkItDown registered last so it wraps the already-resolved extractors.
        if enable_markitdown:
            self._register_markitdown()

        # Fallback used when no specific extractor is registered.
        self._fallback = GenericExtractor()

    def _register_legacy_office(self) -> None:
        """Register legacy Office extractors (requires LibreOffice in PATH)."""
        from services.extraction.legacy_office import LegacyOfficeExtractor

        extractor = LegacyOfficeExtractor()
        self._register("application/msword", extractor)
        self._register("application/vnd.ms-excel", extractor)
        self._register("application/vnd.ms-powerpoint", extractor)

    def _register_ocr(self) -> None:
        """Register the OCR extractor for raster image MIME types."""
        from services.extraction.ocr import OcrExtractor

        extractor = OcrExtractor()
        for mime in ("image/png", "image/jpeg", "image/tiff", "image/bmp", "image/webp"):
            self._register(mime, extractor)

    def _register_markitdown(self) -> None:
        """Wrap OOXML extractors with Markdown converters for structured output."""
        from services.extraction.markitdown_extractor import (
            MarkItDownExtractor,
            _docx_to_markdown,
            _pptx_to_markdown,
            _xlsx_to_markdown,
        )

        for mime, convert_fn in [
            (_DOCX_MIME, _docx_to_markdown),
            (_PPTX_MIME, _pptx_to_markdown),
            (_XLSX_MIME, _xlsx_to_markdown),
        ]:
            existing = self._by_mime.get(mime, [])
            fallback = existing[0] if existing else None
            self._register(
                mime,
                MarkItDownExtractor(convert=convert_fn, fallback=fallback),  # type: ignore[arg-type]
            )

    def _register(self, mime_type: str, extractor: object) -> None:
        """Append extractor to the chain for mime_type and index by name."""
        self._by_mime.setdefault(mime_type, []).append(extractor)
        caps = caps_from_extractor(extractor)
        self._by_name[caps.parser_name] = extractor

    def register(self, mime_type: str, extractor: object) -> None:
        """Add or override an extractor for a MIME type."""
        self._register(mime_type, extractor)

    def get(self, mime_type: str) -> object | None:
        """Return the first extractor for *mime_type* when registered.

        Resolves MIME type aliases before looking up the extractor list.
        Returns the first extractor for backward compatibility.
        """
        canonical = _ALIASES.get(mime_type, mime_type)
        chain = self._by_mime.get(canonical)
        return chain[0] if chain else None

    def has_extractor(self, mime_type: str) -> bool:
        """Return True when *mime_type* has a specific extractor or a text alias.

        Unlike ``get()``, this returns True for any ``text/*`` MIME type even
        when not explicitly registered — the GenericExtractor fallback in
        ``extract()`` will handle it.  Use this to decide whether an attachment
        is worth processing rather than silently dropping it.
        """
        if self.get(mime_type) is not None:
            return True
        canonical = _ALIASES.get(mime_type, mime_type)
        return canonical.startswith("text/")

    def get_by_name(self, parser_name: str) -> object | None:
        """Return the extractor registered under *parser_name*, or None."""
        return self._by_name.get(parser_name)

    def candidates(self, mime_type: str) -> list[object]:
        """Return the full chain for a canonical MIME type, quality-tier-ordered.

        The list is sorted by quality tier (high → standard → basic) so the
        implicit default chain prefers higher-quality extractors.
        """
        canonical = _ALIASES.get(mime_type, mime_type)
        chain = list(self._by_mime.get(canonical, []))
        chain.sort(key=lambda e: _QUALITY_ORDER.get(caps_from_extractor(e).quality_tier, 99))
        return chain

    def list(self) -> list[ParserCapabilities]:
        """Return distinct capabilities of every registered parser."""
        seen: set[str] = set()
        result: list[ParserCapabilities] = []
        for chain in self._by_mime.values():
            for extractor in chain:
                caps = caps_from_extractor(extractor)
                if caps.parser_name not in seen:
                    seen.add(caps.parser_name)
                    result.append(caps)
        return result

    def capabilities(self, parser_name: str) -> ParserCapabilities | None:
        """Return capabilities for a named parser, or None."""
        ext = self._by_name.get(parser_name)
        return caps_from_extractor(ext) if ext is not None else None

    def canonical_mime(self, mime_type: str) -> str:
        """Return the canonical MIME type after alias resolution."""
        return _ALIASES.get(mime_type, mime_type)

    def extract(self, path: Path, mime_type: str) -> ExtractionResult:
        """Extract content from *path* using the extractor for *mime_type*.

        Returns an :class:`~services.extraction.base.ExtractionResult` whose
        ``text`` field contains the plain text and whose ``attachments`` list
        contains any child files (non-empty only for container formats such as
        email and archives).  All downstream pipeline stages receive this
        uniform envelope — they never need to know which extractor produced it.

        Falls back to :class:`~services.extraction.generic.GenericExtractor`
        when no specific extractor is registered, so unrecognised file types
        still produce a best-effort text result rather than silently returning
        an empty result.

        **Sniff-and-retry**: when the first extraction attempt returns an empty
        text (e.g. because the stored MIME type is ``application/zip`` or
        ``application/octet-stream`` for a file that is actually a DOCX/XLSX/
        PPTX), the file's raw content is inspected via
        :func:`~services.extraction.mime_detector.sniff_office_mime` and
        extraction is retried with the more specific type.  This transparently
        recovers documents that were ingested before MIME detection was improved.
        """
        extractor = self.get(mime_type)
        if extractor is None:
            logger.debug(
                "no specific extractor for mime_type=%s path=%s; using generic",
                mime_type,
                path,
            )
            extractor = self._fallback
        result = extractor.extract(path)  # type: ignore[attr-defined]

        # Sniff-and-retry strategy:
        # * For generic MIME types (application/zip, application/octet-stream) we
        #   ALWAYS try content sniffing — the stored type may be a mislabel, and
        #   ZipExtractor on a DOCX would return an XML-file listing, not doc text.
        # * For any other MIME type we only retry when extraction returned nothing.
        _always_sniff: frozenset[str] = frozenset({"application/zip", "application/octet-stream"})
        should_sniff = (mime_type in _always_sniff or not result.text) and path.exists()
        if should_sniff:
            sniffed = sniff_office_mime(path)
            if sniffed and sniffed != mime_type:
                # OLE compound document: application/x-ole-storage is aliased to
                # MsgExtractor in _ALIASES, so bypass get() and use XlsExtractor
                # directly (xlrd handles .xls OLE natively; fails fast on .doc/.ppt).
                if sniffed == "application/x-ole-storage":
                    retry_extractor: object | None = None
                    for ext in self._by_mime.get("application/vnd.ms-excel", []):
                        retry_extractor = ext
                        break
                else:
                    retry_extractor = self.get(sniffed)
                if retry_extractor is not None:
                    retry_result = retry_extractor.extract(path)  # type: ignore[attr-defined]
                    if retry_result.text:
                        logger.debug(
                            "extraction recovered via content sniffing "
                            "original_mime=%s sniffed=%s path=%s",
                            mime_type,
                            sniffed,
                            path,
                        )
                        result = retry_result

        if not result.text:
            logger.debug(
                "extraction returned empty mime_type=%s path=%s exists=%s",
                mime_type,
                path,
                path.exists(),
            )
        return result  # type: ignore[no-any-return]

"""Extractor registry mapping MIME types to extractors."""

from __future__ import annotations

import logging
from pathlib import Path

from services.extraction.base import Extractor
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


class ExtractorRegistry:
    """Map MIME types to concrete extractors."""

    def __init__(
        self,
        *,
        enable_ocr: bool = False,
        enable_legacy_office: bool = False,
    ) -> None:
        pdf_extractor = PdfExtractor(ocr_fallback=enable_ocr)

        self._extractors: dict[str, Extractor] = {
            # Plain text family
            "text/plain": PlainExtractor(),
            "text/markdown": PlainExtractor(),
            "text/csv": PlainExtractor(),
            # HTML / XML
            "text/html": HtmlExtractor(),
            "text/xml": XmlExtractor(),
            "application/xml": XmlExtractor(),
            "application/xhtml+xml": HtmlExtractor(),
            # RTF
            "text/rtf": RtfExtractor(),
            "application/rtf": RtfExtractor(),
            # JSON
            "application/json": JsonExtractor(),
            # PDF
            "application/pdf": pdf_extractor,
            # Microsoft Office (Open XML)
            _DOCX_MIME: DocxExtractor(),
            _PPTX_MIME: PptxExtractor(),
            _XLSX_MIME: XlsxExtractor(),
            # Microsoft Office legacy binary (xlrd — pure Python, no system deps)
            "application/vnd.ms-excel": XlsExtractor(),
            # OpenDocument
            _ODT_MIME: OdtExtractor(),
            _ODS_MIME: OdsExtractor(),
            _ODP_MIME: OdpExtractor(),
            # EPUB
            "application/epub+zip": EpubExtractor(),
            # Email
            "message/rfc822": EmlExtractor(),
            "application/vnd.ms-outlook": MsgExtractor(),
            # Archives
            "application/zip": ZipExtractor(),
            "application/x-tar": TarExtractor(),
            "application/gzip": TarExtractor(),
        }

        if enable_legacy_office:
            self._register_legacy_office()

        if enable_ocr:
            self._register_ocr()

        # Fallback used when no specific extractor is registered.
        # GenericExtractor tries UTF-8 then charset-normalizer but does NOT
        # fall back to latin-1, so true binary files still return "".
        self._fallback = GenericExtractor()

    def _register_legacy_office(self) -> None:
        """Register legacy Office extractors (requires LibreOffice in PATH)."""
        from services.extraction.legacy_office import LegacyOfficeExtractor

        extractor = LegacyOfficeExtractor()
        self._extractors["application/msword"] = extractor
        self._extractors["application/vnd.ms-excel"] = extractor
        self._extractors["application/vnd.ms-powerpoint"] = extractor

    def _register_ocr(self) -> None:
        """Register the OCR extractor for raster image MIME types."""
        from services.extraction.ocr import OcrExtractor

        extractor = OcrExtractor()
        for mime in ("image/png", "image/jpeg", "image/tiff", "image/bmp", "image/webp"):
            self._extractors[mime] = extractor

    def register(self, mime_type: str, extractor: Extractor) -> None:
        """Add or override an extractor for a MIME type."""
        self._extractors[mime_type] = extractor

    def get(self, mime_type: str) -> Extractor | None:
        """Return the extractor for *mime_type* when registered.

        Resolves MIME type aliases before looking up the extractor dict.
        """
        canonical = _ALIASES.get(mime_type, mime_type)
        return self._extractors.get(canonical)

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

    def extract(self, path: Path, mime_type: str) -> str:
        """Extract text from *path* using the extractor for *mime_type*.

        Falls back to :class:`~services.extraction.generic.GenericExtractor`
        when no specific extractor is registered, so unrecognised file types
        still produce a best-effort text result rather than silently returning
        an empty string.

        **Sniff-and-retry**: when the first extraction attempt returns an empty
        string (e.g. because the stored MIME type is ``application/zip`` or
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
        result = extractor.extract(path)

        # Sniff-and-retry strategy:
        # * For generic MIME types (application/zip, application/octet-stream) we
        #   ALWAYS try content sniffing — the stored type may be a mislabel, and
        #   ZipExtractor on a DOCX would return an XML-file listing, not doc text.
        # * For any other MIME type we only retry when extraction returned nothing.
        _always_sniff: frozenset[str] = frozenset(
            {"application/zip", "application/octet-stream"}
        )
        should_sniff = (mime_type in _always_sniff or not result) and path.exists()
        if should_sniff:
            sniffed = sniff_office_mime(path)
            if sniffed and sniffed != mime_type:
                # OLE compound document: application/x-ole-storage is aliased to
                # MsgExtractor in _ALIASES, so bypass get() and use XlsExtractor
                # directly (xlrd handles .xls OLE natively; fails fast on .doc/.ppt).
                if sniffed == "application/x-ole-storage":
                    retry_extractor: Extractor | None = self._extractors.get(
                        "application/vnd.ms-excel"
                    )
                else:
                    retry_extractor = self.get(sniffed)
                if retry_extractor is not None:
                    retry_result = retry_extractor.extract(path)
                    if retry_result:
                        logger.debug(
                            "extraction recovered via content sniffing "
                            "original_mime=%s sniffed=%s path=%s",
                            mime_type,
                            sniffed,
                            path,
                        )
                        result = retry_result

        if not result:
            logger.debug(
                "extraction returned empty mime_type=%s path=%s exists=%s",
                mime_type,
                path,
                path.exists(),
            )
        return result

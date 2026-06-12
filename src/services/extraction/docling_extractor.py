"""Docling-based PDF extractor for layout-aware document processing.

Requires ``docling`` to be installed (``pip install docling`` or via the
``[docling]`` optional extra).  When docling is absent the extractor returns
an empty result so the parser router can fall through to the next candidate
(e.g. pypdf).

Enabled for ``application/pdf`` when ``ENABLE_DOCLING=true`` is set.
"""

from __future__ import annotations

import logging
from pathlib import Path

from services.extraction.base import ExtractionResult, ParserCapabilities, QualityTier

logger = logging.getLogger(__name__)


class DoclingPdfExtractor:
    """Extract text and structure from PDF files using Docling.

    Produces Markdown output (headings, tables, lists) that is significantly
    richer than plain text for RAG chunking.  Imports ``docling`` lazily so
    the rest of the extraction pipeline works even when docling is not installed.
    """

    def capabilities(self) -> ParserCapabilities:
        try:
            import docling as _docling

            version = getattr(_docling, "__version__", "unknown")
        except ImportError:
            version = "not-installed"
        return ParserCapabilities(
            parser_name="docling_pdf",
            parser_version=version,
            supported_mime_types=("application/pdf",),
            quality_tier=QualityTier.HIGH,
        )

    def extract(self, path: Path) -> ExtractionResult:
        """Return Markdown-structured text extracted by Docling.

        Returns an empty ``ExtractionResult`` when:
        - the file does not exist,
        - ``docling`` is not installed, or
        - conversion fails for any reason.

        The parser router treats an empty result as a signal to try the next
        parser in the chain (typically the pypdf-based ``PdfExtractor``).
        """
        if not path.exists():
            return ExtractionResult(text="")
        try:
            from docling.document_converter import DocumentConverter
        except ImportError:
            logger.debug("docling not installed; skipping docling_pdf for path=%s", path)
            return ExtractionResult(text="")
        try:
            converter = DocumentConverter()
            conv_result = converter.convert(str(path))
            md = conv_result.document.export_to_markdown()
            if md and md.strip():
                return ExtractionResult(text=md.strip())
        except Exception:
            logger.debug("docling extraction failed for path=%s", path, exc_info=True)
        return ExtractionResult(text="")

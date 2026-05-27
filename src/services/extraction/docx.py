"""DOCX text extractor."""

from __future__ import annotations

import zipfile
from pathlib import Path

from docx import Document
from docx.opc.exceptions import PackageNotFoundError

from services.extraction.base import ExtractionResult


class DocxExtractor:
    """Extract text from Word .docx files using python-docx."""

    def extract(self, path: Path) -> ExtractionResult:
        """Return concatenated text from all paragraphs and tables.

        python-docx yields merged cells once per spanned column, so a cell
        that spans 3 columns appears 3 times in ``row.cells``.  We deduplicate
        by the underlying ``_tc`` XML element identity to produce each cell's
        text exactly once.
        """
        try:
            doc = Document(str(path))
            texts: list[str] = []
            for p in doc.paragraphs:
                if p.text:
                    texts.append(p.text)
            for table in doc.tables:
                for row in table.rows:
                    seen_tc: set[int] = set()
                    for cell in row.cells:
                        tc_id = id(cell._tc)  # noqa: SLF001
                        if tc_id in seen_tc:
                            continue
                        seen_tc.add(tc_id)
                        if cell.text:
                            texts.append(cell.text)
            return ExtractionResult(text="\n".join(texts))
        except (OSError, KeyError, ValueError, zipfile.BadZipFile, PackageNotFoundError):
            return ExtractionResult(text="")

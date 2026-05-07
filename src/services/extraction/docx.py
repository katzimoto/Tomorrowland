"""DOCX text extractor."""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.opc.exceptions import PackageNotFoundError


class DocxExtractor:
    """Extract text from Word .docx files using python-docx."""

    def extract(self, path: Path) -> str:
        """Return concatenated text from all paragraphs and tables."""
        try:
            doc = Document(str(path))
            texts: list[str] = []
            for p in doc.paragraphs:
                if p.text:
                    texts.append(p.text)
            for table in doc.tables:
                for row in table.rows:
                    for cell in row.cells:
                        if cell.text:
                            texts.append(cell.text)
            return "\n".join(texts)
        except (OSError, KeyError, PackageNotFoundError):
            return ""

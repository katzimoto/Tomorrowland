"""DOCX text extractor."""

from __future__ import annotations

from pathlib import Path

from docx import Document


class DocxExtractor:
    """Extract text from Word .docx files using python-docx."""

    def extract(self, path: Path) -> str:
        """Return concatenated text from all paragraphs."""
        try:
            doc = Document(str(path))
            paragraphs = [p.text for p in doc.paragraphs if p.text]
            return "\n".join(paragraphs)
        except Exception:
            return ""

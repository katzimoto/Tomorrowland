"""PPTX text extractor."""

from __future__ import annotations

import zipfile
from pathlib import Path

from pptx import Presentation
from pptx.exc import PackageNotFoundError


class PptxExtractor:
    """Extract text from PowerPoint .pptx files using python-pptx."""

    def extract(self, path: Path) -> str:
        """Return concatenated text from all slides and shapes."""
        try:
            prs = Presentation(str(path))
            texts: list[str] = []
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text:
                        texts.append(shape.text)
            return "\n".join(texts)
        except (OSError, KeyError, ValueError, zipfile.BadZipFile, PackageNotFoundError):
            return ""

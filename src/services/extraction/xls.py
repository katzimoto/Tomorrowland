"""XLS (Excel 97-2003 binary) text extractor via xlrd."""

from __future__ import annotations

from pathlib import Path

import xlrd

from services.extraction.base import ExtractionResult


class XlsExtractor:
    """Extract text from legacy Excel .xls files using xlrd.

    xlrd>=2.0 supports only the old BIFF (.xls) format — use
    :class:`~services.extraction.xlsx.XlsxExtractor` for modern .xlsx/.xlsm
    files.  No system libraries are required; xlrd is pure Python.
    """

    def extract(self, path: Path) -> ExtractionResult:
        """Return concatenated cell values from all sheets.

        Integer-valued floats (e.g. 42.0) are formatted without the
        trailing ``.0`` so that IDs and year numbers read naturally.
        """
        try:
            wb = xlrd.open_workbook(str(path))
            texts: list[str] = []
            for sheet in wb.sheets():
                for row_idx in range(sheet.nrows):
                    for col_idx in range(sheet.ncols):
                        cell = sheet.cell(row_idx, col_idx)
                        val = cell.value
                        if val is None or val == "":
                            continue
                        # Format floats that are whole numbers as ints (42.0 → "42")
                        if cell.ctype == xlrd.XL_CELL_NUMBER and isinstance(val, float):
                            texts.append(str(int(val)) if val == int(val) else str(val))
                        else:
                            texts.append(str(val))
            return ExtractionResult(text="\n".join(texts))
        except Exception:  # noqa: BLE001
            return ExtractionResult(text="")

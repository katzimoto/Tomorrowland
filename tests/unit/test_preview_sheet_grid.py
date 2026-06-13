from __future__ import annotations

import json
from pathlib import Path

from openpyxl import Workbook

from services.preview.sheet_grid import render_sheets


def _make_xlsx(path: Path, sheets: dict[str, list[list[object]]]) -> None:
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(row)
    wb.save(str(path))


def test_render_single_sheet_grid(tmp_path: Path) -> None:
    xlsx = tmp_path / "data.xlsx"
    _make_xlsx(xlsx, {"Budget": [["Item", "Cost"], ["Rent", 1000], ["Food", 200]]})

    rendered = render_sheets(xlsx, max_rows=100, max_cols=100)
    assert rendered.truncated is False
    assert [s["label"] for s in rendered.sheets] == ["Budget"]
    grid = json.loads(rendered.artifacts["sheet-0"][2])
    assert grid["name"] == "Budget"
    assert grid["rows"][0] == ["Item", "Cost"]
    assert grid["rows"][1] == ["Rent", "1000"]


def test_multiple_sheets_get_separate_artifacts(tmp_path: Path) -> None:
    xlsx = tmp_path / "multi.xlsx"
    _make_xlsx(xlsx, {"Q1": [["a"]], "Q2": [["b"]]})

    rendered = render_sheets(xlsx, max_rows=100, max_cols=100)
    assert [s["label"] for s in rendered.sheets] == ["Q1", "Q2"]
    assert set(rendered.artifacts) == {"sheet-0", "sheet-1"}
    assert json.loads(rendered.artifacts["sheet-1"][2])["rows"] == [["b"]]


def test_row_cap_truncates(tmp_path: Path) -> None:
    xlsx = tmp_path / "big.xlsx"
    _make_xlsx(xlsx, {"S": [[i] for i in range(10)]})

    rendered = render_sheets(xlsx, max_rows=3, max_cols=100)
    assert rendered.truncated is True
    grid = json.loads(rendered.artifacts["sheet-0"][2])
    assert len(grid["rows"]) == 3
    assert grid["truncated"]["rows"] is True


def test_col_cap_truncates(tmp_path: Path) -> None:
    xlsx = tmp_path / "wide.xlsx"
    _make_xlsx(xlsx, {"S": [list(range(10))]})

    rendered = render_sheets(xlsx, max_rows=100, max_cols=4)
    assert rendered.truncated is True
    grid = json.loads(rendered.artifacts["sheet-0"][2])
    assert len(grid["rows"][0]) == 4
    assert grid["truncated"]["cols"] is True


def test_empty_cells_render_as_empty_string(tmp_path: Path) -> None:
    xlsx = tmp_path / "gaps.xlsx"
    _make_xlsx(xlsx, {"S": [["a", None, "c"]]})

    rendered = render_sheets(xlsx, max_rows=100, max_cols=100)
    grid = json.loads(rendered.artifacts["sheet-0"][2])
    assert grid["rows"][0] == ["a", "", "c"]

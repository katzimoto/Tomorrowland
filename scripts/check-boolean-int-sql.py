"""Check for boolean columns compared to integer literals in raw SQL.

PostgreSQL rejects ``boolean = 0`` / ``boolean = 1``.  The integration
test suite uses SQLite (which silently coerces booleans to integers),
so these bugs only surface at runtime in production.

This script scans sa.text() blocks in src/ and tests/ for patterns
like ``is_latest = 1`` or ``is_private = 0``.

Usage:  python scripts/check-boolean-int-sql.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_BOOLEAN_COLUMNS = re.compile(
    r"\b(is_private|is_latest|is_admin|is_stale|enabled|is_active)\s*=\s*[01]\b",
)


def _extract_sql_strings(node: ast.AST, source: str) -> list[str]:
    """Walk *node* and return every string literal inside a sa.text() call."""
    strings: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, call: ast.Call) -> None:
            if (
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "text"
                and call.args
            ):
                first = call.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    strings.append(first.value)
            self.generic_visit(call)

    Visitor().visit(node)
    return strings


def _check_file(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return errors
    for sql in _extract_sql_strings(tree, ""):
        for m in _BOOLEAN_COLUMNS.finditer(sql):
            errors.append(
                f"{path}: boolean column compared to int literal: "
                f"`{m.group(0)}`  (use `true`/`false` or bound param)"
            )
    return errors


def main() -> int:
    errors: list[str] = []
    for path in sorted(ROOT.rglob("*.py")):
        parts = path.parts
        if ".venv" in parts:
            continue
        if "__pycache__" in parts:
            continue
        if "migrations" in parts:
            continue
        rel = path.relative_to(ROOT)
        if str(rel).startswith("graphify-out"):
            continue
        errors.extend(_check_file(path))

    if errors:
        print(f"{len(errors)} boolean-int SQL issue(s) found:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    print("OK — no boolean-integer SQL comparisons found.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

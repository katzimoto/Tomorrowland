"""Check for raw SQL queries with aggregate functions but no GROUP BY.

PostgreSQL 16+ requires that any non-aggregated column in a SELECT list
also appear in the GROUP BY clause.  The local test suite uses SQLite
(which silently accepts the omission), so these bugs only surface when
integration tests run against a real PG database or in production.

This script scans ``sa.text(...)`` blocks in ``src/`` and ``tests/`` for
queries that contain aggregate functions (COUNT, SUM, AVG, MIN, MAX)
alongside bare column references without a GROUP BY clause.

Usage:  python scripts/check-sql-group-by.py
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_AGGREGATE_RE = re.compile(
    r"\b(COUNT|SUM|AVG|MIN|MAX|ARRAY_AGG|STRING_AGG)\s*\(",
    re.IGNORECASE,
)
_GROUP_BY_RE = re.compile(r"\bGROUP\s+BY\b", re.IGNORECASE)

# Match an identifier (column reference) that is NOT an aggregate call.
# We look for identifiers at the "top-level" SELECT list — i.e. after
# SELECT and before the first top-level FROM.
_COLUMN_REF_RE = re.compile(
    r"""
    (?:^|,)\s*                    # start of select item or after comma
    (?!                           # not followed by:
        COUNT|SUM|AVG|MIN|MAX|ARRAY_AGG|STRING_AGG  # aggregate func
        \s*\(
        |\d+\s*$                  # numeric literal
        |'[^']*'\s*$              # string literal
        |\*                        # star
        |DISTINCT\s+
        |CASE\s+
    )
    ([a-zA-Z_][a-zA-Z0-9_.]*)     # the column reference itself
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _select_list_has_bare_column(sql: str) -> bool:
    """Return True when the top-level SELECT list contains a column
    reference that is not wrapped in an aggregate function."""
    # Find the SELECT ... FROM portion at the top level (not inside
    # parentheses, which indicate subqueries).
    depth = 0
    select_start = -1
    from_pos = -1
    for i, ch in enumerate(sql):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0:
            if select_start < 0:
                m = re.match(r"\bSELECT\b", sql[i:], re.IGNORECASE)
                if m:
                    select_start = i + m.end()
            if select_start >= 0 and from_pos < 0:
                m = re.match(r"\bFROM\b", sql[i:], re.IGNORECASE)
                if m:
                    from_pos = i
                    break

    if select_start < 0 or from_pos < 0:
        return False

    select_list = sql[select_start:from_pos].strip()
    # Split by top-level commas (not inside parens)
    items = _split_top_level(select_list)
    for item in items:
        stripped = item.strip()
        if not stripped:
            continue
        # If the item contains an aggregate at any nesting depth,
        # it's an aggregate expression, not a bare column.
        if _AGGREGATE_RE.search(stripped):
            continue
        # Skip if it's just a literal or star
        if re.match(r"^\d|^'|^\*", stripped):
            continue
        # Skip if it's a CASE expression
        if re.match(r"\bCASE\b", stripped, re.IGNORECASE):
            continue
        # Skip if it's a subquery (starts with SELECT)
        if re.match(r"\bSELECT\b", stripped, re.IGNORECASE):
            continue
        # Skip NULL, TRUE, FALSE, CURRENT_TIMESTAMP etc.
        if re.match(
            r"\b(NULL|TRUE|FALSE|CURRENT_TIMESTAMP|CURRENT_DATE|NOW)\b",
            stripped,
            re.IGNORECASE,
        ):
            continue
        # Remaining items are bare column references
        _id_match = re.search(r"[a-zA-Z_][a-zA-Z0-9_.]*", stripped)
        if _id_match:
            return True
    return False


def _split_top_level(text: str) -> list[str]:
    """Split *text* on commas that are not inside parentheses."""
    parts: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return parts


def _extract_sql_strings(node: ast.AST) -> list[str]:
    """Walk *node* and return every string literal inside a ``sa.text()`` call."""
    strings: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_Call(self, call: ast.Call) -> None:
            if isinstance(call.func, ast.Attribute) and call.func.attr == "text" and call.args:
                first = call.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    strings.append(first.value)
            self.generic_visit(call)

    Visitor().visit(node)
    return strings


def _has_aggregate_without_group_by(sql: str) -> bool:
    """Return True when *sql* uses an aggregate alongside bare columns
    without a GROUP BY clause."""
    if not _AGGREGATE_RE.search(sql):
        return False
    if _GROUP_BY_RE.search(sql):
        return False
    return _select_list_has_bare_column(sql)


def _check_file(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return errors
    for sql in _extract_sql_strings(tree):
        if _has_aggregate_without_group_by(sql):
            snippet = sql.strip()[:120].replace("\n", " ")
            errors.append(
                f"{path}: aggregate function without GROUP BY "
                f"(add GROUP BY or use SQLAlchemy Core expressions): "
                f"`{snippet}...`"
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
        print(f"{len(errors)} SQL GROUP BY issue(s) found:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    print("OK — no aggregate-without-GROUP-BY SQL found.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

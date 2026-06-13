"""Safe builders for Meilisearch filter expressions.

Every user-controlled value that lands inside a Meilisearch filter expression
must pass through :func:`escape_value` first. Without escaping, a value
containing a double quote, backslash, or control character can corrupt the
filter expression or — in the worst case — shift the predicate to a different
field. This module centralizes the escaping rules and exposes a small set of
predicate builders (``build_eq``, ``build_in``, ``build_gte``, ``build_lte``,
``quote``) so the rest of the codebase does not need to know the quoting
syntax.

Escape rules (applied in order):

1. Reject values containing a backtick — they have no valid escape inside a
   quoted filter value and indicate the value is being used in the wrong
   position (e.g. as a raw identifier).
2. Reject values with unbalanced parentheses.
3. Strip ASCII control characters except whitespace (``\\t``, ``\\n``,
   ``\\r``) — these would corrupt the filter expression.
4. Escape backslashes (``\\`` → ``\\\\``).
5. Escape double quotes (``"`` → ``\\"``).
"""

from __future__ import annotations

import re

# ASCII control characters except whitespace (0x09 tab, 0x0A LF, 0x0D CR).
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def escape_value(value: str) -> str:
    """Escape a string for safe inclusion inside a quoted Meilisearch value.

    Args:
        value: The raw string to escape.

    Returns:
        The escaped string, safe to wrap in double quotes.

    Raises:
        ValueError: If *value* contains a backtick or unbalanced parentheses,
            because these cannot be safely escaped inside a quoted value.
    """
    if "`" in value:
        raise ValueError("Meilisearch filter values must not contain backticks")
    if value.count("(") != value.count(")"):
        raise ValueError("Meilisearch filter values must have balanced parentheses")

    cleaned = _CONTROL_CHARS_RE.sub("", value)
    # Escape backslashes first so the backslashes we add for quotes are not
    # themselves re-escaped.
    cleaned = cleaned.replace("\\", "\\\\").replace('"', '\\"')
    return cleaned


def escape_list(values: list[str]) -> list[str]:
    """Apply :func:`escape_value` to every element of *values*.

    Returns a new list; does not mutate the input.
    """
    return [escape_value(v) for v in values]


def quote(value: str) -> str:
    """Escape *value* and wrap it in double quotes."""
    return f'"{escape_value(value)}"'


def build_eq(field: str, value: str) -> str:
    """Build a ``field = "value"`` predicate with proper escaping."""
    return f"{field} = {quote(value)}"


def build_in(field: str, values: list[str]) -> str:
    """Build a ``field IN ["a", "b"]`` predicate with proper escaping.

    Returns the empty string when *values* is empty. Callers MUST guard
    before ANDing: an empty IN [] is a Meilisearch syntax error. The
    :func:`compose_filters` helper in ``meili_acl`` filters out empty
    strings, but inlined callers should check the return value.
    """
    if not values:
        return ""
    escaped = ", ".join(quote(v) for v in values)
    return f"{field} IN [{escaped}]"


def build_gte(field: str, value: str) -> str:
    """Build a ``field >= "value"`` predicate with proper escaping."""
    return f"{field} >= {quote(value)}"


def build_lte(field: str, value: str) -> str:
    """Build a ``field <= "value"`` predicate with proper escaping."""
    return f"{field} <= {quote(value)}"

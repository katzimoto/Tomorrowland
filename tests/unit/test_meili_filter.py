from __future__ import annotations

import pytest

from services.search.meili_filter import (
    build_eq,
    build_gte,
    build_in,
    build_lte,
    escape_list,
    escape_value,
    quote,
)

# ---------------------------------------------------------------------------
# escape_value
# ---------------------------------------------------------------------------


def test_escape_value_passes_through_safe_string() -> None:
    assert escape_value("engineering") == "engineering"


def test_escape_value_empty_string() -> None:
    assert escape_value("") == ""


def test_escape_value_escapes_double_quote() -> None:
    """A double quote inside a value must be backslash-escaped so it does
    not close the surrounding quoted value and break the filter expression.
    """
    assert escape_value('a"b') == 'a\\"b'


def test_escape_value_escapes_backslash() -> None:
    """A backslash must be escaped before any escaped quote is emitted so
    the round-trip stays correct.
    """
    assert escape_value("a\\b") == "a\\\\b"


def test_escape_value_escapes_backslash_then_quote() -> None:
    # Backslash gets escaped first, quote second. The literal " becomes \"
    # without its backslash being re-escaped.
    assert escape_value('a\\"b') == 'a\\\\\\"b'


def test_escape_value_strips_null_byte() -> None:
    assert escape_value("a\x00b") == "ab"


def test_escape_value_preserves_whitespace_control_chars() -> None:
    # Tab / newline / carriage return are valid inside a quoted Meilisearch value
    assert escape_value("a\tb\nc\rd") == "a\tb\nc\rd"


def test_escape_value_strips_other_control_chars() -> None:
    # 0x01, 0x02, 0x1f, 0x7f must all be stripped
    for ch in ("\x01", "\x02", "\x1f", "\x7f"):
        assert escape_value(f"a{ch}b") == "ab"


def test_escape_value_rejects_backtick() -> None:
    """Backticks have no valid escape inside a quoted value and indicate the
    value is being placed in the wrong part of the filter expression.
    """
    with pytest.raises(ValueError, match="backtick"):
        escape_value("`id` = 1")


def test_escape_value_rejects_unbalanced_open_paren() -> None:
    with pytest.raises(ValueError, match="parentheses"):
        escape_value("foo (bar")


def test_escape_value_rejects_unbalanced_close_paren() -> None:
    with pytest.raises(ValueError, match="parentheses"):
        escape_value("foo bar)")


def test_escape_value_allows_balanced_parens() -> None:
    assert escape_value("foo (bar) baz") == "foo (bar) baz"


# ---------------------------------------------------------------------------
# escape_list
# ---------------------------------------------------------------------------


def test_escape_list_returns_new_list() -> None:
    original = ["a", 'b"c']
    out = escape_list(original)
    assert out == ["a", 'b\\"c']
    assert out is not original


def test_escape_list_empty() -> None:
    assert escape_list([]) == []


# ---------------------------------------------------------------------------
# quote
# ---------------------------------------------------------------------------


def test_quote_wraps_in_double_quotes() -> None:
    assert quote("hello") == '"hello"'


def test_quote_escapes_inner_quotes() -> None:
    assert quote('a"b') == '"a\\"b"'


def test_quote_handles_empty() -> None:
    assert quote("") == '""'


# ---------------------------------------------------------------------------
# build_eq
# ---------------------------------------------------------------------------


def test_build_eq_simple() -> None:
    assert build_eq("metadata.source", "upload") == 'metadata.source = "upload"'


def test_build_eq_escapes_value() -> None:
    assert build_eq("title", 'a"b') == 'title = "a\\"b"'


def test_build_eq_with_unicode() -> None:
    # Hebrew letters must pass through unchanged. The escape function only
    # touches ASCII control characters, quotes, and backslashes.
    assert build_eq("metadata.author", "שלום") == 'metadata.author = "שלום"'


def test_build_in_rejects_backtick_value() -> None:
    """Backticks have no valid escape inside a quoted value — propagate
    the ValueError from escape_value through build_in so callers fail fast
    rather than emit a broken filter expression.
    """
    with pytest.raises(ValueError, match="backtick"):
        build_in("metadata.tags", ["normal", "`bad`"])


def test_build_in_rejects_unbalanced_paren_value() -> None:
    with pytest.raises(ValueError, match="parentheses"):
        build_in("metadata.tags", ["foo (bar"])


def test_quote_empty_list_via_build_in_returns_empty() -> None:
    """build_in with no values must yield an empty string so the caller
    can skip the predicate without a Meilisearch IN [] syntax error.
    """
    assert build_in("metadata.tags", []) == ""


# ---------------------------------------------------------------------------
# build_in
# ---------------------------------------------------------------------------


def test_build_in_single_value() -> None:
    assert build_in("metadata.source", ["upload"]) == 'metadata.source IN ["upload"]'


def test_build_in_multiple_values() -> None:
    assert (
        build_in("metadata.source", ["upload", "local"]) == 'metadata.source IN ["upload", "local"]'
    )


def test_build_in_empty_returns_empty_string() -> None:
    """Empty IN [] is a syntax error in Meilisearch. The helper returns the
    empty string so callers can AND it with other predicates safely.
    """
    assert build_in("metadata.source", []) == ""


def test_build_in_escapes_each_value() -> None:
    result = build_in("metadata.tags", ['a"b', "c\\d"])
    assert result == 'metadata.tags IN ["a\\"b", "c\\\\d"]'


# ---------------------------------------------------------------------------
# build_gte / build_lte
# ---------------------------------------------------------------------------


def test_build_gte_iso_date() -> None:
    assert (
        build_gte("metadata.created_at", "2024-01-01T00:00:00Z")
        == 'metadata.created_at >= "2024-01-01T00:00:00Z"'
    )


def test_build_lte_iso_date() -> None:
    assert (
        build_lte("metadata.created_at", "2024-12-31T23:59:59Z")
        == 'metadata.created_at <= "2024-12-31T23:59:59Z"'
    )


def test_build_gte_escapes_value() -> None:
    assert build_gte("metadata.author", 'a"b') == 'metadata.author >= "a\\"b"'

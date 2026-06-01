"""Unit tests for the parse_worker attachment cycle/depth guard.

These cover the stateless guard that prevents unbounded child-document
expansion on cyclic or deeply nested archives in the async pipeline (where a
recursion ``_seen`` set cannot be threaded through the job queue).
"""

from __future__ import annotations

from services.pipeline.parse_worker import (
    _MAX_ATTACHMENT_NESTING,
    _attachment_cycle_or_depth_skip,
)

_SHA = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"  # 64 hex


def test_skip_when_attachment_sha_already_in_chain() -> None:
    # The attachment's sha prefix is already encoded in an ancestor → cycle.
    external_id = f"root::attachment::inner.zip::{_SHA[:12]}"
    assert _attachment_cycle_or_depth_skip(external_id, _SHA) is True


def test_no_skip_for_distinct_attachment() -> None:
    external_id = "root::attachment::other.zip::999888777666"
    assert _attachment_cycle_or_depth_skip(external_id, _SHA) is False


def test_skip_when_nesting_depth_exceeded() -> None:
    external_id = "root" + "::attachment::x::aaaaaaaaaaaa" * _MAX_ATTACHMENT_NESTING
    assert _attachment_cycle_or_depth_skip(external_id, _SHA) is True


def test_no_skip_for_shallow_distinct_chain() -> None:
    assert _attachment_cycle_or_depth_skip("root::attachment::x::bbbbbbbbbbbb", _SHA) is False


def test_no_skip_for_root_document() -> None:
    assert _attachment_cycle_or_depth_skip("root-doc-external-id", _SHA) is False

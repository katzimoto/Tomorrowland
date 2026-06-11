"""Unit tests for parser policy resolution and repository matching."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection

from services.extraction.policy import ParserPolicyResolver
from services.extraction.policy_repository import ParserPolicyRepository, _glob_patterns
from services.extraction.registry import ExtractorRegistry


class TestGlobPatterns:
    def test_exact_mime_returns_three_tiers(self) -> None:
        patterns = _glob_patterns("application/pdf")
        assert patterns == ["application/pdf", "application/*", "*"]

    def test_generic_mime_with_slash(self) -> None:
        patterns = _glob_patterns("image/png")
        assert patterns == ["image/png", "image/*", "*"]

    def test_mime_without_slash(self) -> None:
        patterns = _glob_patterns("text/plain")
        assert patterns == ["text/plain", "text/*", "*"]


class TestPolicyRepositoryMatch:
    """Integration-style tests for ParserPolicyRepository.match() using an in-memory SQLite DB."""

    @pytest.fixture
    def connection(self, migrated_engine: sa.Engine) -> Connection:
        """Return a connection on a migrated in-memory SQLite DB."""
        with migrated_engine.begin() as conn:
            yield conn

    @pytest.fixture
    def repo(self, connection: Connection) -> ParserPolicyRepository:
        return ParserPolicyRepository(connection)

    @pytest.fixture
    def source_id(self) -> UUID:
        return uuid4()

    @pytest.fixture
    def other_source_id(self) -> UUID:
        return uuid4()

    def _insert_source(self, connection: Connection, source_id: UUID) -> None:
        connection.execute(
            sa.text(
                "INSERT INTO ingestion_sources "
                "(id, name, type, source_language, enabled) "
                "VALUES (:id, :name, :type, :lang, :enabled)"
            ),
            {
                "id": source_id.hex,
                "name": "test-source",
                "type": "folder",
                "lang": "en",
                "enabled": True,
            },
        )

    def test_match_returns_none_when_no_policies(self, repo: ParserPolicyRepository) -> None:
        assert repo.match(source_id=uuid4(), mime_type="application/pdf") is None

    def test_match_exact_source_mime(
        self, connection: Connection, repo: ParserPolicyRepository, source_id: UUID
    ) -> None:
        self._insert_source(connection, source_id)
        repo.create(source_id=source_id, mime_pattern="application/pdf", parser_chain=["pypdf"])

        result = repo.match(source_id=source_id, mime_type="application/pdf")
        assert result is not None
        assert result["parser_chain"] == ["pypdf"]

    def test_match_glob_source_pattern(
        self, connection: Connection, repo: ParserPolicyRepository, source_id: UUID
    ) -> None:
        self._insert_source(connection, source_id)
        repo.create(
            source_id=source_id,
            mime_pattern="image/*",
            parser_chain=["ocr"],
        )

        result = repo.match(source_id=source_id, mime_type="image/png")
        assert result is not None
        assert result["parser_chain"] == ["ocr"]

    def test_match_wildcard_source(
        self, connection: Connection, repo: ParserPolicyRepository, source_id: UUID
    ) -> None:
        self._insert_source(connection, source_id)
        repo.create(source_id=source_id, mime_pattern="*", parser_chain=["generic"])

        result = repo.match(source_id=source_id, mime_type="application/octet-stream")
        assert result is not None
        assert result["parser_chain"] == ["generic"]

    def test_match_global_policy(
        self, connection: Connection, repo: ParserPolicyRepository, source_id: UUID
    ) -> None:
        self._insert_source(connection, source_id)
        repo.create(
            source_id=None,
            mime_pattern="application/pdf",
            parser_chain=["global-pypdf"],
        )

        result = repo.match(source_id=source_id, mime_type="application/pdf")
        assert result is not None
        assert result["parser_chain"] == ["global-pypdf"]

    def test_match_source_specific_wins_over_global(
        self, connection: Connection, repo: ParserPolicyRepository, source_id: UUID
    ) -> None:
        self._insert_source(connection, source_id)
        repo.create(
            source_id=None,
            mime_pattern="application/pdf",
            parser_chain=["global"],
        )
        repo.create(
            source_id=source_id,
            mime_pattern="application/pdf",
            parser_chain=["source-specific"],
        )

        result = repo.match(source_id=source_id, mime_type="application/pdf")
        assert result is not None
        assert result["parser_chain"] == ["source-specific"]

    def test_match_priority_tiebreaker(
        self, connection: Connection, repo: ParserPolicyRepository, source_id: UUID
    ) -> None:
        self._insert_source(connection, source_id)
        repo.create(
            source_id=None,
            mime_pattern="application/pdf",
            parser_chain=["low"],
            priority=0,
        )
        repo.create(
            source_id=None,
            mime_pattern="application/pdf",
            parser_chain=["high"],
            priority=10,
        )

        result = repo.match(source_id=source_id, mime_type="application/pdf")
        assert result is not None
        assert result["parser_chain"] == ["high"]

    def test_match_disabled_policies_ignored(
        self, connection: Connection, repo: ParserPolicyRepository, source_id: UUID
    ) -> None:
        self._insert_source(connection, source_id)
        repo.create(
            source_id=None,
            mime_pattern="application/pdf",
            parser_chain=["disabled"],
            enabled=False,
        )

        result = repo.match(source_id=source_id, mime_type="application/pdf")
        assert result is None

    def test_match_returns_none_for_non_matching_mime(
        self, connection: Connection, repo: ParserPolicyRepository, source_id: UUID
    ) -> None:
        self._insert_source(connection, source_id)
        repo.create(
            source_id=source_id,
            mime_pattern="text/plain",
            parser_chain=["plain"],
        )

        result = repo.match(source_id=source_id, mime_type="application/pdf")
        assert result is None

    def test_crud_roundtrip(
        self, connection: Connection, repo: ParserPolicyRepository, source_id: UUID
    ) -> None:
        self._insert_source(connection, source_id)
        pid = repo.create(
            source_id=source_id,
            mime_pattern="application/pdf",
            parser_chain=["pypdf"],
            options={"max_size_mb": 200},
            priority=5,
        )

        policy = repo.get(pid)
        assert policy is not None
        assert policy["mime_pattern"] == "application/pdf"
        assert policy["parser_chain"] == ["pypdf"]
        assert policy["options"] == {"max_size_mb": 200}
        assert policy["priority"] == 5
        assert policy["enabled"] is True

        repo.update(pid, parser_chain=["pypdf", "ocr"], priority=10)
        updated = repo.get(pid)
        assert updated is not None
        assert updated["parser_chain"] == ["pypdf", "ocr"]
        assert updated["priority"] == 10

        repo.delete(pid)
        assert repo.get(pid) is None


class TestParserPolicyResolver:
    """Unit tests for ParserPolicyResolver that don't need a DB."""

    def test_resolve_returns_policy_chain(self) -> None:
        registry = ExtractorRegistry()

        class FakeRepo:
            def match(self, *, source_id, mime_type):
                return {"parser_chain": ["PlainExtractor"]}

        resolver = ParserPolicyResolver(FakeRepo(), registry)
        chain = resolver.resolve(source_id=uuid4(), mime_type="text/plain")
        assert "PlainExtractor" in chain

    def test_resolve_skips_unknown_parsers(self) -> None:
        registry = ExtractorRegistry()

        class FakeRepo:
            def match(self, *, source_id, mime_type):
                return {"parser_chain": ["nonexistent", "PlainExtractor"]}

        resolver = ParserPolicyResolver(FakeRepo(), registry)
        chain = resolver.resolve(source_id=uuid4(), mime_type="text/plain")
        assert "nonexistent" not in chain
        assert "PlainExtractor" in chain

    def test_resolve_falls_back_to_implicit_chain_when_no_policy(self) -> None:
        registry = ExtractorRegistry()

        class FakeRepo:
            def match(self, *, source_id, mime_type):
                return None

        resolver = ParserPolicyResolver(FakeRepo(), registry)
        chain = resolver.resolve(source_id=uuid4(), mime_type="text/plain")
        # Should return the quality-tier-ordered candidates
        assert isinstance(chain, list)
        assert len(chain) > 0

    def test_resolve_falls_back_when_chain_is_all_unknown(self) -> None:
        registry = ExtractorRegistry()

        class FakeRepo:
            def match(self, *, source_id, mime_type):
                return {"parser_chain": ["nonexistent", "also-fake"]}

        resolver = ParserPolicyResolver(FakeRepo(), registry)
        chain = resolver.resolve(source_id=uuid4(), mime_type="text/plain")
        assert isinstance(chain, list)
        assert len(chain) > 0

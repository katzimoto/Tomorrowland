"""Tests for CitationFeedbackRepository."""

from __future__ import annotations

from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Engine

from services.chat.citation_feedback import CitationFeedbackCreate, CitationFeedbackRepository


def _create_user(connection: sa.Connection) -> UUID:
    user_id = uuid4()
    connection.execute(
        sa.text("INSERT INTO users (id, email, auth_source) VALUES (:id, :email, 'local')"),
        {"id": user_id.hex, "email": f"{uuid4().hex}@test.com"},
    )
    return user_id


def _make(
    doc_id: UUID,
    user_id: UUID,
    feedback_type: str = "other",
    **kwargs: object,
) -> CitationFeedbackCreate:
    return CitationFeedbackCreate(
        document_id=doc_id,
        feedback_type=feedback_type,
        user_id=user_id,
        **kwargs,
    )


def test_create_returns_feedback_with_all_fields(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        doc_id = uuid4()
        msg_id = uuid4()

        repo = CitationFeedbackRepository(conn)
        result = repo.create(
            CitationFeedbackCreate(
                citation_id="cit-1",
                message_id=msg_id,
                document_id=doc_id,
                chunk_id="chunk-abc",
                feedback_type="wrong_passage",
                comment="This passage is incorrect.",
                user_id=user_id,
            )
        )

    assert result.id is not None
    assert result.citation_id == "cit-1"
    assert result.message_id == msg_id
    assert result.document_id == doc_id
    assert result.chunk_id == "chunk-abc"
    assert result.feedback_type == "wrong_passage"
    assert result.comment == "This passage is incorrect."
    assert result.user_id == user_id
    assert result.created_at is not None


def test_create_with_optional_fields_none(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)

        repo = CitationFeedbackRepository(conn)
        result = repo.create(
            CitationFeedbackCreate(
                document_id=uuid4(),
                feedback_type="other",
                user_id=user_id,
            )
        )

    assert result.id is not None
    assert result.citation_id is None
    assert result.message_id is None
    assert result.chunk_id is None
    assert result.comment is None
    assert result.feedback_type == "other"


def test_list_by_document_returns_only_matching_rows(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        doc_id = uuid4()
        other_doc_id = uuid4()

        repo = CitationFeedbackRepository(conn)
        repo.create(_make(doc_id, user_id, "correct"))
        repo.create(_make(doc_id, user_id, "wrong_passage"))
        repo.create(_make(other_doc_id, user_id, "other"))

        results = repo.list_by_document(doc_id)

    assert len(results) == 2
    assert all(r.document_id == doc_id for r in results)


def test_list_by_document_empty_for_unknown_document(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        repo = CitationFeedbackRepository(conn)
        results = repo.list_by_document(uuid4())

    assert results == []


def test_list_by_document_pagination(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        doc_id = uuid4()

        repo = CitationFeedbackRepository(conn)
        for _ in range(5):
            repo.create(_make(doc_id, user_id))

        page1 = repo.list_by_document(doc_id, limit=2, offset=0)
        page2 = repo.list_by_document(doc_id, limit=2, offset=2)
        page3 = repo.list_by_document(doc_id, limit=2, offset=4)

    assert len(page1) == 2
    assert len(page2) == 2
    assert len(page3) == 1
    all_ids = {r.id for r in page1 + page2 + page3}
    assert len(all_ids) == 5


def test_list_by_message_returns_only_matching_rows(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        doc_id = uuid4()
        msg_id = uuid4()
        other_msg_id = uuid4()

        repo = CitationFeedbackRepository(conn)
        repo.create(_make(doc_id, user_id, "correct", message_id=msg_id))
        repo.create(_make(doc_id, user_id, "wrong_passage", message_id=msg_id))
        repo.create(_make(doc_id, user_id, "other", message_id=other_msg_id))

        results = repo.list_by_message(msg_id)

    assert len(results) == 2
    assert all(r.message_id == msg_id for r in results)


def test_list_by_message_empty_for_unknown_message(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        repo = CitationFeedbackRepository(conn)
        results = repo.list_by_message(uuid4())

    assert results == []


def test_list_by_feedback_type_filters_correctly(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)

        repo = CitationFeedbackRepository(conn)
        for _ in range(3):
            repo.create(_make(uuid4(), user_id, "wrong_passage"))
        repo.create(_make(uuid4(), user_id, "correct"))

        results = repo.list_by_feedback_type("wrong_passage")

    assert len(results) == 3
    assert all(r.feedback_type == "wrong_passage" for r in results)


def test_list_by_feedback_type_pagination(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)

        repo = CitationFeedbackRepository(conn)
        for _ in range(4):
            repo.create(_make(uuid4(), user_id, "unsupported_claim"))

        page1 = repo.list_by_feedback_type("unsupported_claim", limit=2, offset=0)
        page2 = repo.list_by_feedback_type("unsupported_claim", limit=2, offset=2)

    assert len(page1) == 2
    assert len(page2) == 2
    all_ids = {r.id for r in page1 + page2}
    assert len(all_ids) == 4


def test_results_ordered_by_created_at_desc(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn:
        user_id = _create_user(conn)
        doc_id = uuid4()

        repo = CitationFeedbackRepository(conn)
        first = repo.create(_make(doc_id, user_id, "correct"))
        second = repo.create(_make(doc_id, user_id, "wrong_passage"))

        results = repo.list_by_document(doc_id)

    # Most recent first
    assert results[0].id == second.id
    assert results[1].id == first.id

from __future__ import annotations

import contextlib
import json
import logging
import time
from collections.abc import Generator
from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError

from services.api._helpers import _config_bool
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.chat import ChatMessage, ChatRepository, ChatSession, rewrite_query
from services.chat.models import ChatMessageCreate, ChatScope, ChatSessionCreate, ChatSessionUpdate
from services.intelligence.task_defaults import TaskDefaultResolver
from services.rag.reranker import CrossEncoderReranker, NoOpReranker
from services.rag.service import RagService
from services.search.factory import build_encoder
from services.search.qdrant import QdrantSearchClient
from shared.correlation import get_correlation_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


def _require_chat_enabled(request: Request) -> None:
    if not request.app.state.settings.feature_document_chat:
        raise HTTPException(status_code=404, detail="Document Chat is disabled")


class ChatCreateRequest(BaseModel):
    scope_type: str
    scope_ids: list[str] = []
    title: str | None = None


class ChatMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class ChatUpdateRequest(BaseModel):
    title: str | None = None


def _session_response(session: ChatSession) -> dict[str, Any]:
    return {
        "id": str(session.id),
        "user_id": str(session.user_id),
        "title": session.title,
        "scope_type": session.scope_type,
        "scope_ids": session.scope_ids,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "archived_at": session.archived_at.isoformat() if session.archived_at else None,
        "message_count": len(session.metadata.get("_messages", [])),
    }


def _message_response(msg: ChatMessage, *, include_trace: bool = False) -> dict[str, Any]:
    resp: dict[str, Any] = {
        "id": str(msg.id),
        "session_id": str(msg.session_id),
        "role": msg.role,
        "content": msg.content,
        "rewritten_query": msg.rewritten_query,
        "citations": msg.citations,
        "model": msg.model,
        "latency_ms": msg.latency_ms,
        "created_at": msg.created_at.isoformat(),
    }
    if include_trace:
        resp["retrieval_trace"] = msg.retrieval_trace
    return resp


def _check_system_config_flag(connection: sa.Connection) -> None:
    """Check the feature.document_chat config flag (cached)."""
    from shared.config_cache import get_cached_config

    value = get_cached_config(connection, "feature.document_chat")
    if value is not None and not _config_bool(value, default=False):
        raise HTTPException(status_code=404, detail="Document Chat is disabled")


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


@router.post("/sessions")
def create_session(
    body: ChatCreateRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    _require_chat_enabled(request)

    with request.app.state.engine.begin() as connection:
        _check_system_config_flag(connection)
        repo = ChatRepository(connection)
        session = repo.create_session(
            ChatSessionCreate(
                user_id=user.sub,
                scope_type=body.scope_type,
                scope_ids=body.scope_ids,
                title=body.title or "New Chat",
            )
        )
        return _session_response(session)


@router.get("/sessions")
def list_sessions(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    limit: int = 20,
    offset: int = 0,
    archived: bool = False,
) -> dict[str, Any]:
    _require_chat_enabled(request)

    with request.app.state.engine.begin() as connection:
        _check_system_config_flag(connection)
        repo = ChatRepository(connection)
        sessions, total = repo.list_sessions(
            user.sub,
            limit=limit,
            offset=offset,
            archived=archived,
        )
        return {
            "sessions": [_session_response(s) for s in sessions],
            "total": total,
        }


@router.get("/sessions/{session_id}")
def get_session(
    session_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    _require_chat_enabled(request)

    with request.app.state.engine.begin() as connection:
        _check_system_config_flag(connection)
        repo = ChatRepository(connection)
        session = repo.get_session(
            user.sub,
            session_id,
            include_messages=True,
        )
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        messages = session.metadata.pop("_messages", [])
        return {
            **_session_response(session),
            "messages": [_message_response(m, include_trace=user.is_admin) for m in messages],
        }


@router.patch("/sessions/{session_id}")
def update_session(
    session_id: UUID,
    body: ChatUpdateRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    _require_chat_enabled(request)

    with request.app.state.engine.begin() as connection:
        _check_system_config_flag(connection)
        repo = ChatRepository(connection)
        updated = repo.update_session(
            user.sub,
            session_id,
            ChatSessionUpdate(title=body.title, archived_at=None),
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return _session_response(updated)


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    _require_chat_enabled(request)

    with request.app.state.engine.begin() as connection:
        _check_system_config_flag(connection)
        repo = ChatRepository(connection)
        deleted = repo.delete_session(user.sub, session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"ok": True}


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/messages")
def create_message(
    session_id: UUID,
    body: ChatMessageRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    _require_chat_enabled(request)

    with request.app.state.engine.begin() as connection:
        _check_system_config_flag(connection)
        repo = ChatRepository(connection)
        # Validate session exists and belongs to user
        session = repo.get_session(user.sub, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        # 1. Load prior messages for query rewrite (before persisting current user message)
        prior_messages = repo.list_messages(session_id)

        # 2. Persist user message
        repo.create_message(
            ChatMessageCreate(
                session_id=session_id,
                role="user",
                content=body.content,
            )
        )

        # 3. Build and validate session scope
        try:
            chat_scope = ChatScope(
                scope_type=session.scope_type,  # type: ignore[arg-type]
                scope_ids=session.scope_ids,
            )
        except ValidationError as exc:
            msg = exc.errors()[0]["msg"]
            raise HTTPException(status_code=400, detail=f"Invalid session scope: {msg}") from exc

        if chat_scope.scope_type == "folder":
            # Folder metadata is not stored in the Qdrant payload; full support is deferred.
            # TODO: implement folder scope when folder_id is indexed in vector payloads.
            raise HTTPException(
                status_code=400,
                detail="Folder-scoped chat is not yet supported. Please use a different scope.",
            )

        # Validate that the user still has access to scoped documents (revocation check).
        if not user.is_admin and chat_scope.scope_type in (
            "single_document",
            "selected_documents",
            "current_search_results",
        ):
            _scope_auth_repo = AuthRepository(connection)
            for doc_id_str in chat_scope.scope_ids:
                try:
                    doc_uuid = UUID(doc_id_str)
                except ValueError as exc:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "One or more documents in this chat's scope are no longer accessible."
                        ),
                    ) from exc
                source_id = _scope_auth_repo.document_source_id(doc_uuid)
                if source_id is None or not _scope_auth_repo.user_can_access_source(
                    user,  # type: ignore[arg-type]
                    source_id,
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "One or more documents in this chat's scope are no longer accessible."
                        ),
                    )

        # 4. Optionally rewrite query for follow-up turns (utility model)
        question = body.content
        rewritten_query: str | None = None
        settings = request.app.state.settings
        resolver: TaskDefaultResolver | None = getattr(
            request.app.state, "task_default_resolver", None
        )

        utility_resolved = resolver.resolve("utility") if resolver and resolver.loaded else None
        utility_model = (
            utility_resolved.model_name
            if utility_resolved and utility_resolved.model_name
            else settings.effective_utility_model
        )
        rewrite_client = (
            resolver.build_llm_provider("utility") if resolver and resolver.loaded else None
        )
        rewrite_client = rewrite_client or request.app.state.llm_provider
        if settings.feature_document_chat_query_rewrite and prior_messages:
            rewritten_query = rewrite_query(
                question,
                prior_messages,
                rewrite_client,
                model=utility_model,
            )
            question = rewritten_query

        # 5. Build RAG service and answer
        if user.is_admin:
            group_ids: list[str] = []
        else:
            _auth_repo = AuthRepository(connection)
            _effective = set(user.groups) | set(_auth_repo.get_effective_group_ids(user.groups))
            group_ids = [str(g) for g in _effective]
            if not group_ids:
                raise HTTPException(
                    status_code=403,
                    detail="You do not belong to any groups with document access.",
                )

        encoder = build_encoder(settings)
        qdrant_client = request.app.state.qdrant_client or QdrantSearchClient(
            url=settings.qdrant_url,
            dimension=encoder.dimension,
        )
        chat_llm = resolver.build_llm_provider("chat") if resolver and resolver.loaded else None
        ollama_client = chat_llm or request.app.state.llm_provider

        from shared.config_cache import get_cached_config

        _sp = get_cached_config(connection, "llm.qa_system_prompt")
        system_prompt = _sp if _sp else None

        reranker_resolved = resolver.resolve("reranking") if resolver and resolver.loaded else None
        reranker_model = (
            reranker_resolved.model_name
            if reranker_resolved and reranker_resolved.model_name
            else settings.effective_reranker_model
        )
        reranker: Any = NoOpReranker()
        if settings.feature_document_chat_reranker:
            reranker = CrossEncoderReranker(
                ollama_client=ollama_client,
                min_score=3.0,
                top_n=8,
                model=reranker_model,
            )
        rag = RagService(
            qdrant_client=qdrant_client,
            encoder=encoder,
            ollama_client=ollama_client,
            connection=connection,
            system_prompt=system_prompt,
            max_chunks=settings.rag_max_chunks,
            max_tokens_context=settings.rag_max_tokens_context,
            score_threshold=settings.rag_score_threshold,
            meili_provider=request.app.state.meili_provider,
            reranker=reranker,
            enable_metadata_search=settings.feature_document_chat_metadata_search,
            enable_translated_text=settings.feature_document_chat_translated_text,
            enable_hierarchy_expansion=settings.feature_document_chat_hierarchy_expansion,
        )

        phase_start = time.perf_counter()
        try:
            result = rag.answer(
                question=question,
                group_ids=group_ids,
                top_k=body.top_k,
                allow_all=user.is_admin,
                scope=chat_scope,
            )
        except Exception as exc:
            logger.warning(
                "Chat RAG degraded session_id=%s error_type=%s correlation_id=%s",
                session_id,
                exc.__class__.__name__,
                get_correlation_id(),
            )
            assistant_msg = repo.create_message(
                ChatMessageCreate(
                    session_id=session_id,
                    role="assistant",
                    content="I could not search the document collection right now.",
                    rewritten_query=rewritten_query,
                )
            )
            return _message_response(assistant_msg)

        latency_ms = int((time.perf_counter() - phase_start) * 1000)

        citations = [
            {
                "citation_id": c.citation_id,
                "document_id": c.document_id,
                "doc_title": c.doc_title,
                "chunk_text": c.chunk_text,
                "score": c.score,
                "chunk_index": c.chunk_index,
                "source_id": c.source_id,
                "page_number": c.page_number,
                "section_heading": c.section_heading,
                "language": c.language,
                "translated_from": c.translated_from,
            }
            for c in result.citations
        ]
        assistant_msg = repo.create_message(
            ChatMessageCreate(
                session_id=session_id,
                role="assistant",
                content=result.answer,
                rewritten_query=rewritten_query,
                citations=citations,
                retrieval_trace=(
                    result.retrieval_trace.model_dump() if result.retrieval_trace else None
                ),
                model=result.model,
                latency_ms=latency_ms,
            )
        )

        return _message_response(assistant_msg, include_trace=user.is_admin)


@router.get("/sessions/{session_id}/messages/{message_id}/trace")
def get_message_trace(
    session_id: UUID,
    message_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    """Return the retrieval trace for an assistant message (admin/developer only)."""
    _require_chat_enabled(request)
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    with request.app.state.engine.begin() as connection:
        _check_system_config_flag(connection)
        repo = ChatRepository(connection)
        session = repo.get_session(user.sub, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")
        messages = repo.list_messages(session_id)
        msg = next((m for m in messages if m.id == message_id), None)
        if msg is None:
            raise HTTPException(status_code=404, detail="Message not found")
        if msg.retrieval_trace is None:
            raise HTTPException(status_code=404, detail="No retrieval trace for this message")
        return {"message_id": str(msg.id), "retrieval_trace": msg.retrieval_trace}


@router.post("/sessions/{session_id}/messages/stream")
def create_message_stream(
    session_id: UUID,
    body: ChatMessageRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> StreamingResponse:
    """Stream a RAG answer with SSE phase/token events.

    Requires ``FEATURE_DOCUMENT_CHAT_STREAMING=true``.
    """
    _require_chat_enabled(request)
    settings = request.app.state.settings
    if not settings.feature_document_chat_streaming:
        raise HTTPException(status_code=404, detail="Not found")

    connection = request.app.state.engine.connect()
    txn = connection.begin()
    try:
        _check_system_config_flag(connection)
        repo = ChatRepository(connection)
        session = repo.get_session(user.sub, session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

        prior_messages = repo.list_messages(session_id)

        try:
            chat_scope = ChatScope(
                scope_type=session.scope_type,  # type: ignore[arg-type]
                scope_ids=session.scope_ids,
            )
        except ValidationError as exc:
            msg = exc.errors()[0]["msg"]
            raise HTTPException(status_code=400, detail=f"Invalid session scope: {msg}") from exc

        if chat_scope.scope_type == "folder":
            raise HTTPException(
                status_code=400,
                detail="Folder-scoped chat is not yet supported. Please use a different scope.",
            )

        if not user.is_admin and chat_scope.scope_type in (
            "single_document",
            "selected_documents",
            "current_search_results",
        ):
            _scope_auth_repo = AuthRepository(connection)
            for doc_id_str in chat_scope.scope_ids:
                try:
                    doc_uuid = UUID(doc_id_str)
                except ValueError:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "One or more documents in this chat's scope are no longer accessible."
                        ),
                    ) from None
                source_id = _scope_auth_repo.document_source_id(doc_uuid)
                if source_id is None or not _scope_auth_repo.user_can_access_source(
                    user,  # type: ignore[arg-type]
                    source_id,
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "One or more documents in this chat's scope are no longer accessible."
                        ),
                    )

        question = body.content
        rewritten_query: str | None = None
        resolver: TaskDefaultResolver | None = getattr(
            request.app.state, "task_default_resolver", None
        )

        utility_resolved = resolver.resolve("utility") if resolver and resolver.loaded else None
        utility_model = (
            utility_resolved.model_name
            if utility_resolved and utility_resolved.model_name
            else settings.effective_utility_model
        )
        rewrite_client = (
            resolver.build_llm_provider("utility") if resolver and resolver.loaded else None
        )
        rewrite_client = rewrite_client or request.app.state.llm_provider
        if settings.feature_document_chat_query_rewrite and prior_messages:
            rewritten_query = rewrite_query(
                question,
                prior_messages,
                rewrite_client,
                model=utility_model,
            )
            question = rewritten_query

        if user.is_admin:
            group_ids: list[str] = []
        else:
            _auth_repo = AuthRepository(connection)
            _effective = set(user.groups) | set(_auth_repo.get_effective_group_ids(user.groups))
            group_ids = [str(g) for g in _effective]
            if not group_ids:
                raise HTTPException(
                    status_code=403, detail="You do not belong to any groups with document access."
                )

        encoder = build_encoder(settings)
        qdrant_client = request.app.state.qdrant_client or QdrantSearchClient(
            url=settings.qdrant_url,
            dimension=encoder.dimension,
        )
        chat_llm = resolver.build_llm_provider("chat") if resolver and resolver.loaded else None
        ollama_client = chat_llm or request.app.state.llm_provider

        from shared.config_cache import get_cached_config

        _sp = get_cached_config(connection, "llm.qa_system_prompt")
        system_prompt = _sp if _sp else None

        reranker_resolved = resolver.resolve("reranking") if resolver and resolver.loaded else None
        reranker_model = (
            reranker_resolved.model_name
            if reranker_resolved and reranker_resolved.model_name
            else settings.effective_reranker_model
        )
        reranker: Any = NoOpReranker()
        if settings.feature_document_chat_reranker:
            reranker = CrossEncoderReranker(
                ollama_client=ollama_client,
                min_score=3.0,
                top_n=8,
                model=reranker_model,
            )

        rag = RagService(
            qdrant_client=qdrant_client,
            encoder=encoder,
            ollama_client=ollama_client,
            connection=connection,
            system_prompt=system_prompt,
            max_chunks=settings.rag_max_chunks,
            max_tokens_context=settings.rag_max_tokens_context,
            score_threshold=settings.rag_score_threshold,
            meili_provider=request.app.state.meili_provider,
            reranker=reranker,
            enable_metadata_search=settings.feature_document_chat_metadata_search,
            enable_translated_text=settings.feature_document_chat_translated_text,
            enable_hierarchy_expansion=settings.feature_document_chat_hierarchy_expansion,
        )

        # Persist the user message now that scope validation passed.
        repo.create_message(
            ChatMessageCreate(
                session_id=session_id,
                role="user",
                content=body.content,
            )
        )

        # Persist the user's question durably before streaming starts so a
        # mid-stream client disconnect cannot discard it. The assistant reply is
        # written in its own transaction inside event_stream() below.
        txn.commit()

        def _sse_format(event: str, data: dict[str, Any]) -> str:
            return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"

        def event_stream() -> Generator[str, None, None]:
            not_found_answer = (
                "I could not find any relevant information in the documents you have access to."
            )
            # The user message is already committed; this transaction covers only
            # the assistant reply, so a mid-stream disconnect keeps the question
            # and discards just the partial answer.
            assistant_txn = connection.begin()
            committed = False
            try:
                for event, data in rag.answer_stream(
                    question=question,
                    group_ids=group_ids,
                    top_k=body.top_k,
                    allow_all=user.is_admin,
                    scope=chat_scope,
                ):
                    if event == "done":
                        answer_text = data.get("answer") or not_found_answer
                        msg = repo.create_message(
                            ChatMessageCreate(
                                session_id=session_id,
                                role="assistant",
                                content=answer_text,
                                rewritten_query=rewritten_query,
                                citations=data.get("citations") or [],
                                retrieval_trace=data.get("retrieval_trace"),
                                model=data.get("model"),
                                latency_ms=data.get("latency_ms"),
                            )
                        )
                        data["message_id"] = str(msg.id)
                        assistant_txn.commit()
                        committed = True
                    yield _sse_format(event, data)
            except GeneratorExit:
                # Client disconnected mid-stream: drop the partial assistant
                # transaction. The user message was committed before streaming.
                if not committed:
                    assistant_txn.rollback()
                raise
            except Exception:
                logger.exception(
                    "SSE stream failed session_id=%s correlation_id=%s",
                    session_id,
                    get_correlation_id(),
                )
                if not committed:
                    assistant_txn.rollback()
                # Persist a user-visible error message in its own transaction so
                # it survives even though the answer transaction was rolled back.
                with contextlib.suppress(Exception):
                    error_txn = connection.begin()
                    repo.create_message(
                        ChatMessageCreate(
                            session_id=session_id,
                            role="assistant",
                            content=(
                                "I encountered an issue generating an answer. Please try again."
                            ),
                            rewritten_query=rewritten_query,
                            citations=[],
                        )
                    )
                    error_txn.commit()
            finally:
                if not committed:
                    with contextlib.suppress(Exception):
                        assistant_txn.rollback()
                connection.close()

        return StreamingResponse(event_stream(), media_type="text/event-stream")
    except Exception:
        txn.rollback()
        connection.close()
        raise

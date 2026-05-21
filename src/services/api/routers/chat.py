from __future__ import annotations

import logging
import time
from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from services.api._helpers import _config_bool
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.chat import ChatMessage, ChatRepository, ChatSession
from services.chat.models import ChatMessageCreate, ChatSessionCreate, ChatSessionUpdate
from services.intelligence.ollama_client import OllamaClient
from services.rag.reranker import NoOpReranker
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


def _message_response(msg: ChatMessage) -> dict[str, Any]:
    return {
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


def _check_system_config_flag(connection: sa.Connection) -> None:
    row = (
        connection.execute(
            sa.text("SELECT value FROM system_config WHERE key = :key"),
            {"key": "feature.document_chat"},
        )
        .mappings()
        .first()
    )
    if row and not _config_bool(row["value"], default=False):
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
            "messages": [_message_response(m) for m in messages],
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

        # 1. Persist user message
        repo.create_message(
            ChatMessageCreate(
                session_id=session_id,
                role="user",
                content=body.content,
            )
        )

        # 2. Build RAG service and answer
        scope_document_id: str | None = None
        if session.scope_type == "single_document" and len(session.scope_ids) == 1:
            scope_document_id = session.scope_ids[0]

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

        encoder = build_encoder(request.app.state.settings)
        qdrant_client = request.app.state.qdrant_client or QdrantSearchClient(
            url=request.app.state.settings.qdrant_url,
            dimension=encoder.dimension,
        )
        ollama_client = request.app.state.ollama_client or OllamaClient(
            base_url=request.app.state.settings.ollama_url,
            model=request.app.state.settings.ollama_model,
        )

        prompt_row = (
            connection.execute(
                sa.text("SELECT value FROM system_config WHERE key = :key"),
                {"key": "llm.qa_system_prompt"},
            )
            .mappings()
            .first()
        )
        system_prompt = str(prompt_row["value"]) if prompt_row else None

        settings = request.app.state.settings
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
            reranker=NoOpReranker(),
        )

        phase_start = time.perf_counter()
        try:
            result = rag.answer(
                question=body.content,
                group_ids=group_ids,
                top_k=body.top_k,
                document_id=scope_document_id,
                allow_all=user.is_admin,
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
                )
            )
            return _message_response(assistant_msg)

        latency_ms = int((time.perf_counter() - phase_start) * 1000)

        # 3. Persist assistant message
        citations = [
            {
                "citation_id": c.citation_id,
                "document_id": c.document_id,
                "doc_title": c.doc_title,
                "chunk_text": c.chunk_text,
                "score": c.score,
                "chunk_index": c.chunk_index,
                "source_id": c.source_id,
            }
            for c in result.citations
        ]
        assistant_msg = repo.create_message(
            ChatMessageCreate(
                session_id=session_id,
                role="assistant",
                content=result.answer,
                citations=citations,
                model=result.model,
                latency_ms=latency_ms,
            )
        )

        return _message_response(assistant_msg)

from __future__ import annotations

import logging
from typing import Annotated, Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from services.api._helpers import _config_bool
from services.api.main import current_user
from services.auth.models import TokenPayload
from services.auth.repository import AuthRepository
from services.intelligence.ollama_client import OllamaClient
from services.rag.models import QuestionRequest
from services.rag.service import RagService
from services.search.factory import build_encoder
from services.search.qdrant import QdrantSearchClient
from shared.correlation import get_correlation_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["qa"])


@router.post("/qa")
def qa(
    body: QuestionRequest,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    if not request.app.state.settings.feature_rag_qa:
        raise HTTPException(status_code=404, detail="RAG Q&A is disabled")

    base_group_ids = [str(g) for g in user.groups]
    if not base_group_ids:
        return {
            "question": body.question,
            "answer": "You do not belong to any groups with document access.",
            "citations": [],
            "model": "",
        }

    with request.app.state.engine.begin() as connection:
        flag_row = (
            connection.execute(
                sa.text("SELECT value FROM system_config WHERE key = :key"),
                {"key": "feature.rag_qa"},
            )
            .mappings()
            .first()
        )
        if flag_row and not _config_bool(flag_row["value"], default=True):
            raise HTTPException(status_code=404, detail="RAG Q&A is disabled")

        if user.is_admin:
            group_ids: list[str] = []
        else:
            _auth_repo = AuthRepository(connection)
            _effective = set(user.groups) | set(_auth_repo.get_effective_group_ids(user.groups))
            group_ids = [str(g) for g in _effective]

        encoder = build_encoder(request.app.state.settings)
        qdrant_client = request.app.state.qdrant_client or QdrantSearchClient(
            url=request.app.state.settings.qdrant_url,
            dimension=encoder.dimension,
        )
        ollama_client = request.app.state.ollama_client or OllamaClient(
            base_url=request.app.state.settings.ollama_url,
            model=request.app.state.settings.ollama_model,
        )

        # Read system prompt from config
        prompt_row = (
            connection.execute(
                sa.text("SELECT value FROM system_config WHERE key = :key"),
                {"key": "llm.qa_system_prompt"},
            )
            .mappings()
            .first()
        )
        system_prompt = str(prompt_row["value"]) if prompt_row else None

        rag = RagService(
            qdrant_client=qdrant_client,
            encoder=encoder,
            ollama_client=ollama_client,
            connection=connection,
            system_prompt=system_prompt,
        )
        try:
            result = rag.answer(
                question=body.question,
                group_ids=group_ids,
                top_k=body.top_k,
            )
        except Exception as exc:
            logger.warning(
                "RAG Q&A degraded route=/qa stage=retrieval error_type=%s correlation_id=%s",
                exc.__class__.__name__,
                get_correlation_id(),
            )
            return {
                "question": body.question,
                "answer": (
                    "I could not search the document collection right now. Please try again later."
                ),
                "citations": [],
                "model": "",
            }
        return {
            "question": result.question,
            "answer": result.answer,
            "citations": [
                {
                    "doc_id": c.doc_id,
                    "doc_title": c.doc_title,
                    "chunk_text": c.chunk_text,
                    "score": c.score,
                }
                for c in result.citations
            ],
            "model": result.model,
        }

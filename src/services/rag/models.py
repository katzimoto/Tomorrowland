"""RAG Q&A models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """A citation backing an answer."""

    doc_id: str
    doc_title: str | None = None
    chunk_text: str
    score: float


class QuestionRequest(BaseModel):
    """Request body for RAG Q&A."""

    question: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class AnswerResponse(BaseModel):
    """Response body for RAG Q&A."""

    question: str
    answer: str
    citations: list[Citation]
    model: str

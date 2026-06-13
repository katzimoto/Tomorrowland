"""RAG Q&A models."""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, Field

from services.rag.trace_models import RetrievalTrace


class Citation(BaseModel):
    """A citation backing an answer."""

    citation_id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str
    doc_title: str | None = None
    chunk_text: str
    score: float
    chunk_index: int | None = None
    chunk_id: str | None = None
    text_lane: str | None = None
    source_id: str | None = None
    page_number: int | None = None
    section_heading: str | None = None
    language: str | None = None
    translated_from: str | None = None


class QuestionRequest(BaseModel):
    """Request body for RAG Q&A."""

    question: str = Field(..., min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    document_id: str | None = None


class AnswerResponse(BaseModel):
    """Response body for RAG Q&A."""

    question: str
    answer: str
    citations: list[Citation]
    retrieval_trace: RetrievalTrace | None = None
    model: str

"""Retrieval trace data structures for RAG instrumentation.

These models capture what happened during a RAG retrieval without storing
raw document text, full prompts, secrets, credentials, or internal paths.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RetrievalCandidateTrace(BaseModel):
    """Minimal metadata about a retrieved chunk — no raw document text.

    Fields are limited to identifiers, scores, and allowed metadata so the
    trace can be safely persisted, inspected, or exposed without leaking
    document contents or internal paths.
    """

    model_config = ConfigDict(frozen=True)

    document_id: str
    chunk_id: str | None = None
    chunk_index: int | None = None
    score: float
    source_id: str | None = None
    doc_title: str | None = None
    page_number: int | None = None
    section_heading: str | None = None
    language: str | None = None


class RetrievalStageTrace(BaseModel):
    """Timing and count for a single retrieval pipeline stage."""

    stage: str
    candidate_count: int
    timing_ms: float
    description: str | None = None


class RetrievalTrace(BaseModel):
    """Complete non-invasive trace of a RAG retrieval operation.

    Captures per-stage counts, timing, whether reranking was applied, and
    the final candidate set — without storing raw text, full prompts, or
    any secret/credential material.
    """

    stages: list[RetrievalStageTrace] = Field(default_factory=list)
    candidates: list[RetrievalCandidateTrace] = Field(default_factory=list)
    reranker_enabled: bool = False
    total_latency_ms: float = 0.0

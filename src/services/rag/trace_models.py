"""Retrieval trace data structures for RAG instrumentation.

These models capture what happened during a RAG retrieval without storing
raw document text, full prompts, secrets, credentials, or internal paths.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BackendAttributionTrace(BaseModel):
    """Score and rank of a candidate as returned by one retrieval backend."""

    model_config = ConfigDict(frozen=True)

    backend: str
    """One of: ``vector``, ``bm25``, ``metadata``, ``translated``."""
    score: float
    rank: int | None = None
    """1-based position in the backend's own result list (before fusion)."""


class RerankerDeltaTrace(BaseModel):
    """How a candidate moved through the cross-encoder reranker."""

    model_config = ConfigDict(frozen=True)

    input_rank: int
    """1-based rank in the fused list before reranking."""
    input_score: float
    """Fused score before reranking."""
    reranker_score: float | None = None
    """Raw cross-encoder score; None when the reranker did not expose it."""
    output_rank: int | None = None
    """1-based rank in the reranked list; None when the candidate was dropped."""
    dropped: bool = False
    """True when the candidate was removed by min-score or top-n cutoff."""


class DegradedBackendInfo(BaseModel):
    """Safe degraded-backend record — category only, no raw exception text."""

    model_config = ConfigDict(frozen=True)

    backend: str
    """The backend that failed: ``vector``, ``bm25``, ``metadata``, ``translated``,
    ``query_embedding``."""
    error_category: str
    """Broad error category: ``timeout``, ``connection_error``, ``unexpected_error``."""


class RetrievalCandidateTrace(BaseModel):
    """Metadata about a retrieved chunk — no raw document text.

    Fields are limited to identifiers, scores, ranks, and safe metadata so
    the trace can be persisted, inspected, or exposed without leaking document
    contents or internal paths.

    v2 fields (``backends``, ``fused_rank``, ``fused_score``, ``reranker_delta``,
    ``final_context_rank``) are optional and populated only when the pipeline
    has enough information to emit them.
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
    text_lane: str | None = None
    translated_from: str | None = None

    # v4: translation-version-aware metadata (#734)
    matched_text_kind: str | None = None
    """``original``, ``fast_translation``, or ``high_translation``."""
    translation_version_id: str | None = None
    """UUID of the :class:`~services.documents.models.DocumentTranslationVersion`
    that produced this chunk, when the chunk is translated."""
    translation_quality: str | None = None
    """``fast`` or ``high`` — the quality lane."""
    translation_validation_status: str | None = None
    """``ok``, ``warning``, or ``failed`` — from QE metadata (#733)."""

    # v2 attribution fields
    backends: list[BackendAttributionTrace] = Field(default_factory=list)
    """Which backends contributed to this candidate and at what score/rank."""
    fused_rank: int | None = None
    """1-based rank in the fused (merged) result list before filtering."""
    fused_score: float | None = None
    """Combined score after reciprocal-rank fusion."""
    reranker_delta: RerankerDeltaTrace | None = None
    """Reranker input/output ranks and score; None when reranking was not applied."""
    final_context_rank: int | None = None
    """1-based position in the final context passed to the LLM."""


class RetrievalStageTrace(BaseModel):
    """Timing and count for a single retrieval pipeline stage."""

    stage: str
    candidate_count: int
    timing_ms: float
    description: str | None = None


class ContextPackingTrace(BaseModel):
    """Trace of hierarchy-aware context expansion during RAG context packing."""

    model_config = ConfigDict(frozen=True)

    expansion_applied: bool = False
    """True when at least one chunk was expanded with parent/sibling layout blocks."""
    expanded_chunk_ids: list[str] = Field(default_factory=list)
    """Chunk IDs (from chunk_id) that were expanded."""
    parent_blocks_added: int = 0
    """Number of parent heading blocks added across all expansions."""
    sibling_blocks_added: int = 0
    """Number of sibling blocks added across all expansions."""
    budget_words: int = 0
    """Maximum context words for expansion (approximated from rag_max_tokens_context)."""
    dropped_for_budget: int = 0
    """Number of expansion candidates dropped because the budget was exhausted."""
    sections_matched: int = 0
    """Number of chunks whose (page_number, section_heading) matched a layout section."""
    sections_not_found: int = 0
    """Number of chunks whose (page_number, section_heading) did not match any section."""


class RetrievalTrace(BaseModel):
    """Complete non-invasive trace of a RAG retrieval operation.

    Captures per-stage counts, timing, whether reranking was applied, and
    the final candidate set — without storing raw text, full prompts, or
    any secret/credential material.

    ``trace_version`` is 2 for traces that include backend attribution and
    reranker deltas.  Consumers that only read v1 fields (``stages``,
    ``candidates``, ``reranker_enabled``, ``retrieval_degraded``,
    ``total_latency_ms``) remain unaffected.
    """

    trace_version: int = 2
    stages: list[RetrievalStageTrace] = Field(default_factory=list)
    candidates: list[RetrievalCandidateTrace] = Field(default_factory=list)
    reranker_enabled: bool = False
    retrieval_degraded: bool = False
    total_latency_ms: float = 0.0

    # v2 fields
    degraded_backends: list[DegradedBackendInfo] = Field(default_factory=list)
    """One entry per backend that failed; safe category string, no raw exception."""
    scope_filtered_count: int = 0
    """Candidates removed by document-scope / ACL post-filtering on BM25 branches."""
    dedup_count: int = 0
    """Candidates removed as cross-backend duplicates."""
    score_threshold_filtered_count: int = 0
    """Candidates removed for falling below the configured score threshold."""
    reranker_dropped_count: int = 0
    """Candidates dropped by the reranker (min-score or top-n cutoff)."""

    # v3: hierarchy expansion
    context_packing: ContextPackingTrace | None = None
    """Trace of hierarchy-aware context packing; None when expansion was not attempted."""

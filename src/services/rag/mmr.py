"""Maximal Marginal Relevance (MMR) diversification for retrieved chunks.

Hybrid retrieval + reranking frequently leave several near-identical passages
(often consecutive chunks of the same document/section) crowding the top of the
candidate list. Feeding all of them to the LLM wastes the context budget and
crowds out diverse supporting evidence. MMR re-selects a diverse-yet-relevant
subset by trading off, at each step, a candidate's relevance against its maximum
similarity to the already-selected chunks (Carbonell & Goldstein, 1998).

This first implementation measures redundancy with a **lexical** token-cosine
similarity over ``chunk_text``. Candidate embedding vectors are not carried
through the permission-filtered fusion path today, so an embedding-cosine
redundancy measure would require plumbing vectors through that path — a larger,
higher-risk change tracked as a follow-up. Lexical similarity captures the
near-duplicate-passage case (large verbatim overlap) well in practice.

Relevance is taken from the *input order*: the chunk list is already sorted
best-first by the upstream reranker / fusion, so a scale-invariant rank-based
relevance avoids mixing reranker and fused-score scales.
"""

from __future__ import annotations

import math
import re
from typing import Any

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    """Lower-cased word-token set for *text* (used for lexical similarity)."""
    return {t.lower() for t in _TOKEN_RE.findall(text)}


def _lexical_similarity(a: set[str], b: set[str]) -> float:
    """Token-set cosine similarity in ``[0.0, 1.0]``.

    ``|a ∩ b| / sqrt(|a| * |b|)`` — 1.0 for identical token sets, 0.0 when
    disjoint (or when either side is empty).
    """
    if not a or not b:
        return 0.0
    overlap = len(a & b)
    if overlap == 0:
        return 0.0
    return overlap / math.sqrt(len(a) * len(b))


def mmr_reorder(
    chunks: list[dict[str, Any]],
    *,
    lambda_: float,
    top_k: int,
) -> list[dict[str, Any]]:
    """Select a diverse, relevant subset of *chunks* using MMR.

    *chunks* must already be sorted best-first (relevance order). Each step picks
    the candidate maximising ``lambda_ * relevance - (1 - lambda_) * max_sim`` to
    the already-selected set, where ``relevance`` is the candidate's rank-based
    score and ``max_sim`` is its highest lexical similarity to a selected chunk.

    * ``lambda_ == 1.0`` reduces to pure relevance, i.e. the input order
      truncated to *top_k* (no diversification).
    * ``lambda_ == 0.0`` maximises diversity only.

    The original chunk dicts are returned unchanged (same objects), reordered and
    truncated to at most *top_k*. Ties resolve toward the lower input index, so
    the result is deterministic.
    """
    if top_k <= 0 or not chunks:
        return []
    if len(chunks) <= 1:
        return chunks[:top_k]

    n = len(chunks)
    # Rank-based relevance, best-first: chunks[0] -> 1.0, descending, > 0.
    relevance = [(n - i) / n for i in range(n)]
    token_sets = [_tokens(str(c.get("chunk_text") or "")) for c in chunks]

    selected: list[int] = []
    remaining = list(range(n))

    while remaining and len(selected) < top_k:
        best_idx = remaining[0]
        best_score = -math.inf
        for i in remaining:
            max_sim = max(
                (_lexical_similarity(token_sets[i], token_sets[j]) for j in selected), default=0.0
            )
            score = lambda_ * relevance[i] - (1.0 - lambda_) * max_sim
            # Strict ``>`` keeps the lower index on ties (remaining is ascending).
            if score > best_score:
                best_score = score
                best_idx = i
        selected.append(best_idx)
        remaining.remove(best_idx)

    return [chunks[i] for i in selected]

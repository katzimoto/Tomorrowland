"""RAG Q&A service."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.engine import Connection

from services.documents.repository import DocumentRepository
from services.intelligence.ollama_client import OllamaClient
from services.search.encoder import MockEncoder
from services.search.qdrant import QdrantSearchClient

from .models import AnswerResponse, Citation


class RagService:
    """Retrieval-Augmented Generation Q&A service.

    Retrieves relevant document chunks from Qdrant, assembles context,
    and generates an answer using a local LLM.
    """

    def __init__(
        self,
        qdrant_client: QdrantSearchClient,
        encoder: MockEncoder,
        ollama_client: OllamaClient,
        connection: Connection,
        system_prompt: str | None = None,
    ) -> None:
        self._qdrant = qdrant_client
        self._encoder = encoder
        self._ollama = ollama_client
        self._connection = connection
        self._system_prompt = system_prompt or (
            "You are a knowledge assistant. Answer based only on the context provided. "
            "If the context does not contain the answer, say so."
        )

    def answer(
        self,
        question: str,
        group_ids: list[str],
        top_k: int = 5,
    ) -> AnswerResponse:
        """Answer a question using RAG.

        Args:
            question: The user's question.
            group_ids: List of group IDs the user belongs to (for permission filtering).
            top_k: Number of chunks to retrieve.

        Returns:
            An AnswerResponse with the generated answer and citations.
        """
        # 1. Retrieve relevant chunks
        chunks = self._retrieve_chunks(question, group_ids, top_k)

        if not chunks:
            return AnswerResponse(
                question=question,
                answer=(
                    "I could not find any relevant information in the documents you have access to."
                ),
                citations=[],
                model=self._ollama._model,
            )

        # 2. Assemble context
        context = self._assemble_context(chunks)

        # 3. Generate answer
        prompt = self._build_prompt(question, context)
        try:
            answer_text = self._ollama.generate(prompt)
        except Exception:
            # Best-effort: return context-only fallback
            answer_text = (
                "I encountered an issue generating an answer. "
                "Here are the relevant passages I found:\n\n" + context
            )

        # 4. Build citations
        citations = [
            Citation(
                doc_id=c["doc_id"],
                doc_title=c.get("doc_title"),
                chunk_text=c["chunk_text"],
                score=c["score"],
            )
            for c in chunks
        ]

        return AnswerResponse(
            question=question,
            answer=answer_text,
            citations=citations,
            model=self._ollama._model,
        )

    def _retrieve_chunks(
        self,
        question: str,
        group_ids: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Retrieve top-K chunks from Qdrant filtered by group_ids."""
        query_vector = self._encoder.encode(question)
        results = self._qdrant.search(
            vector=query_vector,
            group_ids=group_ids,
            limit=top_k,
        )

        # Deduplicate by doc_id (keep highest score)
        seen: dict[str, dict[str, Any]] = {}
        for r in results:
            doc_id = r.doc_id
            if doc_id not in seen or r.score > seen[doc_id]["score"]:
                seen[doc_id] = {
                    "doc_id": doc_id,
                    "chunk_text": r.chunk_text or "",
                    "score": r.score,
                    "doc_title": None,
                }

        # Look up doc titles
        doc_repo = DocumentRepository(self._connection)
        for doc_id in seen:
            doc = doc_repo.get_by_id(UUID(doc_id))
            if doc:
                seen[doc_id]["doc_title"] = doc.title

        # Return sorted by score descending
        return sorted(seen.values(), key=lambda c: c["score"], reverse=True)

    def _assemble_context(self, chunks: list[dict[str, Any]]) -> str:
        """Build a context string from retrieved chunks."""
        passages: list[str] = []
        for i, chunk in enumerate(chunks, 1):
            title = chunk.get("doc_title") or "Untitled"
            text = chunk["chunk_text"]
            passages.append(f"[{i}] {title}:\n{text}")
        return "\n\n".join(passages)

    def _build_prompt(self, question: str, context: str) -> str:
        """Build the full prompt for the LLM."""
        return f"{self._system_prompt}\n\nContext:\n{context}\n\nQuestion: {question}\n\nAnswer:"

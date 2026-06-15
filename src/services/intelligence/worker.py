"""Intelligence worker for best-effort LLM tasks."""

from __future__ import annotations

import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from uuid import UUID

from services.intelligence.llm_provider import LLMProvider, parse_json_array
from services.intelligence.profile_repository import ProfileRepository
from services.intelligence.repository import IntelligenceRepository
from services.intelligence.summary_helpers import (
    MAX_SUMMARIZE_CHARS,
    SUMMARY_CHUNK_CHARS,
    build_reduce_prompt,
    chunk_content,
    content_hash,
    normalize_summary_output,
    safe_error_category,
)
from services.intelligence.task_defaults import TaskDefaultResolver
from shared.correlation import get_correlation_id
from shared.metrics import current_metrics

logger = logging.getLogger(__name__)

MAX_ENTITY_CHARS = 6000
MAX_TAG_CHARS = 4000
MAX_KEY_POINTS_CHARS = 8000
MAX_KEY_POINTS = 7
MAX_KEY_POINT_LENGTH = 400

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_HAS_DIGIT = re.compile(r"\d")
_HAS_PROPER_NOUN = re.compile(r"(?<!^)(?<![.!?]\s)\b[A-Z][a-z]+")


def _rule_based_key_points(text: str, max_points: int) -> list[str]:
    """Extract up to *max_points* key sentences from *text* without an LLM.

    Strategy: collect the first sentence of each paragraph as primary
    candidates, then fill remaining slots with sentences that carry a digit or
    a proper noun — a cheap proxy for factual density.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    seen: set[str] = set()
    points: list[str] = []

    def _add(sentence: str) -> bool:
        s = sentence.strip()[:MAX_KEY_POINT_LENGTH]
        if s and s not in seen:
            seen.add(s)
            points.append(s)
            return True
        return False

    for para in paragraphs:
        sentences = _SENTENCE_SPLIT.split(para)
        if sentences:
            _add(sentences[0])
        if len(points) >= max_points:
            break

    if len(points) < max_points:
        for para in paragraphs:
            for sentence in _SENTENCE_SPLIT.split(para):
                if _HAS_DIGIT.search(sentence) or _HAS_PROPER_NOUN.search(sentence):
                    _add(sentence)
                if len(points) >= max_points:
                    break
            if len(points) >= max_points:
                break

    return points


class IntelligenceWorker:
    """Run best-effort LLM tasks on document content.

    Tasks are read from ``system_config`` feature flags. Failures are logged
    and swallowed — they never block ingestion.

    When a *source_id* is provided alongside the document, the worker resolves
    the active SourceProfile for that source and applies the configured
    strategy fields to select existing code paths.
    """

    def __init__(
        self,
        repository: IntelligenceRepository,
        ollama_client: LLMProvider,
        config_source: Any | None = None,
        utility_model: str | None = None,
        resolver: TaskDefaultResolver | None = None,
        profile_repo: ProfileRepository | None = None,
    ) -> None:
        self._repo = repository
        self._ollama = ollama_client
        self._config = config_source
        self._resolver = resolver
        self._profile_repo = profile_repo
        # When set, cheap/repeated tasks use this model instead of the main
        # model. None means use the client default (single-model behavior).
        self._utility_model = utility_model or None
        # If no explicit utility_model but a resolver is available, resolve it.
        if self._utility_model is None and resolver is not None and resolver.loaded:
            utility = resolver.resolve("utility")
            if utility is not None and utility.model_name:
                self._utility_model = utility.model_name

    def process_document(
        self, document_id: UUID, content: str, source_id: UUID | None = None
    ) -> dict[str, int]:
        """Run enabled intelligence tasks for *document_id*.

        Tasks (summarize, extract_entities, auto_tag, key_points) run
        concurrently via a thread pool. Each task is independent — they
        share the same *content* but not each other's outputs.

        If *source_id* is provided and a profile_repo is configured, the
        active SourceProfile for that source is resolved and its strategy
        fields are used to select existing code paths.  If no active profile
        exists, current default behavior is preserved exactly.

        Failures in individual tasks are logged and swallowed so that LLM
        enrichment never blocks ingestion.

        Returns a dict with ``succeeded`` and ``failed`` counts.
        """
        # Resolve active SourceProfile for strategy routing
        profile: dict[str, Any] | None = None
        if source_id is not None and self._profile_repo is not None:
            try:
                profile = self._profile_repo.get_active_profile(source_id)
            except Exception:
                logger.warning(
                    "Failed to resolve SourceProfile for source_id=%s "
                    "document_id=%s; using defaults",
                    source_id,
                    document_id,
                    exc_info=True,
                )

        if profile is not None:
            logger.info(
                "Using SourceProfile for source_id=%s document_id=%s "
                "chunking=%s retrieval=%s extraction=%s",
                source_id,
                document_id,
                profile.get("chunking_strategy", "default"),
                profile.get("retrieval_strategy", "default"),
                profile.get("extraction_strategy", "default"),
            )

        tasks = self._enabled_tasks()
        if not tasks:
            return {"succeeded": 0, "failed": 0}

        # Capture metrics reference before submitting to threads —
        # ContextVar does not propagate to ThreadPoolExecutor workers.
        _metrics = current_metrics()

        # Track per-task outcomes so callers can decide whether enrichment
        # produced useful results.  Guarded by _outcomes_lock because _run
        # executes in multiple ThreadPoolExecutor threads concurrently.
        outcomes: dict[str, int] = {"succeeded": 0, "failed": 0}
        _outcomes_lock = threading.Lock()

        def _run(task: str) -> None:
            start = time.perf_counter()
            try:
                if task == "summarize":
                    self._summarize(document_id, content)
                elif task == "extract_entities":
                    self._extract_entities(document_id, content)
                elif task == "auto_tag":
                    self._auto_tag(document_id, content)
                elif task == "key_points":
                    self._extract_key_points(document_id, content)
                if _metrics is not None:
                    _metrics.intelligence_tasks_total.labels(task, "success").inc()
                    _metrics.intelligence_task_duration_seconds.labels(task).observe(
                        time.perf_counter() - start
                    )
                with _outcomes_lock:
                    outcomes["succeeded"] += 1
            except Exception:
                if _metrics is not None:
                    _metrics.intelligence_tasks_total.labels(task, "failure").inc()
                    _metrics.intelligence_task_duration_seconds.labels(task).observe(
                        time.perf_counter() - start
                    )
                with _outcomes_lock:
                    outcomes["failed"] += 1
                logger.exception(
                    "Intelligence task %s failed for document_id=%s correlation=%s",
                    task,
                    document_id,
                    get_correlation_id(),
                )

        # Bound the total time spent waiting on enrichment so a stuck task can't
        # hang ingestion. The budget lives on as_completed (which only yields
        # already-finished futures, so a per-future result(timeout=...) would
        # never fire); it raises once 120s pass without all tasks completing.
        pool = ThreadPoolExecutor(max_workers=len(tasks))
        futures = [pool.submit(_run, task) for task in tasks]
        try:
            for future in as_completed(futures, timeout=120):
                future.result()
        except TimeoutError:
            logger.error(
                "Intelligence tasks exceeded 120s budget for document_id=%s correlation=%s",
                document_id,
                get_correlation_id(),
            )
        finally:
            # A thread already running can't be cancelled in Python
            # (cancel() returns False), so don't block on it: cancel pending
            # tasks and return without waiting. A stuck task keeps running in
            # the background; its outcome is simply not reflected in `outcomes`.
            pool.shutdown(wait=False, cancel_futures=True)

        return outcomes

    def _enabled_tasks(self) -> list[str]:
        """Return list of enabled task names from system_config."""
        if self._config is None:
            # Default: all tasks enabled when no config source provided
            return ["summarize", "extract_entities", "auto_tag", "key_points"]

        tasks: list[str] = []
        if self._config.get("feature.summarization", True):
            tasks.append("summarize")
        if self._config.get("feature.entity_extraction", True):
            tasks.append("extract_entities")
        if self._config.get("feature.auto_tagging", True):
            tasks.append("auto_tag")
        if self._config.get("feature.key_points", True):
            tasks.append("key_points")
        return tasks

    def _summarize(self, document_id: UUID, content: str) -> None:
        """Generate and store a document summary.

        For short documents (<= MAX_SUMMARIZE_CHARS) uses a single LLM call.
        For long documents uses a map-reduce strategy: chunk summaries are
        generated separately, then reduced to a final summary.

        Structured JSON output from the model is parsed and normalized.
        If the model returns unparseable text, the raw output is stored as
        the summary text with ``degraded`` status.
        If the LLM call fails entirely, safe failure metadata is persisted.
        """
        stripped = content.strip()
        model = self._ollama.model
        input_chars = len(stripped)
        text_hash = content_hash(stripped)

        if not stripped:
            self._repo.upsert_summary(
                document_id,
                summary="",
                model=model,
                status="failed",
                error_type="empty_content",
                error_summary="empty_content",
                input_chars=0,
                content_hash=text_hash,
            )
            return

        try:
            if len(stripped) <= MAX_SUMMARIZE_CHARS:
                prompt = self._build_prompt(
                    "llm.summarization_prompt", stripped, MAX_SUMMARIZE_CHARS
                )
                # Short doc: single call uses main model for quality output
                raw = self._ollama.generate(prompt)
                normalized = normalize_summary_output(raw)
            else:
                chunks = chunk_content(stripped, SUMMARY_CHUNK_CHARS)

                def _summarize_chunk(chunk: str, chunk_index: int) -> tuple[int, str]:
                    chunk_prompt = self._build_prompt(
                        "llm.summarization_prompt", chunk, SUMMARY_CHUNK_CHARS
                    )
                    # Map phase: use utility model (cheap, repeated)
                    try:
                        chunk_raw = self._ollama.generate(chunk_prompt, model=self._utility_model)
                        parsed = normalize_summary_output(chunk_raw)
                        return chunk_index, parsed["summary"] or chunk
                    except Exception:
                        logger.warning(
                            "Chunk summary failed for chunk_index=%d document_id=%s; "
                            "using raw chunk text as fallback",
                            chunk_index,
                            document_id,
                        )
                        return chunk_index, chunk  # Degrade gracefully with raw text

                # Collect chunk summaries with their original indices so order
                # is preserved regardless of completion order.
                with ThreadPoolExecutor(max_workers=min(len(chunks), 4)) as pool:
                    futures = [
                        pool.submit(_summarize_chunk, chunk, idx)
                        for idx, chunk in enumerate(chunks)
                    ]
                    ordered: list[tuple[int, str]] = []
                    for future in as_completed(futures):
                        ordered.append(future.result())
                    chunk_summaries = [text for _, text in sorted(ordered, key=lambda x: x[0])]

                reduce_prompt = build_reduce_prompt(chunk_summaries)
                # Reduce phase: use main model for quality final output
                reduce_raw = self._ollama.generate(reduce_prompt)
                normalized = normalize_summary_output(reduce_raw)

            _norm_keys = ("language", "document_type", "source_text")
            _norm: dict[str, str | None] = {
                k: normalized[k] if normalized.get(k) != "unknown" else None for k in _norm_keys
            }
            norm_lang = _norm["language"]
            norm_doc_type = _norm["document_type"]
            norm_source = _norm["source_text"]
            summary_text = normalized["summary"].strip()
            if not summary_text:
                summary_text = stripped[:500].split(". ")[0] or stripped[:200]
                normalized["summary"] = summary_text
                normalized["status"] = "degraded"
            self._repo.upsert_summary(
                document_id,
                summary=normalized["summary"],
                model=model,
                status=normalized["status"],
                summary_bullets=normalized["bullets"],
                language=norm_lang,
                document_type=norm_doc_type,
                source_text=norm_source,
                input_chars=input_chars,
                content_hash=text_hash,
            )

        except Exception as exc:
            category = safe_error_category(exc)
            self._repo.upsert_summary(
                document_id,
                summary="",
                model=model,
                status="failed",
                error_type=category,
                error_summary=category,
                input_chars=input_chars,
                content_hash=text_hash,
            )

    def _extract_entities(self, document_id: UUID, content: str) -> None:
        """Extract entities and store them with document links.

        Failures are logged and swallowed so that a transient Ollama or DB
        error never blocks ingestion.
        """
        try:
            prompt = self._build_prompt("llm.entity_extraction_prompt", content, MAX_ENTITY_CHARS)
            result = self._ollama.generate(prompt)
            entities = parse_json_array(result)

            for item in entities:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                entity_type = str(item.get("type", "")).strip().lower()
                if not name or entity_type not in (
                    "person",
                    "organization",
                    "location",
                    "date",
                ):
                    continue

                entity_id = self._repo.upsert_entity(name, entity_type)
                self._repo.link_document_entity(document_id, entity_id)

            logger.info(
                "Extracted %d entities for document_id=%s",
                len(entities),
                document_id,
            )
        except Exception:
            logger.warning(
                "Entity extraction failed for document_id=%s correlation=%s",
                document_id,
                get_correlation_id(),
                exc_info=True,
            )

    def _auto_tag(self, document_id: UUID, content: str) -> None:
        """Generate tags and replace existing tags for the document.

        Failures are logged and swallowed so that a transient Ollama or DB
        error never blocks ingestion.
        """
        try:
            prompt = self._build_prompt("llm.auto_tag_prompt", content, MAX_TAG_CHARS)
            # Utility model: cheap, repeated tagging task
            result = self._ollama.generate(prompt, model=self._utility_model)
            parsed = parse_json_array(result)

            tags = [str(t).strip() for t in parsed if isinstance(t, str) and str(t).strip()]
            self._repo.replace_tags(document_id, tags)
            logger.info("Tagged document_id=%s with %d tags", document_id, len(tags))
        except Exception:
            logger.warning(
                "Auto-tag failed for document_id=%s correlation=%s",
                document_id,
                get_correlation_id(),
                exc_info=True,
            )

    def _extract_key_points(self, document_id: UUID, content: str) -> None:
        """Extract a short ordered list of key bullet points for the document.

        Rule-based by default: take the first sentence of each paragraph; if we
        still have room, fill with sentences that carry digits or proper nouns
        (a cheap "named-entity" proxy that does not require the LLM).
        Optionally augment with the LLM when ``llm.key_points_prompt`` is
        configured; LLM failures are caught and never abort the task.
        """
        truncated = content[:MAX_KEY_POINTS_CHARS]
        points = _rule_based_key_points(truncated, MAX_KEY_POINTS)

        llm_prompt = ""
        if self._config is not None:
            llm_prompt = str(self._config.get("llm.key_points_prompt", "") or "")
        if llm_prompt:
            try:
                # Utility model: cheap LLM augmentation of rule-based output
                response = self._ollama.generate(
                    f"{llm_prompt}\n\n{truncated}", model=self._utility_model
                )
                llm_points = parse_json_array(response)
                normalized = [
                    str(p).strip()[:MAX_KEY_POINT_LENGTH]
                    for p in llm_points
                    if isinstance(p, str) and str(p).strip()
                ]
                if normalized:
                    points = normalized[:MAX_KEY_POINTS]
            except Exception:
                logger.warning(
                    "LLM key_points augmentation failed for document_id=%s; "
                    "falling back to rule-based output",
                    document_id,
                    exc_info=True,
                )

        self._repo.upsert_key_points(document_id, points)
        logger.info("Extracted %d key points for document_id=%s", len(points), document_id)

    def _build_prompt(
        self,
        config_key: str,
        content: str,
        max_chars: int,
    ) -> str:
        """Build a prompt from config key + truncated content."""
        base_prompt = ""
        if self._config is not None:
            base_prompt = str(self._config.get(config_key, ""))
        if not base_prompt:
            # Fallback prompts when no config source
            fallbacks: dict[str, str] = {
                "llm.summarization_prompt": (
                    "Summarize the following document. "
                    "Output valid JSON with these keys:\n"
                    '{"summary": "<3-5 sentence summary>", '
                    '"bullets": ["<key point 1>", ...], '
                    '"language": "<en|he|ar|...>", '
                    '"document_type": "<report|email|contract|..."}'
                ),
                "llm.entity_extraction_prompt": (
                    "Extract named entities from the document as a JSON array. "
                    "Each entity must have name and type "
                    "(person, organization, location, date). "
                    'Format: [{"name": "...", "type": "..."}]'
                ),
                "llm.auto_tag_prompt": (
                    "Analyze the document content below and assign 3-7 specific, "
                    "relevant topic tags. Tags should reflect the document's main "
                    "themes, domain, and key concepts — not generic labels.\n"
                    "Output as a JSON array of strings. "
                    'Example: ["contract law", "data privacy", "vendor risk"]'
                ),
            }
            base_prompt = fallbacks.get(config_key, "")

        truncated = content[:max_chars]
        return f"{base_prompt}\n\n{truncated}"

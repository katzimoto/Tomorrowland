"""Intelligence worker for best-effort LLM tasks."""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from services.intelligence.ollama_client import OllamaClient
from services.intelligence.repository import IntelligenceRepository
from services.search.elastic import ElasticsearchSearchClient
from shared.correlation import get_correlation_id
from shared.metrics import current_metrics

logger = logging.getLogger(__name__)

MAX_SUMMARIZE_CHARS = 8000
MAX_ENTITY_CHARS = 6000
MAX_TAG_CHARS = 4000


class IntelligenceWorker:
    """Run best-effort LLM tasks on document content.

    Tasks are read from ``system_config`` feature flags. Failures are logged
    and swallowed — they never block ingestion.
    """

    def __init__(
        self,
        repository: IntelligenceRepository,
        ollama_client: OllamaClient,
        es_client: ElasticsearchSearchClient,
        config_source: Any | None = None,
    ) -> None:
        self._repo = repository
        self._ollama = ollama_client
        self._es = es_client
        self._config = config_source

    def process_document(self, doc_id: UUID, content: str) -> None:
        """Run enabled intelligence tasks for *doc_id*.

        Tasks run in order: summarize → extract_entities → auto_tag.
        On any failure, log and stop processing further tasks for this doc.
        """
        tasks = self._enabled_tasks()
        if not tasks:
            return

        for task in tasks:
            metrics = current_metrics()
            start = time.perf_counter()
            try:
                if task == "summarize":
                    self._summarize(doc_id, content)
                elif task == "extract_entities":
                    self._extract_entities(doc_id, content)
                elif task == "auto_tag":
                    self._auto_tag(doc_id, content)
                if metrics is not None:
                    metrics.intelligence_tasks_total.labels(task, "success").inc()
                    metrics.intelligence_task_duration_seconds.labels(task).observe(
                        time.perf_counter() - start
                    )
            except Exception:
                if metrics is not None:
                    metrics.intelligence_tasks_total.labels(task, "failure").inc()
                    metrics.intelligence_task_duration_seconds.labels(task).observe(
                        time.perf_counter() - start
                    )
                logger.exception(
                    "Intelligence task %s failed for doc_id=%s correlation=%s",
                    task,
                    doc_id,
                    get_correlation_id(),
                )
                break

    def _enabled_tasks(self) -> list[str]:
        """Return list of enabled task names from system_config."""
        if self._config is None:
            # Default: all tasks enabled when no config source provided
            return ["summarize", "extract_entities", "auto_tag"]

        tasks: list[str] = []
        if self._config.get("feature.summarization", True):
            tasks.append("summarize")
        if self._config.get("feature.entity_extraction", True):
            tasks.append("extract_entities")
        if self._config.get("feature.auto_tagging", True):
            tasks.append("auto_tag")
        return tasks

    def _summarize(self, doc_id: UUID, content: str) -> None:
        """Generate and store a document summary."""
        prompt = self._build_prompt("llm.summarization_prompt", content, MAX_SUMMARIZE_CHARS)
        summary = self._ollama.generate(prompt)
        model = self._ollama._model

        self._repo.upsert_summary(doc_id, summary, model)
        self._update_es_field(doc_id, "summary", summary)
        logger.info("Summarized doc_id=%s", doc_id)

    def _extract_entities(self, doc_id: UUID, content: str) -> None:
        """Extract entities and store them with document links."""
        prompt = self._build_prompt("llm.entity_extraction_prompt", content, MAX_ENTITY_CHARS)
        result = self._ollama.generate(prompt)
        entities = self._ollama.parse_json_array(result)

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
            self._repo.link_document_entity(doc_id, entity_id)

        # Update ES with entity names
        entity_names = [
            str(e.get("name", "")) for e in entities if isinstance(e, dict) and e.get("name")
        ]
        self._update_es_field(doc_id, "entities", entity_names)
        logger.info("Extracted %d entities for doc_id=%s", len(entities), doc_id)

    def _auto_tag(self, doc_id: UUID, content: str) -> None:
        """Generate tags and replace existing tags for the document."""
        prompt = self._build_prompt("llm.auto_tag_prompt", content, MAX_TAG_CHARS)
        result = self._ollama.generate(prompt)
        parsed = self._ollama.parse_json_array(result)

        tags = [str(t).strip() for t in parsed if isinstance(t, str) and str(t).strip()]
        self._repo.replace_tags(doc_id, tags)
        self._update_es_field(doc_id, "tags", tags)
        logger.info("Tagged doc_id=%s with %d tags", doc_id, len(tags))

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
                "llm.summarization_prompt": ("Summarize the following document in 3-5 sentences."),
                "llm.entity_extraction_prompt": (
                    "Extract named entities (people, organizations, locations) as a JSON array."
                ),
                "llm.auto_tag_prompt": (
                    "Assign 3-7 short topic tags to the following document as a JSON array."
                ),
            }
            base_prompt = fallbacks.get(config_key, "")

        truncated = content[:max_chars]
        return f"{base_prompt}\n\n{truncated}"

    def _update_es_field(
        self,
        doc_id: UUID,
        field: str,
        value: Any,
    ) -> None:
        """Update a single field in the Elasticsearch document."""
        try:
            self._es.update_document_field(str(doc_id), field, value)
        except Exception:
            logger.warning(
                "Failed to update ES field %s for doc_id=%s",
                field,
                doc_id,
                exc_info=True,
            )

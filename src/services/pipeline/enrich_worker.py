"""Enrich stage consumer — high-quality translation for frequently viewed documents.

Delegates the actual work to :class:`~services.pipeline.slow_worker.SlowWorker`,
which resolves the pending ``document_translation_versions`` record, re-translates,
re-chunks, and re-indexes the document into Meilisearch and Qdrant. Without this
delegation the enrich stage would translate the text but never mark the version
``available`` (leaving it ``pending`` forever) nor refresh the search indexes.
"""

from __future__ import annotations

import logging
from uuid import UUID

from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.slow_worker import SlowWorker
from shared.rabbit import RabbitClient

logger = logging.getLogger(__name__)


class EnrichConsumer(BaseConsumer):
    queue_name = "document.enrich.requested"
    worker_type = "enrich-worker"

    def __init__(
        self,
        rabbit: RabbitClient,
        job_repo: PipelineJobRepository,
        worker: SlowWorker,
        health_port: int = 8087,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._worker = worker

    def handle_message(
        self,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int,
        correlation_id: str,
        content_text: str = "",
        translated_text: str = "",
    ) -> None:
        # The enrich message does not carry the extracted text, so fall back to
        # the parse-stage payload when it is absent.
        text = content_text
        if not text:
            payload = self._job_repo.get_payload(document_id)
            text = (payload.get("content_text", "") if payload else None) or ""

        self._job_repo.mark_running_stage(job_id, "enrich")
        self._worker.process_document(document_id, content_text=text)
        self._job_repo.mark_succeeded(job_id)


def main() -> None:
    import logging

    import meilisearch
    import sqlalchemy as sa

    from services.documents.repository import DocumentRepository, TranslationVersionRepository
    from services.intelligence.factory import build_llm_provider
    from services.intelligence.repository import IntelligenceRepository
    from services.intelligence.worker import IntelligenceWorker
    from services.search.factory import build_encoder
    from services.search.meili_provider import MeilisearchSearchProvider
    from services.search.qdrant import QdrantSearchClient
    from services.translation.client import LibreTranslateClient
    from shared.config import Settings
    from shared.rabbit import RabbitClient

    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    engine = sa.create_engine(settings.postgres_url)
    connection = engine.connect()
    rabbit = RabbitClient(settings.rabbitmq_url, enabled=True)
    job_repo = PipelineJobRepository(connection)
    doc_repo = DocumentRepository(connection)
    version_repo = TranslationVersionRepository(connection)
    translator = LibreTranslateClient(base_url=settings.libretranslate_url)
    encoder = build_encoder(settings)
    qdrant_client = QdrantSearchClient(url=settings.qdrant_url)
    meili_client = meilisearch.Client(
        settings.meilisearch_url,
        api_key=settings.meilisearch_master_key,
    )
    meili = MeilisearchSearchProvider(meili_client)
    intelligence_worker = IntelligenceWorker(
        repository=IntelligenceRepository(connection),
        ollama_client=build_llm_provider(settings),
        utility_model=settings.effective_utility_model,
    )

    worker = SlowWorker(
        document_repository=doc_repo,
        translator=translator,
        encoder=encoder,
        qdrant_client=qdrant_client,
        version_repository=version_repo,
        meili_provider=meili,
        intelligence_worker=intelligence_worker,
    )
    consumer = EnrichConsumer(rabbit, job_repo, worker)
    consumer.run()

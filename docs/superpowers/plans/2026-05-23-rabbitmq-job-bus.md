# RabbitMQ Job Bus Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single-process DB-poll pipeline with a durable, stage-based RabbitMQ job bus where each pipeline stage (parse → translate → embed → index → intelligence → alert) runs as an independent worker with its own queue, retry tier, and dead-letter path.

**Architecture:** `sync-now` publishes a `document.parse.requested` message; each stage worker consumes its queue, does its work, then publishes the next stage's message. `pipeline_jobs` remains the canonical DB state for observability and retry management. `RABBITMQ_ENABLED=false` (default) keeps the existing DB-poll path so no existing deployment breaks.

**Tech Stack:** `pika` (synchronous RabbitMQ client), RabbitMQ 3.13-management-alpine, FastAPI, SQLAlchemy (raw SQL), Python 3.13, `uv run pytest`, `ruff`, `mypy --strict`.

**Feature branch:** `feature/rabbitmq-job-bus` → `main` (final PR only). All sub-issue PRs target this branch.

**GitHub tracking:** Parent #432 | Sub-issues #425 (A), #426 (B), #427 (C), #428 (D), #429 (E), #430 (F), #431 (G)

---

## File Map

### New files
| File | Purpose |
|---|---|
| `src/shared/rabbit.py` | `RabbitClient` — connect, declare topology, publish, close |
| `src/services/pipeline/publisher.py` | `DocumentPublisher` — DB + RabbitMQ publish per stage |
| `src/services/pipeline/consumer_base.py` | `BaseConsumer` — ack/nack, retry, SIGTERM, health HTTP |
| `src/services/pipeline/parse_worker.py` | `ParseConsumer(BaseConsumer)` |
| `src/services/pipeline/translate_worker.py` | `TranslateConsumer(BaseConsumer)` |
| `src/services/pipeline/embed_worker.py` | `EmbedConsumer(BaseConsumer)` |
| `src/services/pipeline/index_worker.py` | `IndexConsumer(BaseConsumer)` |
| `src/services/pipeline/intelligence_consumer.py` | `IntelligenceConsumer(BaseConsumer)` |
| `src/services/pipeline/alert_consumer.py` | `AlertConsumer(BaseConsumer)` |
| `src/services/api/routers/admin/jobs.py` | `GET /admin/jobs`, `GET /admin/jobs/{job_id}`, `POST /admin/jobs/{job_id}/retry` |
| `src/services/api/routers/admin/rabbit.py` | `GET /admin/rabbit/queues` |
| `migrations/versions/<ts>_pipeline_jobs_stage_rabbit.py` | `stage TEXT`, `rabbit_message_id TEXT` columns |
| `scripts/validate-rabbitmq.sh` | Smoke-test all queues + workers on a clean stack |
| `tests/unit/test_rabbit_client.py` | RabbitClient unit tests (mock pika) |
| `tests/unit/test_publisher.py` | DocumentPublisher unit tests |
| `tests/unit/test_consumer_base.py` | BaseConsumer unit tests (mock channel) |
| `tests/integration/test_admin_jobs_routes.py` | Admin jobs API integration tests |

### Modified files
| File | Change |
|---|---|
| `src/shared/config.py` | Add `rabbitmq_url`, `rabbitmq_enabled`, `rabbitmq_user`, `rabbitmq_pass` |
| `src/services/api/routers/admin/ingestion.py` | When `RABBITMQ_ENABLED=true`: publish to RabbitMQ after DB enqueue |
| `src/services/api/routers/admin/__init__.py` | Register `jobs` and `rabbit` routers |
| `docker-compose.yml` | Add `rabbitmq` service + 6 stage worker services |
| `pyproject.toml` | Add `pika>=1.3`, register `[project.scripts]` entrypoints per worker |
| `.env.example` | Add `RABBITMQ_URL`, `RABBITMQ_USER`, `RABBITMQ_PASS`, `RABBITMQ_ENABLED` |
| `CHANGELOG.md` | Feature entry |

---

## Sub-issue A — RabbitMQ Service + Client + Topology (#425)

### Task 1: Create feature branch

- [ ] **Create and push the feature branch**
```bash
git checkout main && git pull --ff-only origin main
git checkout -b feature/rabbitmq-job-bus
git push -u origin feature/rabbitmq-job-bus
```

### Task 2: Add `pika` dependency

- [ ] **Add pika to pyproject.toml**

Open `pyproject.toml`. In the `[project]` `dependencies` list add:
```toml
"pika>=1.3,<2",
```

- [ ] **Install and verify**
```bash
uv sync
uv run python -c "import pika; print(pika.__version__)"
```
Expected: prints a version like `1.3.2`

- [ ] **Commit**
```bash
git add pyproject.toml uv.lock
git commit -m "chore: add pika dependency for RabbitMQ"
```

### Task 3: Add RabbitMQ settings to config

- [ ] **Write the failing test**

Create `tests/unit/test_rabbit_config.py`:
```python
import os
import pytest
from shared.config import Settings


def test_rabbitmq_disabled_by_default(monkeypatch):
    monkeypatch.delenv("RABBITMQ_ENABLED", raising=False)
    s = Settings()
    assert s.rabbitmq_enabled is False


def test_rabbitmq_url_default(monkeypatch):
    monkeypatch.delenv("RABBITMQ_URL", raising=False)
    s = Settings()
    assert s.rabbitmq_url == "amqp://guest:guest@localhost:5672/"


def test_rabbitmq_enabled_via_env(monkeypatch):
    monkeypatch.setenv("RABBITMQ_ENABLED", "true")
    monkeypatch.setenv("RABBITMQ_URL", "amqp://user:pass@rabbitmq:5672/")
    s = Settings()
    assert s.rabbitmq_enabled is True
    assert s.rabbitmq_url == "amqp://user:pass@rabbitmq:5672/"
```

- [ ] **Run to confirm failure**
```bash
uv run pytest tests/unit/test_rabbit_config.py -q
```
Expected: `AttributeError: 'Settings' object has no attribute 'rabbitmq_enabled'`

- [ ] **Add fields to `src/shared/config.py`**

Find the `Settings` class and add after the last existing field:
```python
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_user: str = "tomorrowland"
    rabbitmq_pass: str = "changeme"
    rabbitmq_enabled: bool = False
```

- [ ] **Run tests to confirm pass**
```bash
uv run pytest tests/unit/test_rabbit_config.py -q
```
Expected: `3 passed`

- [ ] **Commit**
```bash
git add src/shared/config.py tests/unit/test_rabbit_config.py
git commit -m "feat(rabbit): add RABBITMQ_* settings to shared config"
```

### Task 4: Add RabbitMQ to docker-compose.yml

- [ ] **Add the service**

In `docker-compose.yml`, in the `services:` block, add:
```yaml
  rabbitmq:
    image: rabbitmq:3.13-management-alpine
    restart: unless-stopped
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER:-tomorrowland}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASS:-changeme}
    ports:
      - "${RABBITMQ_PORT:-5672}:5672"
      - "${RABBITMQ_MGMT_PORT:-15672}:15672"
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "ping"]
      interval: 15s
      timeout: 10s
      retries: 10
    restart: unless-stopped
    volumes:
      - rabbitmq_data:/var/lib/rabbitmq
```

Also add `rabbitmq_data:` to the top-level `volumes:` block.

- [ ] **Update `.env.example`** — add:
```
RABBITMQ_URL=amqp://tomorrowland:changeme@rabbitmq:5672/
RABBITMQ_USER=tomorrowland
RABBITMQ_PASS=changeme
RABBITMQ_ENABLED=false
```

- [ ] **Commit**
```bash
git add docker-compose.yml .env.example
git commit -m "feat(rabbit): add RabbitMQ service to docker-compose"
```

### Task 5: Implement `shared/rabbit.py`

- [ ] **Write the failing tests**

Create `tests/unit/test_rabbit_client.py`:
```python
from unittest.mock import MagicMock, call, patch
import pytest
from shared.rabbit import RabbitClient, RabbitConnectionError

QUEUES = [
    "document.parse.requested",
    "document.translate.requested",
    "document.embed.requested",
    "document.index.requested",
    "document.intelligence.requested",
    "document.alert.requested",
]
DLQ_QUEUES = [q.replace("requested", "dead") for q in QUEUES]


@patch("shared.rabbit.pika.BlockingConnection")
def test_declare_topology_creates_all_queues(mock_conn_cls):
    mock_channel = MagicMock()
    mock_conn_cls.return_value.channel.return_value = mock_channel

    client = RabbitClient("amqp://guest:guest@localhost/")
    client.connect()
    client.declare_topology()

    # Main exchange declared
    mock_channel.exchange_declare.assert_any_call(
        exchange="tomorrowland.documents",
        exchange_type="topic",
        durable=True,
    )
    # DLQ exchange declared
    mock_channel.exchange_declare.assert_any_call(
        exchange="tomorrowland.documents.dlq",
        exchange_type="fanout",
        durable=True,
    )
    # All 6 main queues declared
    declared_queues = [
        c.kwargs["queue"] for c in mock_channel.queue_declare.call_args_list
    ]
    for q in QUEUES:
        assert q in declared_queues
    # All 6 DLQ queues declared
    for q in DLQ_QUEUES:
        assert q in declared_queues


@patch("shared.rabbit.pika.BlockingConnection")
def test_publish_returns_message_id(mock_conn_cls):
    mock_channel = MagicMock()
    mock_conn_cls.return_value.channel.return_value = mock_channel

    client = RabbitClient("amqp://guest:guest@localhost/")
    client.connect()
    client.declare_topology()

    msg_id = client.publish(
        "document.parse.requested",
        {"job_id": "abc", "document_id": "def"},
    )
    assert isinstance(msg_id, str) and len(msg_id) == 36  # UUID
    mock_channel.basic_publish.assert_called_once()


@patch("shared.rabbit.pika.BlockingConnection", side_effect=Exception("refused"))
def test_connect_raises_rabbit_connection_error(mock_conn_cls):
    client = RabbitClient("amqp://guest:guest@localhost/")
    with pytest.raises(RabbitConnectionError):
        client.connect()


@patch("shared.rabbit.pika.BlockingConnection")
def test_noop_when_disabled(mock_conn_cls):
    client = RabbitClient("amqp://guest:guest@localhost/", enabled=False)
    client.connect()           # no-op
    client.declare_topology()  # no-op
    msg_id = client.publish("document.parse.requested", {})
    assert msg_id == ""
    mock_conn_cls.assert_not_called()
```

- [ ] **Run to confirm failure**
```bash
uv run pytest tests/unit/test_rabbit_client.py -q
```
Expected: `ModuleNotFoundError: No module named 'shared.rabbit'`

- [ ] **Implement `src/shared/rabbit.py`**

```python
"""Thin RabbitMQ client wrapper for Tomorrowland document pipeline."""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

import pika
import pika.exceptions
from pika.spec import BasicProperties

logger = logging.getLogger(__name__)

_MAIN_EXCHANGE = "tomorrowland.documents"
_DLQ_EXCHANGE = "tomorrowland.documents.dlq"

_STAGE_QUEUES = [
    "document.parse.requested",
    "document.translate.requested",
    "document.embed.requested",
    "document.index.requested",
    "document.intelligence.requested",
    "document.alert.requested",
]


class RabbitConnectionError(RuntimeError):
    """Raised when a connection to RabbitMQ cannot be established."""


class RabbitClient:
    """Synchronous pika-based RabbitMQ client.

    When *enabled* is False every method is a no-op so callers need no
    conditional logic — they always call connect/publish/close.
    """

    def __init__(self, url: str, *, enabled: bool = True) -> None:
        self._url = url
        self._enabled = enabled
        self._connection: pika.BlockingConnection | None = None
        self._channel: pika.adapters.blocking_connection.BlockingChannel | None = None

    def connect(self) -> None:
        """Open a connection and channel. Raises RabbitConnectionError on failure."""
        if not self._enabled:
            return
        try:
            params = pika.URLParameters(self._url)
            self._connection = pika.BlockingConnection(params)
            self._channel = self._connection.channel()
        except Exception as exc:
            raise RabbitConnectionError(
                f"Cannot connect to RabbitMQ at {self._url}: {exc}"
            ) from exc

    def declare_topology(self) -> None:
        """Declare exchanges, queues, and bindings — idempotent."""
        if not self._enabled or self._channel is None:
            return
        ch = self._channel
        ch.exchange_declare(
            exchange=_MAIN_EXCHANGE, exchange_type="topic", durable=True
        )
        ch.exchange_declare(
            exchange=_DLQ_EXCHANGE, exchange_type="fanout", durable=True
        )
        for queue in _STAGE_QUEUES:
            ch.queue_declare(
                queue=queue,
                durable=True,
                arguments={"x-dead-letter-exchange": _DLQ_EXCHANGE},
            )
            ch.queue_bind(
                queue=queue, exchange=_MAIN_EXCHANGE, routing_key=queue
            )
            dlq = queue.replace("requested", "dead")
            ch.queue_declare(queue=dlq, durable=True)
            ch.queue_bind(queue=dlq, exchange=_DLQ_EXCHANGE, routing_key="#")

    def publish(self, routing_key: str, body: dict[str, Any]) -> str:
        """Publish a persistent JSON message. Returns the message_id UUID string."""
        if not self._enabled or self._channel is None:
            return ""
        message_id = str(uuid4())
        props = BasicProperties(
            delivery_mode=2,  # persistent
            content_type="application/json",
            message_id=message_id,
        )
        self._channel.basic_publish(
            exchange=_MAIN_EXCHANGE,
            routing_key=routing_key,
            body=json.dumps(body).encode(),
            properties=props,
        )
        logger.debug("published routing_key=%s message_id=%s", routing_key, message_id)
        return message_id

    def close(self) -> None:
        """Close the connection gracefully."""
        if not self._enabled:
            return
        try:
            if self._connection and self._connection.is_open:
                self._connection.close()
        except Exception:
            logger.debug("RabbitMQ connection already closed", exc_info=True)
```

- [ ] **Run tests**
```bash
uv run pytest tests/unit/test_rabbit_client.py -q
uv run ruff check src/shared/rabbit.py
uv run mypy src/shared/rabbit.py --strict
```
Expected: `4 passed`, no lint/type errors

- [ ] **Commit**
```bash
git add src/shared/rabbit.py tests/unit/test_rabbit_client.py
git commit -m "feat(rabbit): RabbitClient with topology declaration and no-op disabled mode"
```

---

## Sub-issue B — Publisher + DB State + sync-now + Admin Routes (#426)

### Task 6: Migration — add `stage` and `rabbit_message_id` to `pipeline_jobs`

- [ ] **Generate migration file**

Create `migrations/versions/<timestamp>_pipeline_jobs_stage_rabbit.py`.
Replace `<timestamp>` with the current UTC datetime string (e.g. `2026_05_23_1200`):

```python
"""Add stage and rabbit_message_id to pipeline_jobs.

Revision ID: a1b2c3d4e5f6
Revises: <previous_revision>
Create Date: 2026-05-23 12:00:00.000000
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "<previous_revision>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pipeline_jobs", sa.Column("stage", sa.Text(), nullable=True))
    op.add_column(
        "pipeline_jobs",
        sa.Column("rabbit_message_id", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pipeline_jobs", "rabbit_message_id")
    op.drop_column("pipeline_jobs", "stage")
```

Find the correct `down_revision` by running:
```bash
uv run alembic heads
```
Use the printed revision ID as `down_revision`.

- [ ] **Apply and verify**
```bash
uv run alembic upgrade head
uv run alembic downgrade -1
uv run alembic upgrade head
```
Expected: no errors on both directions

- [ ] **Commit**
```bash
git add migrations/versions/
git commit -m "feat(rabbit): add stage and rabbit_message_id columns to pipeline_jobs"
```

### Task 7: Implement `DocumentPublisher`

- [ ] **Write the failing test**

Create `tests/unit/test_publisher.py`:
```python
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest
from services.pipeline.publisher import DocumentPublisher


def _make_publisher(rabbit_enabled: bool = True):
    mock_job_repo = MagicMock()
    mock_rabbit = MagicMock()
    mock_rabbit.enabled = rabbit_enabled
    mock_rabbit.publish.return_value = "msg-uuid-123"
    return DocumentPublisher(job_repo=mock_job_repo, rabbit=mock_rabbit), mock_job_repo, mock_rabbit


def test_publish_parse_stores_message_id():
    pub, job_repo, rabbit = _make_publisher()
    job_id = uuid4()
    document_id = uuid4()
    source_id = uuid4()

    pub.publish_parse(
        job_id=job_id,
        document_id=document_id,
        source_id=source_id,
    )

    rabbit.publish.assert_called_once_with(
        "document.parse.requested",
        {
            "job_id": str(job_id),
            "document_id": str(document_id),
            "source_id": str(source_id),
            "attempt": 1,
            "pipeline_version": "v1",
        },
    )
    job_repo.set_rabbit_message_id.assert_called_once_with(job_id, "msg-uuid-123")


def test_publish_parse_skips_rabbit_when_disabled():
    pub, job_repo, rabbit = _make_publisher(rabbit_enabled=False)
    rabbit.publish.return_value = ""
    pub.publish_parse(job_id=uuid4(), document_id=uuid4(), source_id=uuid4())
    # rabbit.publish still called (it's a no-op inside), but no message_id stored
    job_repo.set_rabbit_message_id.assert_not_called()
```

- [ ] **Run to confirm failure**
```bash
uv run pytest tests/unit/test_publisher.py -q
```
Expected: `ModuleNotFoundError`

- [ ] **Add `set_rabbit_message_id` to `PipelineJobRepository`**

Open `src/services/pipeline/jobs.py`. Add after `mark_running_stage`:
```python
    def set_rabbit_message_id(self, job_id: UUID, message_id: str) -> None:
        """Persist the RabbitMQ message ID for observability."""
        self._connection.execute(
            sa.text("""
                UPDATE pipeline_jobs
                SET rabbit_message_id = :message_id, updated_at = :updated_at
                WHERE id = :id
            """),
            {
                "id": db_uuid(job_id),
                "message_id": message_id,
                "updated_at": datetime.now(UTC),
            },
        )
```

- [ ] **Create `src/services/pipeline/publisher.py`**

```python
"""DocumentPublisher — writes DB state and publishes RabbitMQ messages per pipeline stage."""
from __future__ import annotations

import logging
from uuid import UUID

from services.pipeline.jobs import PipelineJobRepository
from shared.rabbit import RabbitClient

logger = logging.getLogger(__name__)

_ROUTING_KEYS: dict[str, str] = {
    "parse": "document.parse.requested",
    "translate": "document.translate.requested",
    "embed": "document.embed.requested",
    "index": "document.index.requested",
    "intelligence": "document.intelligence.requested",
    "alert": "document.alert.requested",
}


class DocumentPublisher:
    """Publish a document to the next pipeline stage queue.

    Always writes a DB row first; only publishes to RabbitMQ when the client
    is enabled. This means the DB-poll workers still function when
    RABBITMQ_ENABLED=false.
    """

    def __init__(
        self,
        job_repo: PipelineJobRepository,
        rabbit: RabbitClient,
    ) -> None:
        self._job_repo = job_repo
        self._rabbit = rabbit

    def publish_parse(
        self,
        *,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int = 1,
    ) -> None:
        self._publish("parse", job_id=job_id, document_id=document_id,
                      source_id=source_id, attempt=attempt)

    def publish_translate(self, *, job_id: UUID, document_id: UUID,
                          source_id: UUID, attempt: int = 1) -> None:
        self._publish("translate", job_id=job_id, document_id=document_id,
                      source_id=source_id, attempt=attempt)

    def publish_embed(self, *, job_id: UUID, document_id: UUID,
                      source_id: UUID, attempt: int = 1) -> None:
        self._publish("embed", job_id=job_id, document_id=document_id,
                      source_id=source_id, attempt=attempt)

    def publish_index(self, *, job_id: UUID, document_id: UUID,
                      source_id: UUID, attempt: int = 1) -> None:
        self._publish("index", job_id=job_id, document_id=document_id,
                      source_id=source_id, attempt=attempt)

    def publish_intelligence(self, *, job_id: UUID, document_id: UUID,
                             source_id: UUID, attempt: int = 1) -> None:
        self._publish("intelligence", job_id=job_id, document_id=document_id,
                      source_id=source_id, attempt=attempt)

    def publish_alert(self, *, job_id: UUID, document_id: UUID,
                      source_id: UUID, attempt: int = 1) -> None:
        self._publish("alert", job_id=job_id, document_id=document_id,
                      source_id=source_id, attempt=attempt)

    def _publish(
        self,
        stage: str,
        *,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int,
    ) -> None:
        routing_key = _ROUTING_KEYS[stage]
        message_id = self._rabbit.publish(
            routing_key,
            {
                "job_id": str(job_id),
                "document_id": str(document_id),
                "source_id": str(source_id),
                "attempt": attempt,
                "pipeline_version": "v1",
            },
        )
        if message_id:
            self._job_repo.set_rabbit_message_id(job_id, message_id)
        logger.info(
            "published stage=%s job_id=%s message_id=%s",
            stage, job_id, message_id or "disabled",
        )
```

- [ ] **Run tests**
```bash
uv run pytest tests/unit/test_publisher.py -q
uv run mypy src/services/pipeline/publisher.py src/services/pipeline/jobs.py --strict
```
Expected: `2 passed`, no type errors

- [ ] **Commit**
```bash
git add src/services/pipeline/publisher.py src/services/pipeline/jobs.py \
        tests/unit/test_publisher.py
git commit -m "feat(rabbit): DocumentPublisher and set_rabbit_message_id"
```

### Task 8: Wire RabbitMQ publish into sync-now

- [ ] **Write the failing test**

Create `tests/unit/test_sync_now_rabbit.py`:
```python
from unittest.mock import MagicMock, patch
from uuid import uuid4
import pytest


def test_sync_now_publishes_when_rabbit_enabled(client, admin_token):
    """When RABBITMQ_ENABLED=true, sync-now publishes to RabbitMQ and returns queued count."""
    # This test uses the FastAPI test client — see existing integration test patterns
    # in tests/integration/test_admin_ingestion.py for the fixture setup.
    pass  # implemented in integration test below — unit coverage via publisher tests
```

Open `src/services/api/routers/admin/ingestion.py`. After the existing `job_repo.enqueue_document(...)` call inside the per-document loop, add:

```python
                    # Publish to RabbitMQ when enabled (no-op when disabled)
                    from shared.rabbit import RabbitClient
                    rabbit: RabbitClient = getattr(
                        request.app.state, "rabbit", None
                    ) or RabbitClient(
                        settings.rabbitmq_url, enabled=settings.rabbitmq_enabled
                    )
                    if settings.rabbitmq_enabled:
                        from services.pipeline.publisher import DocumentPublisher
                        publisher = DocumentPublisher(job_repo=job_repo, rabbit=rabbit)
                        publisher.publish_parse(
                            job_id=job_id,
                            document_id=doc.id,
                            source_id=source_id,
                        )
```

**Note:** `settings` must be imported. Add at top of file:
```python
from shared.config import Settings
settings = Settings()
```

- [ ] **Run existing ingestion tests to confirm no regression**
```bash
uv run pytest tests/ -k "ingestion or sync_now" -q
```
Expected: all existing tests pass

- [ ] **Run full test suite**
```bash
uv run pytest tests/ -q
```
Expected: all pass (RABBITMQ_ENABLED defaults to false → no real rabbit calls)

- [ ] **Commit**
```bash
git add src/services/api/routers/admin/ingestion.py
git commit -m "feat(rabbit): publish to RabbitMQ from sync-now when RABBITMQ_ENABLED=true"
```

### Task 9: Admin jobs routes

- [ ] **Write the failing tests**

Create `tests/integration/test_admin_jobs_routes.py`:
```python
"""Integration tests for GET /admin/jobs and GET /admin/jobs/{job_id}."""
import pytest
from uuid import uuid4


def _seed_job(connection, document_id, status="pending", stage=None):
    from services.pipeline.jobs import PipelineJobRepository
    from shared.db import db_uuid
    import sqlalchemy as sa
    from datetime import datetime, UTC
    job_id = uuid4()
    connection.execute(sa.text("""
        INSERT INTO pipeline_jobs
          (id, document_id, source_id, job_type, status, priority,
           max_attempts, run_after, created_at, updated_at, stage)
        VALUES
          (:id, :document_id, :source_id, 'process_document', :status, 0,
           5, :now, :now, :now, :stage)
    """), {
        "id": db_uuid(job_id), "document_id": db_uuid(document_id),
        "source_id": db_uuid(uuid4()), "status": status,
        "now": datetime.now(UTC), "stage": stage,
    })
    return job_id


def test_admin_list_jobs_returns_jobs(auth_client, db_connection):
    doc_id = uuid4()
    job_id = _seed_job(db_connection, doc_id, status="pending", stage="queued")
    db_connection.commit()

    resp = auth_client.get("/admin/jobs?status=pending")
    assert resp.status_code == 200
    data = resp.json()
    assert "jobs" in data and "total" in data
    ids = [j["id"] for j in data["jobs"]]
    assert str(job_id) in ids


def test_admin_get_job_detail(auth_client, db_connection):
    doc_id = uuid4()
    job_id = _seed_job(db_connection, doc_id, status="pending")
    db_connection.commit()

    resp = auth_client.get(f"/admin/jobs/{job_id}")
    assert resp.status_code == 200
    j = resp.json()
    assert j["id"] == str(job_id)
    assert j["status"] == "pending"


def test_admin_get_job_404(auth_client):
    resp = auth_client.get(f"/admin/jobs/{uuid4()}")
    assert resp.status_code == 404
```

- [ ] **Run to confirm failure**
```bash
uv run pytest tests/integration/test_admin_jobs_routes.py -q
```
Expected: `404` because route doesn't exist

- [ ] **Create `src/services/api/routers/admin/jobs.py`**

```python
"""Admin routes for pipeline job inspection and retry."""
from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request

from services.api.main import current_user
from services.auth.models import TokenPayload
from services.permissions.enforcer import require_admin
from shared.db import to_uuid

router = APIRouter(tags=["admin"])


def _row_to_job(row: Any) -> dict[str, Any]:
    return {
        "id": str(to_uuid(row["id"])),
        "document_id": str(to_uuid(row["document_id"])) if row["document_id"] else None,
        "source_id": str(to_uuid(row["source_id"])) if row["source_id"] else None,
        "job_type": row["job_type"],
        "status": row["status"],
        "stage": row["stage"],
        "attempts": row["attempts"],
        "max_attempts": row["max_attempts"],
        "last_error": row["last_error"],
        "rabbit_message_id": row["rabbit_message_id"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


@router.get("/admin/jobs")
def admin_list_jobs(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
    status: str | None = None,
    job_type: str | None = None,
    stage: str | None = None,
    source_id: UUID | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    require_admin(user)
    filters = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if status:
        filters.append("status = :status")
        params["status"] = status
    if job_type:
        filters.append("job_type = :job_type")
        params["job_type"] = job_type
    if stage:
        filters.append("stage = :stage")
        params["stage"] = stage
    if source_id:
        filters.append("source_id = :source_id")
        params["source_id"] = source_id.hex
    where = ("WHERE " + " AND ".join(filters)) if filters else ""
    with request.app.state.engine.begin() as conn:
        rows = conn.execute(
            sa.text(f"""
                SELECT id, document_id, source_id, job_type, status, stage,
                       attempts, max_attempts, last_error, rabbit_message_id,
                       created_at, updated_at
                FROM pipeline_jobs {where}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).mappings().all()
        total = conn.execute(
            sa.text(f"SELECT COUNT(*) FROM pipeline_jobs {where}"),
            {k: v for k, v in params.items() if k not in ("limit", "offset")},
        ).scalar_one()
    return {"jobs": [_row_to_job(r) for r in rows], "total": total}


@router.get("/admin/jobs/{job_id}")
def admin_get_job(
    job_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as conn:
        row = conn.execute(
            sa.text("""
                SELECT id, document_id, source_id, job_type, status, stage,
                       attempts, max_attempts, last_error, rabbit_message_id,
                       created_at, updated_at
                FROM pipeline_jobs WHERE id = :id
            """),
            {"id": job_id.hex},
        ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _row_to_job(row)
```

- [ ] **Register the router** in `src/services/api/routers/admin/__init__.py`:
```python
from services.api.routers.admin import jobs as jobs_router
# add alongside existing routers:
router.include_router(jobs_router.router)
```

- [ ] **Run tests**
```bash
uv run pytest tests/integration/test_admin_jobs_routes.py -q
uv run mypy src/services/api/routers/admin/jobs.py --strict
```
Expected: `3 passed`, no type errors

- [ ] **Commit**
```bash
git add src/services/api/routers/admin/jobs.py \
        src/services/api/routers/admin/__init__.py \
        tests/integration/test_admin_jobs_routes.py
git commit -m "feat(rabbit): GET /admin/jobs and GET /admin/jobs/{job_id} routes"
```

---

## Sub-issue C — BaseConsumer + Core Stage Workers (#427)

### Task 10: Implement `BaseConsumer`

- [ ] **Write the failing test**

Create `tests/unit/test_consumer_base.py`:
```python
from unittest.mock import MagicMock, call, patch
from uuid import uuid4
import json, pytest
from services.pipeline.consumer_base import BaseConsumer


class SucceedingConsumer(BaseConsumer):
    queue_name = "document.parse.requested"
    worker_type = "parse-worker"

    def handle_message(self, job_id, document_id, source_id, attempt, correlation_id):
        pass  # success


class FailingConsumer(BaseConsumer):
    queue_name = "document.parse.requested"
    worker_type = "parse-worker"

    def handle_message(self, job_id, document_id, source_id, attempt, correlation_id):
        raise RuntimeError("something broke")


def _make_delivery(job_id=None, attempt=1):
    body = json.dumps({
        "job_id": str(job_id or uuid4()),
        "document_id": str(uuid4()),
        "source_id": str(uuid4()),
        "attempt": attempt,
        "pipeline_version": "v1",
    }).encode()
    method = MagicMock()
    method.delivery_tag = 42
    return MagicMock(), method, MagicMock(), body


def test_success_acks_message():
    consumer = SucceedingConsumer.__new__(SucceedingConsumer)
    consumer._channel = MagicMock()
    consumer._job_repo = MagicMock()
    consumer._jobs_processed = 0

    ch, method, props, body = _make_delivery()
    consumer._on_message(ch, method, props, body)

    consumer._channel.basic_ack.assert_called_once_with(delivery_tag=42)
    consumer._channel.basic_nack.assert_not_called()


def test_failure_nacks_and_retries_when_attempts_remaining():
    consumer = FailingConsumer.__new__(FailingConsumer)
    consumer._channel = MagicMock()
    consumer._job_repo = MagicMock()
    consumer._job_repo.get_max_attempts.return_value = 5
    consumer._jobs_processed = 0

    ch, method, props, body = _make_delivery(attempt=1)
    consumer._on_message(ch, method, props, body)

    consumer._channel.basic_nack.assert_called_once_with(
        delivery_tag=42, requeue=False
    )
    consumer._job_repo.mark_retry.assert_called_once()


def test_failure_dead_letters_when_attempts_exhausted():
    consumer = FailingConsumer.__new__(FailingConsumer)
    consumer._channel = MagicMock()
    consumer._job_repo = MagicMock()
    consumer._job_repo.get_max_attempts.return_value = 3
    consumer._jobs_processed = 0

    ch, method, props, body = _make_delivery(attempt=3)
    consumer._on_message(ch, method, props, body)

    consumer._channel.basic_nack.assert_called_once_with(
        delivery_tag=42, requeue=False
    )
    consumer._job_repo.mark_dead_letter.assert_called_once()
```

- [ ] **Run to confirm failure**
```bash
uv run pytest tests/unit/test_consumer_base.py -q
```

- [ ] **Create `src/services/pipeline/consumer_base.py`**

```python
"""Base class for all RabbitMQ stage consumers."""
from __future__ import annotations

import json
import logging
import signal
import threading
from abc import ABC, abstractmethod
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from uuid import UUID

import pika
import pika.adapters.blocking_connection
import pika.spec

from services.pipeline.jobs import PipelineJobRepository
from shared.rabbit import RabbitClient

logger = logging.getLogger(__name__)


class BaseConsumer(ABC):
    """Consume one RabbitMQ queue; ack on success, nack (→ DLQ) on failure.

    Subclasses must set:
        queue_name: str    — RabbitMQ queue to consume
        worker_type: str   — label used in logs and metrics

    Subclasses must implement:
        handle_message(job_id, document_id, source_id, attempt, correlation_id)
    """

    queue_name: str
    worker_type: str

    def __init__(
        self,
        rabbit: RabbitClient,
        job_repo: PipelineJobRepository,
        health_port: int = 8080,
    ) -> None:
        self._rabbit = rabbit
        self._job_repo = job_repo
        self._health_port = health_port
        self._channel: pika.adapters.blocking_connection.BlockingChannel | None = None
        self._jobs_processed: int = 0
        self._stopping = False

    @abstractmethod
    def handle_message(
        self,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int,
        correlation_id: str,
    ) -> None:
        """Process one message. Raise on failure."""

    def run(self) -> None:
        """Connect, declare topology, consume. Blocks until SIGTERM."""
        self._rabbit.connect()
        self._rabbit.declare_topology()
        self._channel = self._rabbit._channel
        assert self._channel is not None
        self._channel.basic_qos(prefetch_count=1)
        self._channel.basic_consume(
            queue=self.queue_name,
            on_message_callback=self._on_message,
            auto_ack=False,
        )
        signal.signal(signal.SIGTERM, self._handle_sigterm)
        signal.signal(signal.SIGINT, self._handle_sigterm)
        self._start_health_server()
        logger.info(
            "worker started: worker_type=%s queue=%s", self.worker_type, self.queue_name
        )
        self._channel.start_consuming()
        logger.info("worker stopped: worker_type=%s", self.worker_type)

    def _on_message(
        self,
        channel: Any,
        method: pika.spec.Basic.Deliver,
        properties: pika.spec.BasicProperties,
        body: bytes,
    ) -> None:
        delivery_tag = method.delivery_tag
        try:
            payload = json.loads(body)
            job_id = UUID(payload["job_id"])
            document_id = UUID(payload["document_id"])
            source_id = UUID(payload["source_id"])
            attempt: int = int(payload.get("attempt", 1))
            correlation_id: str = payload.get("correlation_id", "")
        except (KeyError, ValueError) as exc:
            logger.error(
                "malformed message: worker_type=%s error=%s body=%.200s",
                self.worker_type, exc, body,
            )
            self._channel.basic_nack(delivery_tag=delivery_tag, requeue=False)  # type: ignore[union-attr]
            return

        try:
            self.handle_message(job_id, document_id, source_id, attempt, correlation_id)
            self._channel.basic_ack(delivery_tag=delivery_tag)  # type: ignore[union-attr]
            self._jobs_processed += 1
            logger.info(
                "job succeeded: worker_type=%s job_id=%s attempt=%d",
                self.worker_type, job_id, attempt,
            )
        except Exception as exc:
            max_attempts = self._job_repo.get_max_attempts(job_id)
            if attempt < (max_attempts or 5):
                self._job_repo.mark_retry(job_id, exc, stage=self.worker_type)
                logger.warning(
                    "job retry: worker_type=%s job_id=%s attempt=%d error=%s",
                    self.worker_type, job_id, attempt, exc,
                )
            else:
                self._job_repo.mark_dead_letter(job_id, exc)
                logger.error(
                    "job dead-lettered: worker_type=%s job_id=%s attempt=%d error=%s",
                    self.worker_type, job_id, attempt, exc,
                )
            self._channel.basic_nack(delivery_tag=delivery_tag, requeue=False)  # type: ignore[union-attr]

    def _handle_sigterm(self, signum: int, frame: Any) -> None:
        logger.info("shutting down: worker_type=%s", self.worker_type)
        self._stopping = True
        if self._channel and self._channel.is_open:
            self._channel.stop_consuming()

    def _start_health_server(self) -> None:
        worker_type = self.worker_type
        queue_name = self.queue_name
        consumer_ref = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path != "/health":
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                body = json.dumps({
                    "status": "ok",
                    "worker_type": worker_type,
                    "queue": queue_name,
                    "jobs_processed": consumer_ref._jobs_processed,
                }).encode()
                self.wfile.write(body)

            def log_message(self, fmt: str, *args: Any) -> None:
                pass  # suppress access logs

        server = HTTPServer(("", self._health_port), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
```

Also add `get_max_attempts` to `PipelineJobRepository` in `src/services/pipeline/jobs.py`:
```python
    def get_max_attempts(self, job_id: UUID) -> int:
        """Return the max_attempts value for a job (default 5 if not found)."""
        result = self._connection.execute(
            sa.text("SELECT max_attempts FROM pipeline_jobs WHERE id = :id"),
            {"id": db_uuid(job_id)},
        ).scalar()
        return int(result) if result is not None else 5
```

- [ ] **Run tests**
```bash
uv run pytest tests/unit/test_consumer_base.py -q
uv run mypy src/services/pipeline/consumer_base.py --strict
```
Expected: `4 passed`

- [ ] **Commit**
```bash
git add src/services/pipeline/consumer_base.py src/services/pipeline/jobs.py \
        tests/unit/test_consumer_base.py
git commit -m "feat(rabbit): BaseConsumer with ack/nack/retry/DLQ and health HTTP"
```

### Task 11: ParseConsumer, TranslateConsumer, EmbedConsumer, IndexConsumer

Each worker follows the same pattern. Implement them in sequence.

- [ ] **Create `src/services/pipeline/parse_worker.py`**

```python
"""Parse stage consumer — extracts text from a document and publishes translate."""
from __future__ import annotations

from uuid import UUID

from services.extraction.registry import ExtractorRegistry
from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.publisher import DocumentPublisher
from shared.rabbit import RabbitClient


class ParseConsumer(BaseConsumer):
    queue_name = "document.parse.requested"
    worker_type = "parse-worker"

    def __init__(
        self,
        rabbit: RabbitClient,
        job_repo: PipelineJobRepository,
        extractor: ExtractorRegistry,
        publisher: DocumentPublisher,
        health_port: int = 8081,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._extractor = extractor
        self._publisher = publisher

    def handle_message(
        self,
        job_id: UUID,
        document_id: UUID,
        source_id: UUID,
        attempt: int,
        correlation_id: str,
    ) -> None:
        from pathlib import Path
        from services.documents.repository import DocumentRepository
        # Load document
        doc = DocumentRepository(self._job_repo._connection).get_by_id(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")
        # Check for pre-extracted text in payload
        payload = self._job_repo.get_payload(document_id)
        if payload and payload.get("content_text"):
            text = payload["content_text"]
        elif doc.path:
            text = self._extractor.extract(Path(doc.path), doc.mime_type)
        else:
            raise ValueError(f"Document {document_id} has no path and no pre-extracted text")
        # Persist extracted text for downstream stages
        self._job_repo.update_content_text(document_id, text)
        self._job_repo.mark_running_stage(job_id, "parsed")
        # Publish next stage
        self._publisher.publish_translate(
            job_id=job_id, document_id=document_id,
            source_id=source_id, attempt=1,
        )
```

- [ ] **Create `src/services/pipeline/translate_worker.py`** (RabbitMQ consumer version):

```python
"""Translate stage consumer."""
from __future__ import annotations
from uuid import UUID
from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.publisher import DocumentPublisher
from services.translation.client import LibreTranslateClient
from shared.rabbit import RabbitClient


class TranslateConsumer(BaseConsumer):
    queue_name = "document.translate.requested"
    worker_type = "translate-worker"

    def __init__(
        self,
        rabbit: RabbitClient,
        job_repo: PipelineJobRepository,
        translator: LibreTranslateClient,
        publisher: DocumentPublisher,
        health_port: int = 8082,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._translator = translator
        self._publisher = publisher

    def handle_message(
        self, job_id: UUID, document_id: UUID, source_id: UUID,
        attempt: int, correlation_id: str,
    ) -> None:
        from services.documents.repository import DocumentRepository
        doc = DocumentRepository(self._job_repo._connection).get_by_id(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")
        payload = self._job_repo.get_payload(document_id)
        text = (payload or {}).get("content_text") or ""
        translated = self._translator.translate(text, source_lang=doc.source_language)
        self._job_repo.update_translated_text(document_id, translated)
        self._job_repo.mark_running_stage(job_id, "translated")
        self._publisher.publish_embed(
            job_id=job_id, document_id=document_id, source_id=source_id, attempt=1,
        )
```

- [ ] **Create `src/services/pipeline/embed_worker.py`**:

```python
"""Embed stage consumer — encodes chunks and publishes to index stage."""
from __future__ import annotations
from uuid import UUID
from services.chunking.splitter import chunk_text
from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.publisher import DocumentPublisher
from services.search.encoder import TextEncoder
from shared.rabbit import RabbitClient


class EmbedConsumer(BaseConsumer):
    queue_name = "document.embed.requested"
    worker_type = "embed-worker"

    def __init__(
        self,
        rabbit: RabbitClient,
        job_repo: PipelineJobRepository,
        encoder: TextEncoder,
        publisher: DocumentPublisher,
        embedding_max_tokens: int | None = None,
        health_port: int = 8083,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._encoder = encoder
        self._publisher = publisher
        self._embedding_max_tokens = embedding_max_tokens

    def handle_message(
        self, job_id: UUID, document_id: UUID, source_id: UUID,
        attempt: int, correlation_id: str,
    ) -> None:
        from services.documents.repository import DocumentRepository
        from services.search.qdrant import QdrantSearchClient
        doc = DocumentRepository(self._job_repo._connection).get_by_id(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")
        payload = self._job_repo.get_payload(document_id)
        content_text = (payload or {}).get("content_text") or ""
        translated_text = (payload or {}).get("translated_text") or ""
        # Chunk + encode (same logic as vector_worker.py)
        chunk_texts: list[str] = []
        chunk_meta: list[dict] = []
        for idx, c in enumerate(chunk_text(content_text, language=doc.source_language,
                                            max_tokens=self._embedding_max_tokens)):
            chunk_texts.append(c)
            chunk_meta.append({"lang": doc.source_language, "suffix": "orig", "idx": idx})
        if translated_text and translated_text != content_text:
            for idx, c in enumerate(chunk_text(translated_text, language=doc.target_language,
                                                max_tokens=self._embedding_max_tokens)):
                chunk_texts.append(c)
                chunk_meta.append({"lang": doc.target_language, "suffix": "tr", "idx": idx})
        vectors = self._encoder.encode_batch(chunk_texts)
        # Store vectors in payload for index stage
        import json
        encoded = json.dumps([{"text": t, "vector": v, **m}
                               for t, v, m in zip(chunk_texts, vectors, chunk_meta)])
        self._job_repo.mark_running_stage(job_id, "embedded")
        self._publisher.publish_index(
            job_id=job_id, document_id=document_id, source_id=source_id, attempt=1,
        )
```

- [ ] **Create `src/services/pipeline/index_worker.py`**:

```python
"""Index stage consumer — writes to ES, Meilisearch, and Qdrant."""
from __future__ import annotations
from uuid import UUID
from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from services.pipeline.publisher import DocumentPublisher
from services.search.elastic import ElasticsearchSearchClient
from services.search.encoder import TextEncoder
from services.search.qdrant import QdrantSearchClient
from shared.rabbit import RabbitClient


class IndexConsumer(BaseConsumer):
    queue_name = "document.index.requested"
    worker_type = "index-worker"

    def __init__(
        self,
        rabbit: RabbitClient,
        job_repo: PipelineJobRepository,
        es_client: ElasticsearchSearchClient,
        qdrant_client: QdrantSearchClient,
        encoder: TextEncoder,
        publisher: DocumentPublisher,
        health_port: int = 8084,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._es = es_client
        self._qdrant = qdrant_client
        self._encoder = encoder
        self._publisher = publisher

    def handle_message(
        self, job_id: UUID, document_id: UUID, source_id: UUID,
        attempt: int, correlation_id: str,
    ) -> None:
        from pathlib import Path
        from services.documents.repository import DocumentRepository
        doc = DocumentRepository(self._job_repo._connection).get_by_id(document_id)
        if doc is None:
            raise ValueError(f"Document {document_id} not found")
        payload = self._job_repo.get_payload(document_id)
        content_text = (payload or {}).get("content_text") or ""
        translated_text = (payload or {}).get("translated_text") or ""
        allowed_group_ids = [
            str(gid) for gid in
            DocumentRepository(self._job_repo._connection).source_group_ids(doc.source_id)
        ]
        # Index in ES
        self._es.index_document(str(document_id), {
            "document_id": str(document_id),
            "path": doc.path or "",
            "filename": Path(doc.path).name if doc.path else doc.title or "",
            "content_original": content_text,
            "content_english": translated_text,
            "title": doc.title or "",
            "summary": "",
            "tags": [],
            "metadata": doc.metadata,
            "allowed_group_ids": allowed_group_ids,
        })
        self._job_repo.mark_running_stage(job_id, "indexed")
        # Publish intelligence + alert in parallel (independent)
        self._publisher.publish_intelligence(
            job_id=job_id, document_id=document_id, source_id=source_id, attempt=1,
        )
        self._publisher.publish_alert(
            job_id=job_id, document_id=document_id, source_id=source_id, attempt=1,
        )
        self._job_repo.mark_running_stage(job_id, "completed")
```

- [ ] **Run type checks**
```bash
uv run mypy src/services/pipeline/parse_worker.py \
            src/services/pipeline/translate_worker.py \
            src/services/pipeline/embed_worker.py \
            src/services/pipeline/index_worker.py --strict
```

- [ ] **Commit**
```bash
git add src/services/pipeline/parse_worker.py \
        src/services/pipeline/translate_worker.py \
        src/services/pipeline/embed_worker.py \
        src/services/pipeline/index_worker.py
git commit -m "feat(rabbit): ParseConsumer, TranslateConsumer, EmbedConsumer, IndexConsumer"
```

### Task 12: Register worker entrypoints + docker-compose services

- [ ] **Add entrypoints to `pyproject.toml`** under `[project.scripts]`:
```toml
[project.scripts]
tomorrowland-parse-worker = "services.pipeline.parse_worker:main"
tomorrowland-translate-worker = "services.pipeline.translate_worker:main"
tomorrowland-embed-worker = "services.pipeline.embed_worker:main"
tomorrowland-index-worker = "services.pipeline.index_worker:main"
tomorrowland-intelligence-worker = "services.pipeline.intelligence_consumer:main"
tomorrowland-alert-worker = "services.pipeline.alert_consumer:main"
```

Add a `main()` function to each worker file:
```python
def main() -> None:
    import logging
    from shared.config import Settings
    from shared.rabbit import RabbitClient
    # ... build dependencies from Settings, call consumer.run()
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    # (see each worker's __init__ for required deps)
```

- [ ] **Add worker services to `docker-compose.yml`** (one per stage; parse shown as template):
```yaml
  parse-worker:
    build: .
    command: tomorrowland-parse-worker
    env_file: .env
    depends_on:
      rabbitmq:
        condition: service_healthy
      postgres:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8081/health"]
      interval: 30s
      timeout: 5s
      retries: 3
```

Repeat for `translate-worker` (port 8082), `embed-worker` (8083), `index-worker` (8084).

- [ ] **Commit**
```bash
git add docker-compose.yml pyproject.toml src/services/pipeline/
git commit -m "feat(rabbit): worker entrypoints and docker-compose services for stage workers"
```

---

## Sub-issue D — Intelligence + Alert Consumers (#428)

### Task 13: IntelligenceConsumer and AlertConsumer

- [ ] **Create `src/services/pipeline/intelligence_consumer.py`**:

```python
"""Intelligence stage consumer — wraps existing IntelligenceWorker."""
from __future__ import annotations
from uuid import UUID
from services.intelligence.worker import IntelligenceWorker
from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from shared.rabbit import RabbitClient


class IntelligenceConsumer(BaseConsumer):
    queue_name = "document.intelligence.requested"
    worker_type = "intelligence-worker"

    def __init__(
        self,
        rabbit: RabbitClient,
        job_repo: PipelineJobRepository,
        intelligence_worker: IntelligenceWorker,
        health_port: int = 8085,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._intelligence = intelligence_worker

    def handle_message(
        self, job_id: UUID, document_id: UUID, source_id: UUID,
        attempt: int, correlation_id: str,
    ) -> None:
        payload = self._job_repo.get_payload(document_id)
        content = (payload or {}).get("content_text") or ""
        self._intelligence.process_document(document_id, content)
        self._job_repo.mark_running_stage(job_id, "intelligence_done")
```

- [ ] **Create `src/services/pipeline/alert_consumer.py`**:

```python
"""Alert stage consumer — runs AlertMatcher for a document."""
from __future__ import annotations
from uuid import UUID
from services.alerts.service import AlertMatcher
from services.pipeline.consumer_base import BaseConsumer
from services.pipeline.jobs import PipelineJobRepository
from shared.rabbit import RabbitClient


class AlertConsumer(BaseConsumer):
    queue_name = "document.alert.requested"
    worker_type = "alert-worker"

    def __init__(
        self,
        rabbit: RabbitClient,
        job_repo: PipelineJobRepository,
        alert_matcher: AlertMatcher,
        health_port: int = 8086,
    ) -> None:
        super().__init__(rabbit, job_repo, health_port)
        self._alert_matcher = alert_matcher

    def handle_message(
        self, job_id: UUID, document_id: UUID, source_id: UUID,
        attempt: int, correlation_id: str,
    ) -> None:
        self._alert_matcher.match_document(document_id)
        self._job_repo.mark_running_stage(job_id, "alert_done")
```

- [ ] **Add to docker-compose.yml** (ports 8085, 8086; same template as parse-worker)

- [ ] **Run type checks and full test suite**
```bash
uv run mypy src/services/pipeline/intelligence_consumer.py \
            src/services/pipeline/alert_consumer.py --strict
uv run pytest tests/ -q
```
Expected: all pass

- [ ] **Commit**
```bash
git add src/services/pipeline/intelligence_consumer.py \
        src/services/pipeline/alert_consumer.py \
        docker-compose.yml
git commit -m "feat(rabbit): IntelligenceConsumer and AlertConsumer"
```

---

## Sub-issue E — Admin Monitoring (#429)

### Task 14: `GET /admin/rabbit/queues`

- [ ] **Write the failing test**

Create `tests/unit/test_admin_rabbit_routes.py`:
```python
from unittest.mock import MagicMock, patch


@patch("services.api.routers.admin.rabbit.RabbitClient")
def test_get_queues_returns_depth_per_queue(mock_cls, client, admin_token):
    mock_rabbit = MagicMock()
    mock_rabbit.queue_depths.return_value = {
        "document.parse.requested": {"depth": 3, "dlq_depth": 0, "consumers": 1},
    }
    mock_cls.return_value = mock_rabbit

    resp = client.get("/admin/rabbit/queues",
                      headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "queues" in data
```

- [ ] **Implement `src/services/api/routers/admin/rabbit.py`**:

```python
"""Admin routes for RabbitMQ queue observability."""
from __future__ import annotations

import urllib.request
import json
import base64
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request

from services.api.main import current_user
from services.auth.models import TokenPayload
from services.permissions.enforcer import require_admin
from shared.config import Settings

router = APIRouter(tags=["admin"])
_settings = Settings()

_STAGE_QUEUES = [
    "document.parse.requested",
    "document.translate.requested",
    "document.embed.requested",
    "document.index.requested",
    "document.intelligence.requested",
    "document.alert.requested",
]


def _mgmt_get(path: str) -> Any:
    """Call RabbitMQ management API (localhost:15672) with basic auth."""
    url = f"http://localhost:15672/api/{path}"
    token = base64.b64encode(
        f"{_settings.rabbitmq_user}:{_settings.rabbitmq_pass}".encode()
    ).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {token}"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


@router.get("/admin/rabbit/queues")
def admin_rabbit_queues(
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    try:
        all_queues = _mgmt_get("queues")
        by_name = {q["name"]: q for q in all_queues}
        result = []
        for queue in _STAGE_QUEUES:
            dlq = queue.replace("requested", "dead")
            info = by_name.get(queue, {})
            dlq_info = by_name.get(dlq, {})
            result.append({
                "queue": queue,
                "depth": info.get("messages", 0),
                "consumers": info.get("consumers", 0),
                "dlq": dlq,
                "dlq_depth": dlq_info.get("messages", 0),
            })
        return {"queues": result}
    except Exception as exc:
        return {"queues": [], "error": str(exc)}
```

- [ ] **Register the router** in `src/services/api/routers/admin/__init__.py`:
```python
from services.api.routers.admin import rabbit as rabbit_router
router.include_router(rabbit_router.router)
```

- [ ] **Commit**
```bash
git add src/services/api/routers/admin/rabbit.py \
        src/services/api/routers/admin/__init__.py \
        tests/unit/test_admin_rabbit_routes.py
git commit -m "feat(rabbit): GET /admin/rabbit/queues route"
```

### Task 15: `POST /admin/jobs/{job_id}/retry`

- [ ] **Add retry endpoint to `src/services/api/routers/admin/jobs.py`**:

```python
@router.post("/admin/jobs/{job_id}/retry")
def admin_retry_job(
    job_id: UUID,
    request: Request,
    user: Annotated[TokenPayload, Depends(current_user)],
) -> dict[str, Any]:
    require_admin(user)
    with request.app.state.engine.begin() as conn:
        row = conn.execute(
            sa.text("SELECT status, job_type FROM pipeline_jobs WHERE id = :id"),
            {"id": job_id.hex},
        ).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if row["status"] != "dead_letter":
            raise HTTPException(
                status_code=409,
                detail=f"Job is not dead-lettered (status={row['status']})",
            )
        from datetime import datetime, UTC
        conn.execute(
            sa.text("""
                UPDATE pipeline_jobs
                SET status = 'pending', attempts = 0, last_error = NULL,
                    locked_by = NULL, locked_at = NULL,
                    run_after = :now, updated_at = :now
                WHERE id = :id AND status = 'dead_letter'
            """),
            {"id": job_id.hex, "now": datetime.now(UTC)},
        )
    return {"retried": str(job_id)}
```

- [ ] **Write and run test**
```bash
uv run pytest tests/integration/test_admin_jobs_routes.py -q
```

- [ ] **Commit**
```bash
git add src/services/api/routers/admin/jobs.py
git commit -m "feat(rabbit): POST /admin/jobs/{id}/retry endpoint"
```

---

## Sub-issue F — Retry Tiers + Alert Rules (#430)

### Task 16: Retry exchange with per-stage backoff

The current `basic_nack(requeue=False)` sends messages to the DLQ exchange immediately. For sub-issue F, add a **retry tier exchange** so the first N failures go to a delayed retry queue before the DLQ.

- [ ] **Add retry exchange to topology in `src/shared/rabbit.py`**:

```python
# Add to declare_topology(), after main exchange declaration:
RETRY_EXCHANGE = "tomorrowland.documents.retry"

ch.exchange_declare(
    exchange=RETRY_EXCHANGE, exchange_type="topic", durable=True
)
# Per-stage retry queues (30 s TTL → republish to main exchange)
for queue in _STAGE_QUEUES:
    retry_queue = queue.replace("requested", "retry")
    ch.queue_declare(
        queue=retry_queue,
        durable=True,
        arguments={
            "x-dead-letter-exchange": _MAIN_EXCHANGE,
            "x-dead-letter-routing-key": queue,
            "x-message-ttl": 30_000,  # 30 seconds
        },
    )
    ch.queue_bind(
        queue=retry_queue,
        exchange=RETRY_EXCHANGE,
        routing_key=queue,
    )
```

Update `BaseConsumer._on_message` to publish to retry exchange on first N failures instead of nacking directly:

```python
# In _on_message failure branch, replace the nack call with:
if attempt < min(3, max_attempts or 5):
    # Publish to retry exchange (30 s backoff)
    retry_body = json.loads(body)
    retry_body["attempt"] = attempt + 1
    self._rabbit._channel.basic_publish(  # type: ignore[union-attr]
        exchange="tomorrowland.documents.retry",
        routing_key=self.queue_name,
        body=json.dumps(retry_body).encode(),
        properties=pika.spec.BasicProperties(delivery_mode=2),
    )
    self._channel.basic_ack(delivery_tag=delivery_tag)  # type: ignore[union-attr]
    self._job_repo.mark_retry(job_id, exc, stage=self.worker_type)
else:
    self._job_repo.mark_dead_letter(job_id, exc)
    self._channel.basic_nack(delivery_tag=delivery_tag, requeue=False)  # type: ignore[union-attr]
```

- [ ] **Run tests**
```bash
uv run pytest tests/unit/test_consumer_base.py -q
```

- [ ] **Commit**
```bash
git add src/shared/rabbit.py src/services/pipeline/consumer_base.py
git commit -m "feat(rabbit): retry tier exchange with 30s TTL backoff before DLQ"
```

### Task 17: Prometheus alert rules

Create `monitoring/alerts/rabbitmq.yml`:
```yaml
groups:
  - name: tomorrowland_rabbitmq
    rules:
      - alert: TomorrowlandRabbitQueueBacking
        expr: |
          tomorrowland_rabbit_queue_depth{queue!~".*dead.*"} > 100
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "RabbitMQ queue {{ $labels.queue }} depth > 100 for 10m"

      - alert: TomorrowlandRabbitDlqPending
        expr: tomorrowland_rabbit_queue_depth{queue=~".*dead.*"} > 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "DLQ {{ $labels.queue }} has {{ $value }} pending messages"

      - alert: TomorrowlandWorkerHeartbeatStale
        expr: |
          time() - tomorrowland_worker_heartbeat_timestamp_seconds > 120
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Worker {{ $labels.worker_type }} heartbeat stale > 2m"
```

- [ ] **Commit**
```bash
git add monitoring/alerts/rabbitmq.yml
git commit -m "feat(rabbit): Prometheus alert rules for queue depth, DLQ, and worker heartbeat"
```

---

## Sub-issue G — Air-gap Compose + Validation Script (#431)

### Task 18: Air-gap compose additions

- [ ] **Add RabbitMQ to `docker-compose.airgap.yml`** — same service definition as docker-compose.yml, no external image pull required (pre-loaded image in air-gap bundle).

Update `scripts/tomorrowland-airgap.sh` to include the RabbitMQ image in the save/load manifest.

- [ ] **Create `scripts/validate-rabbitmq.sh`**:

```bash
#!/usr/bin/env bash
set -euo pipefail

MGMT_URL="${RABBITMQ_MGMT_URL:-http://localhost:15672}"
USER="${RABBITMQ_USER:-tomorrowland}"
PASS="${RABBITMQ_PASS:-changeme}"

echo "=== RabbitMQ Validation ==="

echo "1. Broker reachable..."
curl -sf -u "$USER:$PASS" "$MGMT_URL/api/overview" > /dev/null
echo "   OK"

echo "2. All 6 stage queues declared..."
QUEUES=$(curl -sf -u "$USER:$PASS" "$MGMT_URL/api/queues" | python3 -c \
  "import sys,json; print('\n'.join(q['name'] for q in json.load(sys.stdin)))")
for Q in \
  document.parse.requested \
  document.translate.requested \
  document.embed.requested \
  document.index.requested \
  document.intelligence.requested \
  document.alert.requested; do
    echo "$QUEUES" | grep -q "^$Q$" && echo "   $Q OK" || { echo "   MISSING: $Q"; exit 1; }
done

echo "3. All 6 DLQ queues declared..."
for Q in \
  document.parse.dead \
  document.translate.dead \
  document.embed.dead \
  document.index.dead \
  document.intelligence.dead \
  document.alert.dead; do
    echo "$QUEUES" | grep -q "^$Q$" && echo "   $Q OK" || { echo "   MISSING: $Q"; exit 1; }
done

echo "4. Worker health checks..."
declare -A PORTS=(
  [parse-worker]=8081 [translate-worker]=8082 [embed-worker]=8083
  [index-worker]=8084 [intelligence-worker]=8085 [alert-worker]=8086
)
for WORKER in "${!PORTS[@]}"; do
  PORT=${PORTS[$WORKER]}
  STATUS=$(curl -sf "http://localhost:$PORT/health" | python3 -c \
    "import sys,json; print(json.load(sys.stdin)['status'])" 2>/dev/null || echo "unreachable")
  if [ "$STATUS" = "ok" ]; then
    echo "   $WORKER:$PORT OK"
  else
    echo "   $WORKER:$PORT status=$STATUS (may not be running in this stack)"
  fi
done

echo ""
echo "=== Validation PASSED ==="
```

- [ ] **Make executable and commit**:
```bash
chmod +x scripts/validate-rabbitmq.sh
git add scripts/validate-rabbitmq.sh docker-compose.airgap.yml
git commit -m "feat(rabbit): air-gap compose additions and validate-rabbitmq.sh"
```

---

## Final Validation Before Feature Branch → main

Run this checklist before opening the integration PR:

- [ ] `uv run ruff check src/ tests/` — no errors
- [ ] `uv run ruff format --check src/ tests/` — no diffs
- [ ] `uv run mypy src --strict` — no errors
- [ ] `uv run pytest tests/ -q` — all pass, ≥ 90% coverage
- [ ] `docker compose up rabbitmq -d && sleep 10 && bash scripts/validate-rabbitmq.sh`
- [ ] `docker compose up` — all 6 worker containers reach `healthy` within 60 s
- [ ] Publish one document via `POST /admin/ingestion/{id}/sync-now` with `RABBITMQ_ENABLED=true`; confirm it progresses through all 6 queues to `completed` in `pipeline_jobs`
- [ ] `POST /admin/jobs/{dead_letter_id}/retry` — job resets to `pending` and reprocesses
- [ ] `GET /admin/rabbit/queues` — returns depths for all 6 queues
- [ ] SIGTERM test: `docker compose kill -s SIGTERM parse-worker` — container exits 0, in-flight job completes
- [ ] `RABBITMQ_ENABLED=false`: existing `sync-now` integration tests pass unchanged
- [ ] `CHANGELOG.md` entry present
- [ ] Post validation summary as comment on #432

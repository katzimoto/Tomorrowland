from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from shared.events import (
    DocumentEvent,
    DocumentOperation,
    DocumentSource,
    IntelligenceEvent,
)


def test_document_event_accepts_nifi_normalized_raw_event() -> None:
    event = DocumentEvent(
        document_id=uuid4(),
        source_id=uuid4(),
        source=DocumentSource.NIFI,
        external_id="nifi:flow-file:123",
        path=None,
        mime_type="application/pdf",
        source_language=None,
        operation=DocumentOperation.CREATE,
        timestamp=datetime.now(UTC),
        correlation_id=uuid4(),
    )

    assert event.source == "nifi"
    assert event.operation == "create"


def test_document_event_rejects_invalid_operation() -> None:
    with pytest.raises(ValidationError):
        DocumentEvent(
            document_id=uuid4(),
            source_id=uuid4(),
            source="folder",
            external_id="file:/data/a.txt",
            mime_type="text/plain",
            operation="replace",
            timestamp=datetime.now(UTC),
            correlation_id=uuid4(),
        )


def test_intelligence_event_uses_allowed_groups_not_single_group() -> None:
    group_id = uuid4()
    event = IntelligenceEvent(
        document_id=uuid4(),
        content_english="hello",
        allowed_group_ids=[group_id],
        correlation_id=uuid4(),
        tasks=["summarize", "auto_tag"],
    )

    assert event.allowed_group_ids == [group_id]
    assert event.tasks == ["summarize", "auto_tag"]

"""Optional OpenTelemetry tracing hooks.

All functions are no-ops when OpenTelemetry is not installed or when no tracer
provider / exporter has been configured.  No remote collector is started or
required by default.

Intended instrumentation sites
-------------------------------
- HTTP request handling  (route template as span name)
- Database transactions
- Elasticsearch / Qdrant search calls
- LibreTranslate translation calls
- Ollama inference calls
- Pipeline stages: extract, translate, chunk, embed, index, intelligence

Usage::

    from shared.tracing import start_span

    with start_span("pipeline.embed", document_id=str(doc_id)):
        ...  # work here

    with start_span("search.qdrant.query", index="documents"):
        ...
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


@contextmanager
def start_span(name: str, **attributes: Any) -> Iterator[None]:
    """Start an OpenTelemetry span if a provider is installed; otherwise no-op.

    Parameters
    ----------
    name:
        Span name.  Use dot-separated namespacing, e.g. ``"pipeline.embed"``.
        Must be a static string — do not include IDs or user data.
    **attributes:
        Key/value span attributes.  Values are coerced to ``str``; keep them
        low-cardinality (document IDs are fine, raw queries or file content
        are not).
    """
    try:
        from opentelemetry import trace as otel_trace  # type: ignore[import-not-found]
    except ImportError:
        # OpenTelemetry not installed — complete no-op.
        yield
        return

    # OpenTelemetry is available — create a real span.
    tracer = otel_trace.get_tracer(__name__)  # pragma: no cover
    with tracer.start_as_current_span(name) as span:  # pragma: no cover
        for key, value in attributes.items():  # pragma: no cover
            span.set_attribute(key, str(value))  # pragma: no cover
        yield  # pragma: no cover

"""Prometheus metrics for the MCP adapter.

Exposes a standalone ``CollectorRegistry`` with MCP-specific counters and
histograms so operators can monitor MCP tool usage, latency, errors, and
circuit breaker state in Grafana alongside the rest of the Tomorrowland
stack.

Usage::

    from services.mcp.metrics import MCPMetrics

    metrics = MCPMetrics()
    metrics.tool_calls_total.labels(tool="search_documents", outcome="ok").inc()
    metrics.tool_call_duration_seconds.labels(tool="search_documents").observe(0.123)
    metrics.circuit_breaker_state.set(0)  # 0=closed, 1=open, 2=half_open
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
)
from prometheus_client import generate_latest as _generate_latest

MCP_LATENCY_BUCKETS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
)


class MCPMetrics:
    """Prometheus collectors scoped to the MCP adapter."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry(auto_describe=True)

        self.tool_calls_total = Counter(
            "tomorrowland_mcp_tool_calls_total",
            "Total MCP tool invocations by tool name and outcome.",
            ("tool", "outcome"),
            registry=self.registry,
        )
        self.tool_call_duration_seconds = Histogram(
            "tomorrowland_mcp_tool_call_duration_seconds",
            "MCP tool call duration in seconds by tool name.",
            ("tool",),
            buckets=MCP_LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.tool_call_errors_total = Counter(
            "tomorrowland_mcp_tool_call_errors_total",
            "MCP tool call errors by tool name and error type.",
            ("tool", "error_type"),
            registry=self.registry,
        )
        self.circuit_breaker_state = Gauge(
            "tomorrowland_mcp_circuit_breaker_state",
            "Circuit breaker state: 0=closed, 1=open, 2=half_open.",
            registry=self.registry,
        )
        self.circuit_breaker_failures_total = Counter(
            "tomorrowland_mcp_circuit_breaker_failures_total",
            "Total number of server-side failures counted by the circuit breaker.",
            registry=self.registry,
        )


async def metrics_endpoint(request) -> tuple[bytes, int, dict[str, str]]:  # type: ignore[no-untyped-def]  # noqa: ARG001
    """ASGI endpoint that serves Prometheus text format for the MCP registry."""
    body = _generate_latest(_mcp_metrics.registry)
    return body, 200, {"Content-Type": CONTENT_TYPE_LATEST}


# Module-level singleton so the /metrics endpoint and tool wrappers
# share the same registry inside one process.
_mcp_metrics = MCPMetrics()

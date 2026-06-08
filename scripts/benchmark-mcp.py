#!/usr/bin/env python3
"""Benchmark the async MCP client against a mock backend.

Measures throughput (calls/sec) and latency (p50/p95/p99) for each of the
six MCP tools at varying concurrency levels.

Usage::

    uv run python scripts/benchmark-mcp.py [--concurrency 1,5,10,20] [--iterations 100]

Outputs a CSV table suitable for import into spreadsheet tools.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Hack sys.path so we can import the MCP client from the project root.
# ---------------------------------------------------------------------------
sys.path.insert(0, "tomorrowland")


def _build_mock_app() -> httpx.AsyncClient:
    """Create a lightweight mock backend that responds to all agent endpoints."""

    async def _handler(request: httpx.Request) -> httpx.Response:
        # Simulate a small processing delay (0–5 ms) to mimic real backend variance.
        await asyncio.sleep(0.002 + (hash(request.url.path) % 10) * 0.0005)

        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})

        path = request.url.path

        if "/search_documents" in path:
            body = {"results": [], "total": 0, "query": "bench"}
        elif "/get_document" in path:
            body = {"document_id": "abc", "title": "Bench Doc", "mime_type": "text/plain"}
        elif "/get_passages" in path:
            body = {"document_id": "abc", "passages": [], "total": 0}
        elif "/ask_corpus" in path:
            body = {"question": "q", "answer": "bench answer", "citations": [], "model": "mock"}
        elif "/get_related_documents" in path:
            body = {"document_id": "abc", "related": []}
        elif "/list_facets" in path:
            body = {"facets": {"source": {"folder": 1}}}
        else:
            return httpx.Response(404, json={"detail": "not found"})

        return httpx.Response(200, json=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(_handler))


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


async def _benchmark_tool(
    client: Any,
    tool_name: str,
    iterations: int,
    concurrency: int,
) -> dict[str, Any]:
    """Run *iterations* calls to *tool_name* at *concurrency* level.

    Returns a dict with throughput, latency percentiles, and error count.
    """
    tool_map: dict[str, tuple[str, dict[str, Any]]] = {
        "search_documents": ("search_documents", {"query": "benchmark"}),
        "get_document": ("get_document", {"document_id": "abc-123"}),
        "get_passages": ("get_passages", {"document_id": "abc-123"}),
        "ask_corpus": ("ask_corpus", {"question": "benchmark question?"}),
        "get_related_documents": ("get_related_documents", {"document_id": "abc-123"}),
        "list_facets": ("list_facets", {"query": "bench"}),
    }

    method_name, kwargs = tool_map[tool_name]
    latencies: list[float] = []
    errors = 0
    semaphore = asyncio.Semaphore(concurrency)

    async def _call() -> None:
        nonlocal errors
        async with semaphore:
            t0 = time.perf_counter()
            try:
                method = getattr(client, method_name)
                await method(**kwargs)
            except Exception:
                errors += 1
                return
            latencies.append(time.perf_counter() - t0)

    t_start = time.perf_counter()
    tasks = [_call() for _ in range(iterations)]
    await asyncio.gather(*tasks)
    total_s = time.perf_counter() - t_start

    latencies.sort()
    n = len(latencies)
    if n == 0:
        return {
            "tool": tool_name,
            "concurrency": concurrency,
            "iterations": iterations,
            "throughput_calls_per_sec": 0,
            "latency_p50_ms": 0,
            "latency_p95_ms": 0,
            "latency_p99_ms": 0,
            "errors": errors,
        }

    def _pct(p: float) -> float:
        idx = max(0, min(n - 1, int(n * p / 100)))
        return latencies[idx] * 1000

    return {
        "tool": tool_name,
        "concurrency": concurrency,
        "iterations": n,
        "throughput_calls_per_sec": round(n / total_s, 1),
        "latency_p50_ms": round(_pct(50), 2),
        "latency_p95_ms": round(_pct(95), 2),
        "latency_p99_ms": round(_pct(99), 2),
        "errors": errors,
    }


async def run_benchmarks(
    concurrency_levels: list[int],
    iterations: int,
) -> list[dict[str, Any]]:
    """Run all benchmarks and return results."""
    from services.mcp.client import TomorrowlandClient

    mock_transport = _build_mock_app()

    async with mock_transport as transport:
        client = TomorrowlandClient(
            api_url="http://mock",
            api_key="bench-key",
            timeout=30.0,
        )
        # Override the internal client with our mock transport.
        client._client = transport

        # Warmup — establish connections (best-effort).
        await client.warmup()

        tools = [
            "search_documents",
            "get_document",
            "get_passages",
            "ask_corpus",
            "get_related_documents",
            "list_facets",
        ]

        results: list[dict[str, Any]] = []
        for concurrency in concurrency_levels:
            for tool in tools:
                result = await _benchmark_tool(client, tool, iterations, concurrency)
                results.append(result)

        return results


def _print_table(results: list[dict[str, Any]]) -> None:
    """Print results as a formatted table."""
    header = (
        f"{'Tool':<28} {'Conc':>4} {'N':>6} "
        f"{'req/s':>8} {'p50(ms)':>8} {'p95(ms)':>8} {'p99(ms)':>8} {'errs':>5}"
    )
    sep = "-" * len(header)
    print(sep)
    print(header)
    print(sep)
    for r in results:
        print(
            f"{r['tool']:<28} {r['concurrency']:>4} {r['iterations']:>6} "
            f"{r['throughput_calls_per_sec']:>8.1f} {r['latency_p50_ms']:>8.2f} "
            f"{r['latency_p95_ms']:>8.2f} {r['latency_p99_ms']:>8.2f} "
            f"{r['errors']:>5}"
        )
    print(sep)
    print(
        f"\nTotal: {sum(r['iterations'] for r in results)} calls across {len(results)} benchmarks."
    )


def _print_csv(results: list[dict[str, Any]]) -> None:
    """Print results as CSV."""
    keys = [
        "tool",
        "concurrency",
        "iterations",
        "throughput_calls_per_sec",
        "latency_p50_ms",
        "latency_p95_ms",
        "latency_p99_ms",
        "errors",
    ]
    print(",".join(keys))
    for r in results:
        print(",".join(str(r[k]) for k in keys))


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark the async MCP client")
    parser.add_argument(
        "--concurrency",
        type=str,
        default="1,5,10,20",
        help="Comma-separated concurrency levels (default: 1,5,10,20)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="Number of calls per tool per concurrency level (default: 100)",
    )
    parser.add_argument(
        "--csv",
        action="store_true",
        help="Output CSV instead of formatted table",
    )
    args = parser.parse_args()

    concurrency_levels = [int(c.strip()) for c in args.concurrency.split(",")]

    print(
        f"Benchmarking async MCP client "
        f"(iterations={args.iterations}, concurrency={args.concurrency})"
    )
    print()

    results = asyncio.run(run_benchmarks(concurrency_levels, args.iterations))

    if args.csv:
        _print_csv(results)
    else:
        _print_table(results)

    # Exit non-zero if any errors occurred.
    total_errors = sum(r["errors"] for r in results)
    if total_errors > 0:
        print(f"\n⚠️  {total_errors} errors occurred during benchmarking.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Kanban metrics exporter for Prometheus.

Queries the Hermes Kanban board (stats + diagnostics) and emits Prometheus
text-format metrics on stdout.  Designed for one-shot execution — wire it into
cron + node_exporter textfile collector or run it as a shell-wrapper check.

Usage:
    uv run python scripts/kanban-metrics.py              # print to stdout
    uv run python scripts/kanban-metrics.py --output FILE # atomic write to FILE

Exported metrics:
    tomorrowland_tasks_total{status="..."}   gauge, per-status counts
    tomorrowland_tasks_blocked               gauge, convenience (same as blocked label)
    tomorrowland_diagnostics_active          gauge, count of active diagnostics
    tomorrowland_oldest_ready_age_seconds    gauge, age of oldest ready task

Integration with node_exporter textfile collector
-------------------------------------------------
1. Ensure the node_exporter textfile collector is enabled (--collector.textfile.directory).
2. Create the collector directory (default /var/lib/node_exporter/textfile_collector).
3. Schedule this script via cron every 60 seconds:

   * * * * * cd /opt/Tomorrowland && uv run python scripts/kanban-metrics.py \
             --output /var/lib/node_exporter/textfile_collector/kanban-metrics.prom

   The --output flag does an atomic rename (write to temp, then rename) so that
   node_exporter never reads a half-written file.

Integration without node_exporter
----------------------------------
If you are running Prometheus directly, add a scrape job:

    scrape_configs:
      - job_name: tomorrowland-kanban
        metrics_path: /metrics
        static_configs:
          - targets: ['host:PORT']
        # ... or use a file_sd / cron wrapper that writes the metrics to a
        # location served by a minimal HTTP server.

Requirements
------------
- hermes CLI accessible in PATH
- HERMES_KANBAN_DB or HERMES_KANBAN_BOARD env vars set (or a 'current' symlink)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ALL_STATUSES: list[str] = [
    "triage",
    "todo",
    "scheduled",
    "ready",
    "running",
    "blocked",
    "done",
]

_TIMEOUT_S = 30


def _run_hermes(args: list[str]) -> dict | list:
    """Run ``hermes kanban <args>``, return parsed JSON.  Exit on failure."""
    cmd = ["hermes", "kanban", *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_S,
        )
    except FileNotFoundError:
        print(f"ERROR: hermes CLI not found in PATH — cannot run {' '.join(cmd)}", file=sys.stderr)
        sys.exit(2)
    except subprocess.TimeoutExpired:
        print(f"ERROR: {' '.join(cmd)} timed out after {_TIMEOUT_S}s", file=sys.stderr)
        sys.exit(3)

    if result.returncode != 0:
        print(
            f"ERROR: {' '.join(cmd)} exited {result.returncode}\n{result.stderr}",
            file=sys.stderr,
        )
        sys.exit(4)

    return json.loads(result.stdout)


def _format_metrics(
    stats: dict,
    diagnostics_count: int,
) -> str:
    """Render Prometheus text-format metrics."""
    lines: list[str] = []
    by_status: dict[str, int] = stats.get("by_status", {})

    # -- tomorrowland_tasks_total (per-status gauge) --
    lines.append("# HELP tomorrowland_tasks_total Number of Kanban tasks by status.")
    lines.append("# TYPE tomorrowland_tasks_total gauge")
    for status in ALL_STATUSES:
        count = by_status.get(status, 0)
        lines.append(f'tomorrowland_tasks_total{{status="{status}"}} {count}')

    # -- tomorrowland_tasks_blocked (no-label convenience gauge) --
    lines.append("# HELP tomorrowland_tasks_blocked Number of blocked Kanban tasks.")
    lines.append("# TYPE tomorrowland_tasks_blocked gauge")
    lines.append(f"tomorrowland_tasks_blocked {by_status.get('blocked', 0)}")

    # -- tomorrowland_diagnostics_active --
    lines.append("# HELP tomorrowland_diagnostics_active Number of active Kanban diagnostics.")
    lines.append("# TYPE tomorrowland_diagnostics_active gauge")
    lines.append(f"tomorrowland_diagnostics_active {diagnostics_count}")

    # -- tomorrowland_oldest_ready_age_seconds --
    lines.append(
        "# HELP tomorrowland_oldest_ready_age_seconds "
        "Age in seconds of the oldest Kanban task in 'ready' status."
    )
    lines.append("# TYPE tomorrowland_oldest_ready_age_seconds gauge")
    oldest: int | None = stats.get("oldest_ready_age_seconds")
    lines.append(f"tomorrowland_oldest_ready_age_seconds {oldest if oldest is not None else 0}")

    # -- scrape metadata line (not strictly required but helpful for debugging) --
    scrape_time = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    lines.append(f"# HELP tomorrowland_metrics_scrape_seconds Timestamp of last scrape.")
    lines.append("# TYPE tomorrowland_metrics_scrape_seconds gauge")
    lines.append(
        f"tomorrowland_metrics_scrape_seconds {stats.get('now', 0)}"
    )

    return "\n".join(lines) + "\n"


def _atomic_write(path: str, content: str) -> None:
    """Write *content* to *path* atomically (temp-file + rename)."""
    dirname = os.path.dirname(os.path.abspath(path))
    fd, tmpname = tempfile.mkstemp(dir=dirname, suffix=".prom")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.rename(tmpname, path)
    except Exception:
        # Best-effort cleanup; if rename failed the temp file should not be
        # left behind as a false positive.
        try:
            os.unlink(tmpname)
        except OSError:
            pass
        raise


def main() -> None:
    output_file: str | None = None

    # Minimal arg parsing — just --output FILE
    args = sys.argv[1:]
    if args:
        if args[0] in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        if args[0] == "--output":
            if len(args) < 2:
                print("ERROR: --output requires a FILE path", file=sys.stderr)
                sys.exit(1)
            output_file = args[1]
            args = args[2:]
        else:
            print(f"ERROR: unknown argument {args[0]!r}", file=sys.stderr)
            sys.exit(1)

    # Fetch data from the Kanban board
    stats: dict = _run_hermes(["stats", "--json"])  # type: ignore[assignment]
    diagnostics: list = _run_hermes(["diagnostics", "--json"])  # type: ignore[assignment]
    diagnostics_count: int = len(diagnostics) if isinstance(diagnostics, list) else 0

    output: str = _format_metrics(stats, diagnostics_count)

    if output_file:
        _atomic_write(output_file, output)
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()

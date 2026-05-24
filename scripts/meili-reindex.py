#!/usr/bin/env python3
"""Re-index all documents in Meilisearch so the native embedder generates vectors.

Run this once after enabling FEATURE_MEILISEARCH_HYBRID=true and bringing up the
stack.  The script fetches all existing documents in pages, strips any stale
``_vectors`` key, and re-adds them.  Meilisearch calls ollama-embed internally
for each document according to the configured embedder.

Usage::

    python scripts/meili-reindex.py \\
        --url http://localhost:7700 \\
        --key YOUR_MASTER_KEY \\
        --batch-size 200

    # Dry run (print counts only, no writes):
    python scripts/meili-reindex.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
import time


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--url",
        default=os.environ.get("MEILISEARCH_URL", "http://localhost:7700"),
        help="Meilisearch base URL (default: $MEILISEARCH_URL or http://localhost:7700)",
    )
    parser.add_argument(
        "--key",
        default=os.environ.get("MEILISEARCH_MASTER_KEY", ""),
        help="Meilisearch master key (default: $MEILISEARCH_MASTER_KEY)",
    )
    parser.add_argument(
        "--index",
        default="documents",
        help="Index name (default: documents)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        metavar="N",
        help="Documents per re-add batch (default: 200)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts without writing to Meilisearch",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    try:
        import meilisearch
    except ImportError:
        print("ERROR: meilisearch package not installed. Run: pip install meilisearch", file=sys.stderr)
        sys.exit(1)

    client = meilisearch.Client(args.url, args.key)

    try:
        health = client.health()
        if health.get("status") != "available":
            print(f"ERROR: Meilisearch not available: {health}", file=sys.stderr)
            sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Cannot connect to Meilisearch at {args.url}: {exc}", file=sys.stderr)
        sys.exit(1)

    index = client.index(args.index)
    offset = 0
    total_reindexed = 0
    task_uids: list[int] = []

    print(f"Reindexing '{args.index}' at {args.url} (batch={args.batch_size}, dry_run={args.dry_run})")

    while True:
        result = index.get_documents({"offset": offset, "limit": args.batch_size})
        docs = result.results if hasattr(result, "results") else result.get("results", [])
        if not docs:
            break

        # Strip stale _vectors so Meilisearch regenerates them via the embedder.
        clean = []
        for doc in docs:
            d = dict(doc) if not isinstance(doc, dict) else doc
            d.pop("_vectors", None)
            clean.append(d)

        if not args.dry_run:
            task = index.add_documents(clean, primary_key="id")
            task_uids.append(task.task_uid)

        total_reindexed += len(clean)
        offset += len(clean)
        print(f"  Queued {total_reindexed} documents ({len(clean)} in this batch) ...")

    if args.dry_run:
        print(f"\nDry run complete. Would reindex {total_reindexed} documents.")
        return

    print(f"\nAll {total_reindexed} documents queued across {len(task_uids)} tasks.")
    print("Waiting for Meilisearch to finish embedding ...")

    # Poll until all tasks complete.
    pending = list(task_uids)
    while pending:
        still_pending = []
        for uid in pending:
            status = client.get_task(uid).status
            if status not in ("succeeded", "failed", "canceled"):
                still_pending.append(uid)
            elif status != "succeeded":
                print(f"  WARNING: task {uid} ended with status={status}", file=sys.stderr)
        if still_pending:
            print(f"  {len(still_pending)} tasks still processing ...")
            time.sleep(5)
            pending = still_pending
        else:
            break

    print(f"Done. {total_reindexed} documents reindexed with native embedder.")


if __name__ == "__main__":
    main()

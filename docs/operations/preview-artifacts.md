# Preview Artifact Cleanup

Preview artifacts are the rendered output files produced by the preview worker
(HTML, PDFs, images) and stored under `files_root/previews/`.  They are
tracked in the `document_preview_artifacts` database table.

Artifacts can accumulate as orphans after:

- A document is re-uploaded (new content SHA, old artifact directory left behind).
- A document is deleted.
- An admin-triggered re-render via `POST /admin/preview/<document_id>/rerender`.
- A failed render that was later superseded.

Orphan directories are safe to remove — they contain no original uploaded files
and no extracted document payloads, only rendered preview artifacts.

---

## When to run cleanup

Run preview artifact cleanup if:

- Disk usage under `files_root/previews/` is growing unexpectedly.
- You have recently bulk-deleted documents or performed admin re-renders.
- As part of routine maintenance on a long-running deployment.

Always run a **dry-run scan first** to confirm what will be removed before
executing.

---

## Dry-run scan

```bash
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/admin/preview/artifacts/orphans | jq .
```

Example response:

```json
{
  "dry_run": true,
  "scanned": 142,
  "valid": 138,
  "orphaned": 4,
  "deleted": 0,
  "bytes_reclaimable": 8388608,
  "error_count": 0
}
```

Fields:

| Field | Meaning |
|---|---|
| `scanned` | Total artifact directories found on disk |
| `valid` | Directories with a live `document_preview_artifacts` row |
| `orphaned` | Directories with no live DB row (candidates for removal) |
| `bytes_reclaimable` | Estimated bytes that would be freed |
| `deleted` | Always 0 in dry-run |
| `error_count` | Always 0 in dry-run |

No files are modified by the dry-run endpoint.

---

## Execute cleanup

After reviewing the dry-run output, execute the sweep:

```bash
curl -s -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8000/admin/preview/artifacts/sweep | jq .
```

Example response:

```json
{
  "dry_run": false,
  "scanned": 142,
  "valid": 138,
  "orphaned": 4,
  "deleted": 4,
  "bytes_reclaimed": 8388608,
  "error_count": 0
}
```

The sweep is **idempotent** — running it again when no orphans remain returns
`deleted: 0` without error.

---

## What the cleanup never deletes

- Original uploaded document files (stored separately under `files_root/`).
- Extracted document payloads or text.
- Active preview artifact directories referenced by `document_preview_artifacts`.
- Any file outside the `files_root/previews/` subtree.

---

## What is safe to delete

Any directory under `files_root/previews/<document-id>/<content-sha256>/`
whose `(document-id, content-sha256)` pair has no row in
`document_preview_artifacts`.  These are stale render outputs that are no
longer reachable through the API.

---

## Access control

Both endpoints require an **admin bearer token**.  Non-admin requests receive
`403 Forbidden`.

---

## Logging

Each scan and sweep logs a summary line at INFO level:

```
preview artifact orphan scan (dry-run): request_id=... admin=... scanned=142 valid=138 orphaned=4 bytes_orphaned=8388608
preview artifact orphan sweep: request_id=... admin=... scanned=142 valid=138 orphaned=4 deleted=4 bytes=8388608 errors=0
```

Internal filesystem paths are never included in log output.

---

## See Also

- `src/services/preview/artifact_store.py` — `PreviewArtifactStore.scan_orphans` and `sweep_orphans`
- `src/services/preview/artifact_repository.py` — `PreviewArtifactRepository.list_all_keys`
- `docs/operations/pipeline-workers.md` — preview-worker architecture
- Issue #749 — tracking issue for this feature

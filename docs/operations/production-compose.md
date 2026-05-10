# Production Compose Runtime

This guide covers the local production-style Compose runtime. It starts the API,
frontend container, database migration job, and required infrastructure as
separate Compose services. It is intended for operators who need to run,
validate, reset, back up, and troubleshoot Neverland without reading source
code.

## Service Layout

| Service | Published port | Purpose | Health check |
| --- | --- | --- | --- |
| `migrate` | none | Runs `alembic upgrade head` once and exits before the API starts. | Compose completion status |
| `api` | `${API_PORT:-8000}` | FastAPI app served by Uvicorn from `services.api.asgi:app`. | `GET /health` |
| `frontend` | `${FRONTEND_PORT:-8080}` | Nginx-served React frontend that proxies `/api/` to `api:8000`. | `GET /health` |
| `postgres` | `${POSTGRES_PORT:-5432}` | PostgreSQL metadata database. | `pg_isready` |
| `elasticsearch` | `${ELASTICSEARCH_PORT:-9200}` | Full-text index storage. | `GET /_cluster/health` |
| `qdrant` | `${QDRANT_PORT:-6333}` | Vector index storage. | `GET /healthz` |
| `libretranslate` | `${LIBRETRANSLATE_PORT:-5000}` | Language detection and translation service. | `GET /languages` |
| `ollama` | `${OLLAMA_PORT:-11434}` | Local LLM runtime for intelligence features. | `GET /api/tags` |
| `kafka` | `${KAFKA_PORT:-9092}` | Redpanda Kafka-compatible broker for events. | `rpk cluster health` |

Worker containers are intentionally not included yet. The current backend uses
synchronous API-triggered pipeline work and direct service classes. Add
long-running worker containers only after a real worker entrypoint exists.

## First-Run Setup

1. Copy the annotated environment template:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` before storing real data. At minimum, replace these required
   placeholders:

   - `POSTGRES_PASSWORD`
   - `POSTGRES_URL`, using the same PostgreSQL password and database name
   - `JWT_SECRET`, using a long random value
   - `LDAP_*` values if `AUTH_PROVIDER` is `ldap` or `both`

   Keep `CORS_ORIGINS` pinned to the exact browser origins that should call the
   API. For the default local frontend, use `http://localhost:8080`. Do not use a
   wildcard origin in production.

3. Validate the merged Compose configuration:

   ```bash
   docker compose config
   ```

4. Build images and start the product:

   ```bash
   docker compose up --build
   ```

5. Open the runtime after services become healthy:

   - Frontend: `http://localhost:8080`
   - Frontend health: `http://localhost:8080/health`
   - API health: `http://localhost:8000/health`
   - API health through the frontend proxy: `http://localhost:8080/api/health`

On a clean volume, Compose waits for PostgreSQL, runs the `migrate` job, waits
for Elasticsearch, Qdrant, LibreTranslate, and Ollama health checks, then starts
the API and frontend.


## Host-Mounted SMB Share Ingestion

Use a host-mounted SMB/CIFS share when operators already manage Windows or Samba
shares at the operating-system layer and Neverland only needs a read-only file
view for ingestion. This deployment path keeps SMB credentials on the Docker
host instead of storing them in Neverland source configuration, and it works when
a read-only ingestion path is enough.

This path uses the existing `folder` connector: the Docker host mounts the SMB
share, Docker Compose bind-mounts that host path into the `api` container, and
Neverland reads the in-container path as local files. It is independent from the
native SMB connector work tracked in #77 and does not mirror NTFS ACLs into
Neverland permissions.

### Linux SMB/CIFS host mount

Install the CIFS client package for your Linux distribution before mounting a
share. Many distributions package it as `cifs-utils`.

Create a host mount point and mount the share read-only:

```bash
sudo mkdir -p /mnt/neverland-smb/legal
sudo mount -t cifs //fileserver/department /mnt/neverland-smb/legal \
  -o credentials=/etc/neverland/smb-legal.credentials,ro,vers=3.0,iocharset=utf8
```

Store generic SMB credentials in a root-owned host file. Keep real credentials
out of Git, `.env`, Compose examples, documentation, and screenshots:

```ini
username=neverland-reader
password=REPLACE_WITH_SECRET
domain=CORP
```

Lock down the credential file:

```bash
sudo chown root:root /etc/neverland/smb-legal.credentials
sudo chmod 600 /etc/neverland/smb-legal.credentials
```

Optional `/etc/fstab` entry for remounting after reboot:

```fstab
//fileserver/department /mnt/neverland-smb/legal cifs credentials=/etc/neverland/smb-legal.credentials,ro,vers=3.0,iocharset=utf8,nofail 0 0
```

Verify the host can see the mounted files before starting Compose:

```bash
mount | grep /mnt/neverland-smb/legal
ls -la /mnt/neverland-smb/legal
```

### Docker Compose bind mount

Bind-mount the verified host mount into the `api` service as read-only. The host
source path must exist before `docker compose up`, and the container destination
should remain stable across upgrades, for example `/data/smb/<source-name>`:

```yaml
services:
  api:
    volumes:
      - files_data:/data
      - /mnt/neverland-smb/legal:/data/smb/legal:ro
```

Use `:ro` on the Docker bind mount even when the SMB mount is already read-only.
Keep both the host path and container path stable across upgrades so existing
Neverland source definitions continue to point at the same in-container path. In
air-gapped deployments, this path does not require internet access after host
prerequisites such as CIFS tooling are installed.

### Neverland source setup

Create the source from the admin UI or admin API with:

```text
Source type: folder
Path: /data/smb/legal
```

The `folder` connector sees the mounted SMB share as local files. The source
path must be the container path, not the host path. Neverland source permissions
control which groups can search and preview indexed documents after ingestion;
the SMB service account controls which files are visible to the host mount.

### Security guidance

- Use a dedicated read-only SMB service account.
- Scope that account only to the intended shares or subtrees.
- Store SMB credentials in a root-owned host credential file, not in Git.
- Do not put real SMB credentials in `.env`, Compose examples, docs, or
  screenshots.
- Prefer both a read-only SMB mount and a read-only Docker bind mount.
- Neverland does not mirror NTFS ACLs in this host-mounted SMB path.
- Do not rely on Windows ACLs for per-user Neverland authorization after
  ingestion; use Neverland source permissions and group grants.

### Limitations

- Mount lifecycle, reconnect behavior, DFS, and failover are host/operator
  responsibilities.
- Neverland sees the share as local files through the `folder` connector.
- NTFS ACLs are not mirrored into Neverland permissions.
- File locking and partial writes are not deeply handled by this path.
- If files change while syncing, behavior depends on mounted filesystem timing.
- Native SMB connector UX is tracked separately in #77.
- Optional NTFS ACL sync is tracked separately in #79.

### Troubleshooting host-mounted SMB sources

| Symptom | Checks |
| --- | --- |
| Container cannot see files | Verify `mount | grep /mnt/neverland-smb/legal`, confirm the bind mount is under the `api` service, and run `docker compose config` to confirm the rendered path. |
| Permission denied | Confirm the SMB service account can read the share, the host mount is readable, the credential file is root-owned with mode `600`, and the Docker bind mount uses the intended source path. |
| Empty ingestion | Confirm the Neverland source path is `/data/smb/legal` or another container path, not `/mnt/neverland-smb/legal`; also confirm the mounted subtree contains regular files. |
| Mount disappears after reboot | Add and validate an `/etc/fstab` or equivalent systemd mount entry, then remount and verify before starting Neverland. |
| Slow scans | Narrow the SMB account/share scope, use a smaller mounted subtree per source, verify network and SMB server performance, and schedule syncs outside peak file-server usage. |

SMB mount state is external host state. Back up the mount configuration and
credential file outside Neverland, keep paths stable across upgrades, and do not
use destructive volume commands to fix host mount issues.

## Air-Gapped Release Artifact

For offline deployments, use the versioned release archive generated by the
`release-artifact` GitHub Actions workflow instead of building images on the
target host. The archive contains `docker-compose.airgap.yml`, `.env.airgap.example`,
`images/neverland-images.tar`, loading and validation scripts, checksums, and the
air-gapped deployment guide. See `docs/operations/air-gapped-deployment.md` for
the full download, transfer, image loading, configuration, first-use, backup, and
restore workflow. For an existing offline deployment, use
`docs/operations/air-gapped-upgrade.md`; upgrades must preserve `.env` and named
volumes, load images from the local artifact, and run migrations without
`docker compose down -v`.

## Metrics Scraping

The API exposes Prometheus-format metrics at `GET /metrics`. In production-style
Compose, prefer scraping it over the private Compose network rather than
publishing it through an internet-facing proxy:

```yaml
scrape_configs:
  - job_name: neverland-api
    static_configs:
      - targets: ["api:8000"]
    metrics_path: /metrics
```

If operators expose `/metrics` outside the internal network, protect it with a
reverse-proxy allowlist or equivalent network control. Metric labels are kept
low-cardinality and must not include user IDs, document IDs, filenames, query
text, source names, group names, exception messages, or file contents.

The endpoint includes default Python GC and process metrics, `neverland_build_info`,
HTTP request totals, request-duration histograms, and exception totals. The API
also accepts `X-Request-ID` from trusted callers, generates one when absent, and
echoes it back on all responses including 4xx/5xx errors.

## Startup, Shutdown, And Logs

Validate Compose without starting services:

```bash
docker compose config
```

Run only the migration job:

```bash
docker compose run --rm migrate
```

Start in the foreground:

```bash
docker compose up --build
```

Start in the background:

```bash
docker compose up --build -d
```

Follow the most useful application logs:

```bash
docker compose logs -f api frontend migrate
```

Follow infrastructure logs while troubleshooting startup:

```bash
docker compose logs -f postgres elasticsearch qdrant libretranslate ollama kafka
```

Stop services without deleting named volumes:

```bash
docker compose down
```

Stop services and remove Compose-managed named volumes. This is destructive reset
guidance only; never use it during upgrades:

```bash
docker compose down -v
```

## Reset And Clean-Volume Migration

These commands are not upgrade commands. Never use `docker compose down -v` when
installing a newer release over an existing deployment; follow
`docs/operations/air-gapped-upgrade.md` instead.

Use a full reset only when you intend to delete local documents, metadata,
search indexes, vector indexes, model cache, translation cache, and Kafka data:

```bash
docker compose down -v
docker compose up --build
```

To verify a clean-volume migration without keeping services running, remove
volumes and run the migration job:

```bash
docker compose down -v
docker compose run --rm migrate
```

If the migration succeeds, start the stack normally:

```bash
docker compose up --build -d
```

## Data Volumes And Consistency

Compose creates these named volumes:

- `files_data`: original files and generated file artifacts under `FILES_ROOT`.
- `postgres_data`: document metadata, users, permissions, comments,
  annotations, and other relational state.
- `elasticsearch_data`: full-text indexes derived from PostgreSQL and files.
- `qdrant_data`: vector indexes derived from document chunks.
- `kafka_data`: local Redpanda event log.
- `libretranslate_data`: LibreTranslate downloaded language data and cache.
- `ollama_data`: local Ollama model cache.

Back up `postgres_data`, `files_data`, `elasticsearch_data`, and `qdrant_data`
together while the stack is stopped, or from a storage snapshot that captures
them at the same point in time. PostgreSQL is the source of truth for metadata,
but the file, full-text, and vector volumes must match it to avoid missing
previews, stale search results, or vector hits that refer to deleted chunks.

## Backup Guidance

For a small local deployment, the safest backup is an offline copy of the named
volumes plus a logical PostgreSQL dump:

```bash
docker compose down
mkdir -p backups

docker run --rm -v neverland_postgres_data:/volume -v "$PWD/backups:/backup" \
  alpine sh -c 'tar czf /backup/postgres_data.tgz -C /volume .'
docker run --rm -v neverland_files_data:/volume -v "$PWD/backups:/backup" \
  alpine sh -c 'tar czf /backup/files_data.tgz -C /volume .'
docker run --rm -v neverland_elasticsearch_data:/volume -v "$PWD/backups:/backup" \
  alpine sh -c 'tar czf /backup/elasticsearch_data.tgz -C /volume .'
docker run --rm -v neverland_qdrant_data:/volume -v "$PWD/backups:/backup" \
  alpine sh -c 'tar czf /backup/qdrant_data.tgz -C /volume .'

docker compose up -d postgres
docker compose exec -T postgres pg_dump -U "${POSTGRES_USER:-postgres}" \
  "${POSTGRES_DB:-app}" > backups/postgres.sql
```

Adjust the `neverland_` volume prefix if your Compose project name is different.
Run `docker volume ls` to confirm exact names before copying volume data.

For larger deployments, prefer storage-level snapshots taken while services are
stopped or application writes are paused. If Elasticsearch or Qdrant indexes are
lost but PostgreSQL and file storage are intact, plan a controlled re-ingestion
or re-indexing operation rather than mixing indexes from a different backup
point.

## Restore Guidance

For air-gapped upgrade rollback, prefer `scripts/restore-airgap-data.sh` with the
backup created by `scripts/backup-airgap-data.sh`. The generic volume recreation
example below is for deliberate disaster recovery or clean lab restoration, not
normal upgrades.

Restore all consistency-sensitive volumes from the same backup set. A typical
local restore is:

```bash
docker compose down -v

docker volume create neverland_postgres_data
docker volume create neverland_files_data
docker volume create neverland_elasticsearch_data
docker volume create neverland_qdrant_data

docker run --rm -v neverland_postgres_data:/volume -v "$PWD/backups:/backup" \
  alpine sh -c 'tar xzf /backup/postgres_data.tgz -C /volume'
docker run --rm -v neverland_files_data:/volume -v "$PWD/backups:/backup" \
  alpine sh -c 'tar xzf /backup/files_data.tgz -C /volume'
docker run --rm -v neverland_elasticsearch_data:/volume -v "$PWD/backups:/backup" \
  alpine sh -c 'tar xzf /backup/elasticsearch_data.tgz -C /volume'
docker run --rm -v neverland_qdrant_data:/volume -v "$PWD/backups:/backup" \
  alpine sh -c 'tar xzf /backup/qdrant_data.tgz -C /volume'

docker compose up --build -d
```

If you restore PostgreSQL from a logical dump instead of a volume archive, start
only PostgreSQL, load the dump, then start the full stack:

```bash
docker compose up -d postgres
docker compose exec -T postgres psql -U "${POSTGRES_USER:-postgres}" \
  "${POSTGRES_DB:-app}" < backups/postgres.sql
docker compose up --build -d
```

Do not restore PostgreSQL from one point in time and Elasticsearch or Qdrant from
another unless you are prepared to rebuild indexes.

## Health Checks And Service Ports

Use these commands to inspect runtime health from the host:

```bash
curl -fsS http://localhost:8000/health
curl -fsS http://localhost:8080/health
curl -fsS http://localhost:8080/api/health
curl -fsS http://localhost:9200/_cluster/health
curl -fsS http://localhost:6333/healthz
curl -fsS http://localhost:5000/languages
curl -fsS http://localhost:11434/api/tags
```

PostgreSQL and Kafka health checks are usually inspected through Compose:

```bash
docker compose ps
docker compose logs postgres kafka
```

If you changed any `*_PORT` value in `.env`, use the changed host port in the
host-side `curl` commands. Containers still communicate on their internal service
ports and names, such as `api:8000` and `postgres:5432`.

## Troubleshooting

### Migration failures

Inspect migration and database logs:

```bash
docker compose logs migrate postgres
```

After fixing credentials, connectivity, or migration conflicts, re-run:

```bash
docker compose run --rm migrate
```

If a clean environment is acceptable outside an upgrade window, reset volumes and start again:

```bash
docker compose down -v
docker compose up --build
```

### Elasticsearch index startup

If the API starts but search fails, check Elasticsearch health and API startup
logs for index-creation errors:

```bash
curl -fsS http://localhost:9200/_cluster/health
docker compose logs api elasticsearch
```

The API creates and uses application indexes during startup and ingestion. Fix
Elasticsearch health or disk issues first, then restart the API:

```bash
docker compose restart api
```

### Qdrant startup races

Compose waits for Qdrant `GET /healthz`, and the API health dependency retries
through Compose health checks. If Qdrant becomes healthy after the API exhausted
startup attempts, restart the API after Qdrant is healthy:

```bash
docker compose ps qdrant
docker compose restart api
```

### Ollama model availability

The Ollama health check proves the service is reachable, not that the configured
model has already been downloaded. If summaries, tags, or Q&A fail because the
model is missing, pull the configured model manually:

```bash
docker compose exec ollama ollama pull "${OLLAMA_MODEL:-mistral}"
```

Then retry the failed application operation or restart the API if needed:

```bash
docker compose restart api
```

### Authentication failures

If local login or token validation fails, confirm `JWT_SECRET` was changed from
the placeholder before users were created and that every API container uses the
same value. Tokens signed with an old secret become invalid after changing it.

For LDAP login failures, verify these values match the directory environment:

- `AUTH_PROVIDER`
- `LDAP_URL`
- `LDAP_BASE_DN`
- `LDAP_BIND_USER`
- `LDAP_BIND_PASSWORD`

If you do not intend to use LDAP, set `AUTH_PROVIDER=local` so placeholder LDAP
settings are ignored.

### Frontend/API proxy issues

The default browser entry point is `http://localhost:8080`. The frontend proxies
API requests under `/api/` to the `api` service inside Compose. If the UI loads
but API calls fail:

1. Check frontend proxy health from the host:

   ```bash
   curl -fsS http://localhost:8080/api/health
   ```

2. Check direct API health from the host:

   ```bash
   curl -fsS http://localhost:8000/health
   ```

3. Confirm `CORS_ORIGINS` includes the browser origin exactly, including scheme
   and port, for example `http://localhost:8080`.

4. Inspect logs:

   ```bash
   docker compose logs frontend api
   ```

## Production Audit Helper

Run the static production audit helper before the runtime smoke test when you
want a quick review gate that does not start or mutate Compose services:

```bash
bash scripts/production-audit.sh
```

The helper checks pending diff whitespace, verifies that `docker compose config`
renders, and scans tracked application code for hardcoded secret-like
assignments outside test files. Dependency audits can require network access, so
they are opt-in:

```bash
bash scripts/production-audit.sh --include-dependency-audits
```

The opt-in mode runs `uv run pip-audit` and `npm --prefix frontend audit`. If a
review environment lacks Docker, npm, uv, or network access, record the exact
failed command and environment limitation in the PR notes before continuing with
the no-mock smoke test.

## NiFi Kafka Event Ingestion

Issue #65 adds a minimal event-driven NiFi path for deployments that already run
Redpanda/Kafka. CI and deterministic tests use fake consumer/message objects; no
live NiFi or Kafka service is required by the test suite. The Compose runtime
still has no dedicated long-running worker container for this path, so operators
should invoke the bounded drain from an approved operational entrypoint until a
future worker phase adds supervised runtime wiring.

Create an enabled `nifi` ingestion source before sending events. The source must
be granted to Neverland groups in the normal admin UI/API; NiFi-ingested
documents are inserted with `documents.source = 'nifi'` and the source's
`source_id`, so search, preview, download, and RAG access continue to use the
existing source-grant model.

Required event fields:

- `source_id` (UUID) or `source_key` (matches `ingestion_sources.name` or
  `config.source_key`).
- `external_id` stable within that source. Neverland stores it as
  `nifi:<external_id>` and skips reprocessing when the same source/external-id
  already exists.
- `title` or `filename`.
- `mime_type`.
- `payload`.

Optional event fields: `source_language`, lowercase hex `sha256`, JSON-object
`metadata`, `event_timestamp`, `correlation_id`, and `dlq_id`.

Supported payload strategies:

- `{"type":"inline_text","text":"..."}` for pre-extracted text. The text is
  passed to the standard pipeline as `pre_extracted_text`; it is never logged.
- `{"type":"staged_file","path":"/..."}` for local files already staged into
  the API runtime. The source config **must** contain `staging_root`; events
  using this strategy are rejected (DLQ-routed) when `staging_root` is not
  configured. The file path must resolve under `staging_root`. Operators should
  keep staged paths non-sensitive because paths are persisted on document rows
  for extraction.

Checksum validation is enforced when `sha256` is present. Malformed JSON,
invalid envelopes, unknown/disabled/non-NiFi sources, inaccessible staged files,
checksum mismatches, connector normalization failures, and pipeline failures are
routed to DLQ with sanitized reason text. Offsets are committed only after
successful processing or successful DLQ routing; if DLQ routing fails, the offset
is not committed. Transient consumer infrastructure errors are retried with
bounded exponential backoff and are not DLQ-routed by default.

Known limitations: no HTTP callback endpoint, no built-in long-running consumer
container, no live NiFi/Kafka CI validation, and no dedicated monitoring hooks
beyond existing DLQ/admin surfaces.

## No-Mock Smoke Test

Run the production smoke test from the repository root after reviewing `.env`:

```bash
bash scripts/smoke-test.sh
```

By default the script builds and starts the stack, runs the API-container
smoke bootstrap helper to create an idempotent admin/group/source fixture and a
deterministic document under the Compose `/data` volume, verifies login,
synchronous ingestion, search, preview, download, and frontend reachability,
then tears the stack down with volumes. For debugging an existing stack, use:

```bash
bash scripts/smoke-test.sh --use-running --keep-running
```

The script accepts environment overrides for local ports, smoke credentials,
fixture names, and polling timeouts; run `bash scripts/smoke-test.sh --help` for
the full list. It does not print tokens or authorization headers, and on failure
it prints the `docker compose logs` command to inspect service output.

### Placeholder secrets and stale `.env` files

Tracked examples intentionally use placeholder secrets. If `docker compose config`
still shows `change-me-*` values after you edited `.env`, confirm the file is in
the repository root and that the variable names match `.env.example` exactly.

## Current Limitations

- Long-running worker containers are not present yet; ingestion and intelligence
  work are synchronous or API-triggered in the current runtime.
- NiFi event ingestion is release-usable through the bounded Kafka drain in
  `services.pipeline.kafka_consumer`. This release does not add a long-running
  worker container; operators wire the drain into an approved scheduler or
  operational entrypoint and keep live NiFi/Kafka validation outside CI.
- Confluence and Jira Server/Data Center connectors are implemented, but
  Atlassian page/project permission synchronization is not present; access is
  governed by Neverland source grants.
- The native SMB connector uses `smbprotocol` with service-account
  username/password authentication and Neverland source grants. It does not
  mirror NTFS ACLs; Kerberos and DFS support are follow-up limitations. Host
  mounted SMB/CIFS shares can also be ingested through the folder connector.
- Legacy Office support for `.doc`, `.xls`, and `.ppt` remains deferred to Phase
  09.

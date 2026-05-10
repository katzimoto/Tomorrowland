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

Stop services and remove Compose-managed named volumes:

```bash
docker compose down -v
```

## Reset And Clean-Volume Migration

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

If a clean environment is acceptable, reset volumes and start again:

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
- NiFi remains a registered connector stub; event integration is deferred to
  Phase 09.
- Confluence and Jira Server/Data Center connectors are implemented, but
  Atlassian page/project permission synchronization is not present; access is
  governed by Neverland source grants.
- Legacy Office support for `.doc`, `.xls`, and `.ppt` remains deferred to Phase
  09.

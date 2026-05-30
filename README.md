# Tomorrowland

Tomorrowland is a local-first knowledge intelligence system for private document
corpora. It indexes files and enterprise sources into a private search workspace
with previews, permissions, translation, collaboration, and optional local
LLM-powered intelligence. It is designed to run without runtime internet access
when installed from the air-gapped release artifacts.

Canonical requirements live in `spec.md` and `spec-v4.pdf`; operational guidance
lives under `docs/`.

## What it is

- A private document discovery platform for local and air-gapped environments.
- A Docker Compose application with FastAPI, React, PostgreSQL, Meilisearch,
  Qdrant, Kafka-compatible event plumbing, LibreTranslate, and optional Ollama.
- A release artifact workflow that separates a small platform archive from large
  split Docker image parts and optional model bundles.

## Key capabilities

- Hybrid keyword/vector search with permission filtering.
- Document preview, safe download paths, comments, annotations, subscriptions,
  related documents, and expertise evidence.
- Local users/groups with LDAP integration boundaries.
- Translation through a bundled LibreTranslate image for supported languages.
- Optional local Q&A/RAG and intelligence features when an approved Ollama model
  bundle is loaded.
- Admin source management for supported connectors.

## Quick start

Run this from the repository root for a connected development or evaluation
machine:

```bash
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD, POSTGRES_URL, JWT_SECRET, and any local ports.
docker compose up --build
```

Open:

- Frontend: <http://localhost:8080>
- API health: <http://localhost:8000/health>
- Frontend health: <http://localhost:8080/health>

Useful non-destructive commands:

```bash
docker compose config
docker compose run --rm migrate
docker compose logs -f api frontend migrate
docker compose down
```

> **Never use `docker compose down -v` for upgrades.** The `-v` flag deletes
> persistent product data volumes.

See [`docs/operations/production-compose.md`](docs/operations/production-compose.md)
for production-style Compose operations.

## Air-gapped deployment

Use the air-gapped release when the target host cannot reach the internet at
runtime. The preferred operator entrypoint is:

```bash
./scripts/tomorrowland-airgap.sh
```

Required release files:

```text
tomorrowland-release-<version>.tar.gz              platform archive
tomorrowland-release-<version>.tar.gz.sha256
tomorrowland-images-<version>.tar.part-*           split Docker image parts
tomorrowland-images-<version>.tar.parts.sha256
```

Optional release files:

```text
tomorrowland-ollama-bundle-<model>-<version>.tar.gz
tomorrowland-ollama-bundle-<model>-<version>.tar.gz.sha256
```

Run this from the directory containing the downloaded release files:

```bash
sha256sum -c tomorrowland-release-<version>.tar.gz.sha256
sha256sum -c tomorrowland-images-<version>.tar.parts.sha256

tar xzf tomorrowland-release-<version>.tar.gz
cd tomorrowland-release-<version>

cp .env.airgap.example .env
nano .env

./scripts/tomorrowland-airgap.sh validate --load-images
./scripts/tomorrowland-airgap.sh up
./scripts/tomorrowland-airgap.sh status
```

For the complete offline install guide, read
[`README-airgap.md`](README-airgap.md) first, then
[`docs/operations/air-gapped-deployment.md`](docs/operations/air-gapped-deployment.md).

## Upgrade without data loss

Air-gapped upgrades preserve `.env` and persistent Docker volumes. Always back up
first, load images from local artifacts only, run the documented migration path,
and validate after startup.

Run this from the existing deployment directory, not from the new artifact:

```bash
./scripts/tomorrowland-airgap.sh upgrade \
  --artifact-dir ../tomorrowland-release-<version>
```

Read [`docs/operations/air-gapped-upgrade.md`](docs/operations/air-gapped-upgrade.md)
before upgrading.

## Supported connectors

Current operator-facing source paths include:

- Folder sources from host-mounted paths.
- Host-mounted SMB/CIFS shares exposed as read-only folder sources.
- Confluence Server/Data Center polling sources.
- Jira Server/Data Center polling sources.
- NiFi-produced Kafka event ingestion for deployments that already provide the
  event stream and staged files.

Some connector hardening remains intentionally optional or deferred, including
native NTFS ACL sync and optional Atlassian permission hardening.

## Release artifacts

Terminology used across the docs:

| Term | Meaning |
| --- | --- |
| Platform archive | Small `tomorrowland-release-<version>.tar.gz` archive containing Compose files, env templates, docs, scripts, manifests, and checksums. |
| Image parts | Required `tomorrowland-images-<version>.tar.part-*` files. The wrapper streams them into Docker; operators do not manually concatenate them. |
| Optional model bundle | Optional `tomorrowland-ollama-bundle-<model>-<version>.tar.gz` with Ollama model weights. Needed for offline Q&A/RAG/local intelligence, not for platform startup. |
| Legacy names | Earlier `neverland-*` release asset names may appear in historical notes only. `tomorrowland-*` is canonical for new operator-facing examples. |

Future OCR or additional model packs should remain optional add-on artifacts
unless release notes explicitly say otherwise.

## Development setup

- Backend: Python 3.11+, FastAPI, SQLAlchemy, PostgreSQL, Meilisearch, Qdrant.
- Frontend: React 19, TypeScript, Vite in `frontend/`.
- Start with [`docs/development/local-dev.md`](docs/development/local-dev.md).
- Test commands are summarized in [`docs/development/testing.md`](docs/development/testing.md).

## Documentation index

Start with [`docs/README.md`](docs/README.md), which routes by audience:

- Operators: deployment, upgrade, production Compose, release notes.
- Developers: local development, testing, architecture overview.
- Agents: issue-first context loading, token efficiency, and handoff templates.

## Security and data-safety notes

- Keep real secrets out of release artifacts, docs, screenshots, and source
  control. `.env.airgap.example` contains placeholders only.
- Preserve `.env`, named volumes, and host-mounted source paths across upgrades.
- Do not assume runtime internet exists in air-gapped mode; validate that images
  and optional model bundles are already loaded locally.
- Use source grants and groups for Tomorrowland authorization. Host-mounted SMB
  service accounts control what files are visible to ingestion, not per-user UI
  access after ingestion.

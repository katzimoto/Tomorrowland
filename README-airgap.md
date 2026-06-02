# Tomorrowland Air-Gapped Release

This is the short operator note for installing Tomorrowland on a host with no
runtime internet access. For details, use
[`docs/operations/air-gapped-deployment.md`](docs/operations/air-gapped-deployment.md).

## Files you need

Required (the platform starts with only these):

```text
tomorrowland-release-<version>.tar.gz              platform archive (small, no model weights)
tomorrowland-release-<version>.tar.gz.sha256
tomorrowland-images-<version>.tar.part-*           split Docker image parts
tomorrowland-images-<version>.tar.parts.sha256
```

Optional (only for offline Q&A/RAG/local intelligence):

```text
tomorrowland-ollama-bundle-<model>-<version>.tar.gz  local AI model weights
tomorrowland-ollama-bundle-<model>-<version>.tar.gz.sha256
```

Keep the split image parts beside the platform archive. The wrapper script loads
parts directly; do not concatenate them by hand.

## How local AI works

The platform archive includes the Ollama runtime Docker image but does **not**
include any model weights. The platform starts without local AI. A missing model
bundle is a warning, not an error. Without any model, the base platform (keyword
search, preview, permissions, translation, ingest) works normally; only
embedding-backed semantic search and Q&A/RAG/local intelligence are degraded.

There are two ways to enable AI features **without** the Ollama model bundle:

1. **External LLM (recommended if you already run one):** point Tomorrowland at a
   local OpenAI-compatible endpoint such as a **LiteLLM** proxy, vLLM, or
   llama.cpp by setting `LLM_PROVIDER` / `LLM_BASE_URL` / `LLM_MODEL` (and the
   `EMBEDDING_*` equivalents) in `.env`. See "Using an external LLM" in
   [`docs/operations/air-gapped-deployment.md`](docs/operations/air-gapped-deployment.md).
2. **Ollama model bundle:** transfer and load the optional
   `tomorrowland-ollama-bundle-<model>-<version>.tar.gz` asset into the bundled
   Ollama service.

## Quick start

Run this from the directory containing the downloaded release files:

```bash
sha256sum -c tomorrowland-release-<version>.tar.gz.sha256
sha256sum -c tomorrowland-images-<version>.tar.parts.sha256

tar xzf tomorrowland-release-<version>.tar.gz
cd tomorrowland-release-<version>
```

## Configure

Run this from the extracted release directory:

```bash
cp .env.airgap.example .env
nano .env
```

Replace every `change-me-*` placeholder. Keep `POSTGRES_PASSWORD` and the
password inside `POSTGRES_URL` in sync. Keep `JWT_SECRET` stable after users are
created.

## Validate and load images

Run this from the extracted release directory:

```bash
./scripts/tomorrowland-airgap.sh validate --load-images
```

If image parts are not beside the extracted release directory, pass their
location explicitly:

```bash
./scripts/tomorrowland-airgap.sh validate --load-images \
  --image-parts-dir /media/usb/tomorrowland-images
```

## Start

Run this from the extracted release directory:

```bash
./scripts/tomorrowland-airgap.sh up
```

## Check status

Run this from the extracted release directory:

```bash
./scripts/tomorrowland-airgap.sh status
curl -fsS http://127.0.0.1:${API_PORT:-8000}/health
curl -fsS http://127.0.0.1:${FRONTEND_PORT:-8080}/health
```

Open the frontend at the configured frontend host and port, usually
`http://localhost:8080`.

## Troubleshooting

- Missing images: rerun `validate --load-images` and confirm all
  `tomorrowland-images-<version>.tar.part-*` files and
  `tomorrowland-images-<version>.tar.parts.sha256` are present.
- Image parts on removable media: use `--image-parts-dir`.
- Compose tries to build or pull: stop and confirm you are using
  `docker-compose.airgap.yml` through `scripts/tomorrowland-airgap.sh`.
- Ollama model missing: platform startup can continue, but Q&A/RAG/local
  intelligence is degraded until the optional model bundle is loaded and
  validated. This is a warning, not a startup failure.

## Safety notes

> **Never run `docker compose down -v` during install or upgrade.** It deletes
> persistent product data volumes.

Use `./scripts/tomorrowland-airgap.sh down` to stop services while preserving
volumes. Use [`docs/operations/air-gapped-upgrade.md`](docs/operations/air-gapped-upgrade.md)
for existing deployments.

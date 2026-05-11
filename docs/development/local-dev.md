# Local Development

Use this guide for a connected development or evaluation machine. Air-gapped
operators should use `README-airgap.md` and
`docs/operations/air-gapped-deployment.md` instead.

## Prerequisites

- Python 3.11 or newer.
- Docker Engine and Docker Compose plugin.
- Node.js/npm for frontend work in `frontend/`.

## Start the Compose runtime

Run this from the repository root:

```bash
cp .env.example .env
# Edit .env: set POSTGRES_PASSWORD, POSTGRES_URL, JWT_SECRET, and local ports.
docker compose up --build
```

Open:

- Frontend: <http://localhost:8080>
- API health: <http://localhost:8000/health>
- Frontend health: <http://localhost:8080/health>

## Useful commands

Run these from the repository root:

```bash
docker compose config
docker compose run --rm migrate
docker compose logs -f api frontend migrate
docker compose down
```

> **Do not use `docker compose down -v` unless you intentionally want a destructive
> local reset.** Never use it during upgrades.

## Where to look next

- Backend routes currently live in `src/services/api/main.py`.
- Frontend source lives in `frontend/`.
- Production-style Compose details are in
  `docs/operations/production-compose.md`.
- Current work should be driven by GitHub Issues and PRs rather than historical
  implementation phase tables.

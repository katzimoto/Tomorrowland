# Production Compose Runtime

This guide covers the Phase 08a local production runtime. It starts the API,
frontend container, database migration job, and required infrastructure as
separate Compose services.

## Service Layout

- `migrate` runs `alembic upgrade head` once and exits.
- `api` runs Uvicorn with `services.api.asgi:app`.
- `frontend` runs Nginx on port `8080` and proxies `/api/` to the API service.
- `postgres`, `elasticsearch`, `qdrant`, `libretranslate`, `ollama`, and
  `kafka` run as independent infrastructure services.

Worker containers are intentionally not included yet. The backend currently
uses direct service classes and API-triggered work. Add worker containers only
after a real long-running worker entrypoint exists.

## First Run

Copy the example environment and change secrets before using the runtime for
real data:

```bash
cp .env.example .env
```

At minimum, change:

- `POSTGRES_PASSWORD`
- `POSTGRES_URL` to match that password
- `JWT_SECRET`
- LDAP settings if `AUTH_PROVIDER` is `ldap` or `both`

Start the product:

```bash
docker compose up --build
```

Open:

- Frontend: `http://localhost:8080`
- API health: `http://localhost:8000/health`
- Frontend health: `http://localhost:8080/health`

## Common Commands

Validate Compose without starting services:

```bash
docker compose config
```

Run only migrations:

```bash
docker compose run --rm migrate
```

Start in the background:

```bash
docker compose up --build -d
```

Follow logs:

```bash
docker compose logs -f api frontend migrate
```

Stop services without deleting data:

```bash
docker compose down
```

Reset all Compose-managed data:

```bash
docker compose down -v
```

## Data Volumes

Compose creates named volumes for:

- `files_data`
- `postgres_data`
- `kafka_data`
- `elasticsearch_data`
- `qdrant_data`
- `libretranslate_data`
- `ollama_data`

Back up `postgres_data`, `files_data`, `elasticsearch_data`, and `qdrant_data`
together to keep document metadata and search indexes consistent.

## Phase 08a Limitations

- The frontend is a runtime placeholder; the React UI lands in Phase 08b.
- The no-mock product smoke test lands in Phase 08f-3.
- Optional NiFi, Atlassian, and old Office support are deferred to Phase 09.

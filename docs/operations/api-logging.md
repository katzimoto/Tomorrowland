# API Logging

The API writes logs to stdout and stderr. In Docker Compose, inspect them with:

```bash
docker compose logs -f api
```

For connector sync failures, include recent logs and the request ID returned by the failed API response:

```bash
docker compose logs --since=15m api
```

To temporarily increase API verbosity for local troubleshooting, use the logging override:

```bash
LOG_LEVEL=debug docker compose -f docker-compose.yml -f docker-compose.logging.yml up -d api
```

Then reproduce the failing operation and inspect the API logs again:

```bash
docker compose logs --since=15m api
```

Return to the normal production-style configuration by recreating the API service without the override:

```bash
docker compose up -d api
```

Unhandled API errors are logged with the request ID, HTTP method, path, route template, status code, error type, and source ID when the route contains one. Folder connector file-read failures also log the failing file path and configured source path before the error bubbles up to the API response.

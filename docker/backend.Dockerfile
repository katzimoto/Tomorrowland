FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=info
ENV UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gosu \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv pip install --no-cache --system -r pyproject.toml

COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src

RUN uv pip install --no-cache --system .

# Non-root user. /data is the files-volume mount point; we chown it here so
# that new volume deployments get the correct ownership automatically. For
# upgrades from root-only images the entrypoint re-chowns at startup.
RUN groupadd -g 1000 appuser \
    && useradd -u 1000 -g 1000 -r -M -s /sbin/nologin appuser \
    && mkdir -p /data \
    && chown appuser:appuser /data

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn services.api.asgi:app --host 0.0.0.0 --port 8000 --log-level ${LOG_LEVEL:-info}"]

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=info
ENV UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv pip install --no-cache --system -r pyproject.toml

COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src

RUN uv pip install --no-cache --system .

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn services.api.asgi:app --host 0.0.0.0 --port 8000 --log-level ${LOG_LEVEL:-info}"]

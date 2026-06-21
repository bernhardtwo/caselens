# syntax=docker/dockerfile:1
# Build context is the repo root so data/corpus is available for the bootstrap ingest:
#   docker build -f apps/api/Dockerfile -t caselens-api .

FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY apps/api/src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv ./.venv
COPY --chown=app:app apps/api/pyproject.toml ./
COPY --chown=app:app apps/api/src ./src
COPY --chown=app:app data/corpus ./data/corpus
USER app
EXPOSE 8000
CMD ["uvicorn", "caselens.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

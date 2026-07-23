# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin --uid 10001 llmux

WORKDIR /app

# --- Build: install dependencies from the locked lockfile -----------------
FROM base AS build
COPY --from=ghcr.io/astral-sh/uv:0.5.20 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# --- Runtime: copy the project and run as non-root -------------------------
FROM base AS runtime
COPY --from=build /app/.venv /app/.venv
COPY --from=ghcr.io/astral-sh/uv:0.5.20 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev \
    && chown -R llmux:llmux /app
USER llmux

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/v1/health || exit 1

CMD ["uvicorn", "llmux.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies + uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install Python dependencies
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra all && \
    uv pip install fastapi uvicorn psycopg2-binary

# Copy source
COPY . .

# Create logs directory
RUN mkdir -p /app/logs

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["sh", "-c", "uv run alembic upgrade head || uv run alembic stamp head || echo 'Alembic skipped'; exec uv run python -m cli.main start --platform web"]

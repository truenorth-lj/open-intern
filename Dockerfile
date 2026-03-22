FROM python:3.12-slim

WORKDIR /app

# Install system dependencies + uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install Python dependencies
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra all --extra telegram && \
    uv pip install fastapi uvicorn psycopg2-binary

# Copy source
COPY . .

# Create logs directory and default config
RUN mkdir -p /app/logs && \
    cp config/agent.example.yaml config/agent.yaml

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["sh", "-c", "alembic upgrade head || alembic stamp head || echo 'Alembic skipped'; exec python -m cli.main start --web"]

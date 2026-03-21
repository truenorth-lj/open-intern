FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir ".[all]" fastapi uvicorn

# Copy source
COPY . .

# Create logs directory and default config
RUN mkdir -p /app/logs && \
    cp config/agent.example.yaml config/agent.yaml

EXPOSE 8080

CMD ["python", "-m", "cli.main", "start", "--web"]

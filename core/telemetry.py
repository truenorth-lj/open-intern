"""Telemetry — structured logging, Prometheus metrics, and request correlation."""

from __future__ import annotations

import contextvars
import logging
import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# ---------------------------------------------------------------------------
# Correlation ID — propagated through async context
# ---------------------------------------------------------------------------

_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    return _correlation_id.get()


def set_correlation_id(cid: str) -> contextvars.Token[str]:
    return _correlation_id.set(cid)


# ---------------------------------------------------------------------------
# Structured JSON log formatter
# ---------------------------------------------------------------------------


class JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON for structured log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        obj: dict[str, Any] = {
            "ts": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        cid = _correlation_id.get()
        if cid:
            obj["correlation_id"] = cid
        if record.exc_info and record.exc_info[1]:
            obj["exception"] = self.formatException(record.exc_info)
        # Extra fields injected via logging.info("...", extra={...})
        for key in ("agent_id", "platform", "duration_ms", "tokens", "method", "path"):
            val = getattr(record, key, None)
            if val is not None:
                obj[key] = val
        return json.dumps(obj, default=str)


def configure_logging(json_format: bool = True) -> None:
    """Replace the root logger's formatter with JSON output.

    Call once at startup (replaces logging.basicConfig).
    When *json_format* is False, keeps the default human-readable format
    (useful for local development / debugging).
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Remove existing handlers
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler()
    if json_format:
        handler.setFormatter(JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
    root.addHandler(handler)


# ---------------------------------------------------------------------------
# Prometheus metrics (lazy init — noop if prometheus_client not installed)
# ---------------------------------------------------------------------------

try:
    from prometheus_client import Counter, Histogram, generate_latest

    AGENT_CHAT_TOTAL = Counter(
        "agent_chat_total",
        "Total agent chat invocations",
        ["agent_id", "platform", "status"],
    )
    AGENT_CHAT_DURATION = Histogram(
        "agent_chat_duration_seconds",
        "Agent chat latency",
        ["agent_id", "platform"],
        buckets=(0.5, 1, 2, 5, 10, 30, 60, 120),
    )
    LLM_TOKENS_TOTAL = Counter(
        "llm_tokens_total",
        "LLM token usage",
        ["agent_id", "provider", "direction"],  # direction: input | output
    )
    MEMORY_OP_DURATION = Histogram(
        "memory_op_duration_seconds",
        "Memory store/recall latency",
        ["agent_id", "operation"],  # operation: store | recall
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2),
    )
    PLATFORM_MESSAGE_TOTAL = Counter(
        "platform_message_total",
        "Platform messages handled",
        ["platform", "status"],  # status: ok | error | retry
    )
    HTTP_REQUEST_DURATION = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency",
        ["method", "path_template", "status_code"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
    )
    ERROR_TOTAL = Counter(
        "error_total",
        "Errors by category",
        ["category"],  # budget | rate_limit | safety | llm | memory | platform
    )

    _PROMETHEUS_AVAILABLE = True

except ImportError:
    _PROMETHEUS_AVAILABLE = False

    # Noop stubs so instrumented code doesn't need guards
    class _NoopMetric:
        def labels(self, *a: Any, **kw: Any) -> _NoopMetric:
            return self

        def inc(self, amount: float = 1) -> None:
            pass

        def observe(self, amount: float) -> None:
            pass

    AGENT_CHAT_TOTAL = _NoopMetric()  # type: ignore[assignment]
    AGENT_CHAT_DURATION = _NoopMetric()  # type: ignore[assignment]
    LLM_TOKENS_TOTAL = _NoopMetric()  # type: ignore[assignment]
    MEMORY_OP_DURATION = _NoopMetric()  # type: ignore[assignment]
    PLATFORM_MESSAGE_TOTAL = _NoopMetric()  # type: ignore[assignment]
    HTTP_REQUEST_DURATION = _NoopMetric()  # type: ignore[assignment]
    ERROR_TOTAL = _NoopMetric()  # type: ignore[assignment]

    def generate_latest() -> bytes:  # type: ignore[misc]
        return b"# prometheus_client not installed\n"


# ---------------------------------------------------------------------------
# FastAPI middleware — correlation ID + request metrics
# ---------------------------------------------------------------------------


class TelemetryMiddleware(BaseHTTPMiddleware):
    """Inject correlation ID and record HTTP request metrics."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        cid = request.headers.get("X-Correlation-ID") or str(uuid4())
        token = set_correlation_id(cid)

        status_code: int = 500
        start = time.perf_counter()
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            ERROR_TOTAL.labels(category="http").inc()
            raise
        finally:
            duration = time.perf_counter() - start
            path = _normalise_path(request.url.path)
            HTTP_REQUEST_DURATION.labels(
                method=request.method,
                path_template=path,
                status_code=str(status_code),
            ).observe(duration)

            _correlation_id.reset(token)

        response.headers["X-Correlation-ID"] = cid
        return response


def _normalise_path(path: str) -> str:
    """Collapse path segments that look like IDs to reduce cardinality."""
    parts = path.strip("/").split("/")
    normalised = []
    for part in parts:
        # UUIDs, hex strings > 8 chars, or pure digits → placeholder
        if len(part) > 8 and (part.replace("-", "").isalnum()):
            normalised.append("{id}")
        elif part.isdigit():
            normalised.append("{id}")
        else:
            normalised.append(part)
    return "/" + "/".join(normalised)


# ---------------------------------------------------------------------------
# /metrics endpoint helper
# ---------------------------------------------------------------------------


def metrics_response() -> Response:
    """Return Prometheus metrics as text/plain."""
    from starlette.responses import Response as StarletteResponse

    body = generate_latest()
    return StarletteResponse(
        content=body,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )

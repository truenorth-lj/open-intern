"""Sentry error tracking — opt-in via SENTRY_DSN environment variable.

When SENTRY_DSN is empty (the default), this module is a no-op: no SDK is
imported, no data is sent, and the ``zero telemetry`` promise is preserved.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_sentry_initialized = False


def init_sentry(
    dsn: str,
    environment: str = "production",
    traces_sample_rate: float = 0.1,
    profiles_sample_rate: float = 0.1,
) -> bool:
    """Initialize Sentry SDK if *dsn* is provided.

    Returns True if Sentry was successfully initialized, False otherwise.
    """
    global _sentry_initialized

    if not dsn:
        logger.debug("SENTRY_DSN not set — Sentry disabled")
        return False

    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            traces_sample_rate=traces_sample_rate,
            profiles_sample_rate=profiles_sample_rate,
            send_default_pii=False,
            enable_tracing=True,
        )
        _sentry_initialized = True
        logger.info("Sentry initialized (environment=%s)", environment)
        return True
    except Exception:
        logger.warning("Failed to initialize Sentry", exc_info=True)
        return False


def is_sentry_enabled() -> bool:
    return _sentry_initialized

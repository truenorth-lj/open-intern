"""Centralized database engine management.

All modules share a single connection pool instead of creating independent engines.
This prevents pool fragmentation and centralizes the psycopg URL workaround.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


def normalize_database_url(url: str) -> str:
    """Normalize database URL to use the default psycopg2 driver.

    LangGraph's PostgresSaver uses psycopg v3 directly, but SQLAlchemy ORM code
    uses psycopg2 (the default driver). This converts ``postgresql+psycopg://``
    to ``postgresql://`` so SQLAlchemy picks up psycopg2.
    """
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql://", 1)
    return url


@lru_cache(maxsize=4)
def get_engine(database_url: str) -> Engine:
    """Get or create a shared SQLAlchemy engine for the given URL.

    The engine is cached per URL so all modules share the same connection pool.
    """
    sa_url = normalize_database_url(database_url)
    engine = create_engine(
        sa_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )
    logger.info("Created shared database engine")
    return engine


def get_session_factory(database_url: str) -> sessionmaker[Session]:
    """Get a sessionmaker bound to the shared engine."""
    return sessionmaker(bind=get_engine(database_url))

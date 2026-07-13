"""PostgreSQL connectivity helper (raw articles, ingestion logs, provenance)."""

from __future__ import annotations

import psycopg

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def get_connection() -> psycopg.Connection:
    """Open a new PostgreSQL connection using the configured DSN."""
    return psycopg.connect(settings.postgres_dsn)


def verify_connectivity() -> bool:
    """Return True if PostgreSQL is reachable."""
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except psycopg.Error as exc:  # pragma: no cover - network path
        logger.warning("PostgreSQL not reachable: %s", exc)
        return False

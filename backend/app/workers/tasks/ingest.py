"""Celery ingestion tasks.

Each task fetches from a source, maps everything to the unified Article model,
and persists the raw rows to Postgres. These are wired to Celery Beat in
``app.workers.celery_app`` to run on a cron-like schedule.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.db import articles as article_store
from app.ingestion import gdelt, reddit
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="ingest.gdelt",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def ingest_gdelt(self) -> dict[str, Any]:
    """Fetch the latest GDELT 2.0 GKG batch and store new articles."""
    if not settings.gdelt_enabled:
        logger.info("GDELT ingestion disabled - skipping")
        return {"source": "gdelt", "skipped": True}

    try:
        fetched = gdelt.fetch_latest_articles()
        stored = article_store.upsert_articles(fetched)
    except Exception as exc:
        logger.exception("GDELT ingestion failed")
        raise self.retry(exc=exc) from exc

    return {"source": "gdelt", "fetched": len(fetched), "stored": stored}


@celery_app.task(
    name="ingest.reddit",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def ingest_reddit(self) -> dict[str, Any]:
    """Fetch hot threads from the configured subreddits and store new articles."""
    if not settings.reddit_enabled:
        logger.info("Reddit ingestion disabled - skipping")
        return {"source": "reddit", "skipped": True}

    try:
        fetched = reddit.fetch_hot_articles()
        stored = article_store.upsert_articles(fetched)
    except Exception as exc:
        logger.exception("Reddit ingestion failed")
        raise self.retry(exc=exc) from exc

    return {"source": "reddit", "fetched": len(fetched), "stored": stored}

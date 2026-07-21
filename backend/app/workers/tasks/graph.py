"""Celery task that flushes analyzed articles into the Neo4j knowledge graph.

``graph.sync_pending`` pulls a batch of articles that have been NER-processed but
not yet written to the graph, and pushes them with batched ``UNWIND`` Cypher
(see ``app.graph.writer``). Runs on the default queue on a Beat schedule and is
also kicked off after ingestion.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.db import articles as article_store
from app.graph import writer
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="graph.sync_pending",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def sync_pending(self, limit: int | None = None) -> dict[str, Any]:
    """Write a batch of analyzed-but-not-graphed articles into Neo4j."""
    if not settings.graph_sync_enabled:
        logger.info("Graph sync disabled - skipping")
        return {"synced": 0, "skipped": True}

    batch = settings.graph_sync_batch_size if limit is None else limit
    article_ids = article_store.fetch_analyzed_not_graphed_ids(batch)
    if not article_ids:
        return {"synced": 0}

    try:
        stats = writer.sync_articles(article_ids)
        article_store.mark_graphed(article_ids)
    except Exception as exc:
        logger.exception("Graph sync failed for %d article(s)", len(article_ids))
        raise self.retry(exc=exc) from exc

    return {"synced": len(article_ids), **stats}

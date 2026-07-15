"""Celery NLP tasks (CPU-heavy, routed to the ``nlp_tasks`` queue).

- ``nlp.dispatch_pending`` (light, default queue): scans Postgres for articles
  that have not been analyzed yet and fans out one ``nlp.process_article`` task
  per article.
- ``nlp.process_article`` (heavy, ``nlp_tasks`` queue): runs NER + entity
  resolution + co-occurrence relations for a single article and stores the result.
"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.db import analysis as analysis_store
from app.db import articles as article_store
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="nlp.dispatch_pending", bind=True)
def dispatch_pending(self, limit: int | None = None) -> dict[str, Any]:
    """Enqueue NLP processing for articles that have not been analyzed yet."""
    if not settings.nlp_enabled:
        logger.info("NLP disabled - skipping dispatch")
        return {"dispatched": 0, "skipped": True}

    batch = settings.nlp_dispatch_batch_size if limit is None else limit
    article_ids = article_store.fetch_unprocessed_ids(batch)
    for article_id in article_ids:
        process_article.delay(article_id)

    logger.info("Dispatched %d article(s) for NLP processing", len(article_ids))
    return {"dispatched": len(article_ids)}


@celery_app.task(
    name="nlp.process_article",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def process_article(self, article_id: str) -> dict[str, Any]:
    """Run the NLP pipeline for one article and persist entities + relations."""
    # Imported lazily so the light dispatcher/worker doesn't pull spaCy into memory.
    from app.nlp import processor

    article = article_store.fetch_article(article_id)
    if article is None:
        logger.warning("Article %s not found - nothing to process", article_id)
        return {"article_id": article_id, "found": False}

    try:
        result = processor.process_article(article)
        analysis_store.save_analysis(result)
        article_store.mark_processed([article_id])
    except Exception as exc:
        logger.exception("NLP processing failed for %s", article_id)
        raise self.retry(exc=exc) from exc

    return {
        "article_id": article_id,
        "entities": len(result.entities),
        "relations": len(result.relations),
    }

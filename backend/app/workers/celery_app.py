"""Celery application entrypoint.

Broker: RabbitMQ (AMQP). Result backend: Redis.
Ingestion tasks live under ``app.workers.tasks`` and are scheduled via Celery Beat.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

celery_app = Celery(
    "osint",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.workers.tasks.ingest",
        "app.workers.tasks.nlp",
        "app.workers.tasks.graph",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
    task_default_queue="celery",
)

# Route CPU-heavy NER work to a dedicated queue so it can be scaled/isolated
# independently from the lightweight ingestion + dispatch tasks.
celery_app.conf.task_routes = {
    "nlp.process_article": {"queue": settings.nlp_queue_name},
}

# ------------------------------------------------------------------
# Celery Beat: cron-like periodic ingestion.
# GDELT refreshes every 15 minutes; Reddit "hot" we poll on the same cadence.
# ------------------------------------------------------------------
celery_app.conf.beat_schedule = {
    "ingest-gdelt": {
        "task": "ingest.gdelt",
        "schedule": crontab(minute=f"*/{settings.ingest_gdelt_interval_minutes}"),
    },
    "ingest-reddit": {
        "task": "ingest.reddit",
        "schedule": crontab(minute=f"*/{settings.ingest_reddit_interval_minutes}"),
    },
    "nlp-dispatch-pending": {
        "task": "nlp.dispatch_pending",
        "schedule": crontab(minute=f"*/{settings.nlp_dispatch_interval_minutes}"),
    },
    "graph-sync-pending": {
        "task": "graph.sync_pending",
        "schedule": crontab(minute=f"*/{settings.graph_sync_interval_minutes}"),
    },
}


@worker_ready.connect
def _bootstrap_storage(**_: object) -> None:
    """Ensure the Postgres schema exists once the worker is up."""
    try:
        from app.db import analysis, articles

        articles.init_schema()
        analysis.init_schema()
    except Exception:  # pragma: no cover - startup best-effort
        logger.exception("Failed to initialize Postgres schema on worker startup")


@celery_app.task(name="health.ping")
def ping() -> str:
    """Trivial task used to verify the worker pipeline end-to-end."""
    return "pong"

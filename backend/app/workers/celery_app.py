"""Celery application entrypoint.

Broker: RabbitMQ (AMQP). Result backend: Redis.
NER / ingestion tasks will live under `app.workers.tasks` (Phase 2).
"""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "osint",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)


@celery_app.task(name="health.ping")
def ping() -> str:
    """Trivial task used to verify the worker pipeline end-to-end."""
    return "pong"

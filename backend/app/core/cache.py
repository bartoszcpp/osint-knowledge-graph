"""Small Redis-backed JSON cache for expensive graph queries.

Graph traversals can be slow, so the hottest read endpoints cache their JSON
response for a few minutes (``CACHE_TTL_SECONDS``). The cache is best-effort:
any Redis error is swallowed and the caller falls back to computing the value, so
a Redis outage degrades performance but never breaks the API.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from functools import lru_cache
from typing import Any

import redis

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def make_key(namespace: str, **params: Any) -> str:
    """Build a stable cache key from a namespace and query parameters."""
    raw = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha1(raw.encode()).hexdigest()[:16]  # noqa: S324 - not security-sensitive
    return f"{settings.cache_key_prefix}:{namespace}:{digest}"


def get_json(key: str) -> Any | None:
    """Return a cached value, or None on miss / any Redis error."""
    if not settings.cache_enabled:
        return None
    try:
        raw = _client().get(key)
    except redis.RedisError as exc:  # pragma: no cover - network path
        logger.warning("Cache read failed (%s): %s", key, exc)
        return None
    return json.loads(raw) if raw else None


def set_json(key: str, value: Any, ttl: int | None = None) -> None:
    """Store a JSON-serializable value with a TTL (best-effort)."""
    if not settings.cache_enabled:
        return
    ttl = settings.cache_ttl_seconds if ttl is None else ttl
    try:
        _client().setex(key, ttl, json.dumps(value, default=str))
    except redis.RedisError as exc:  # pragma: no cover - network path
        logger.warning("Cache write failed (%s): %s", key, exc)


def get_or_set(key: str, producer: Callable[[], Any], ttl: int | None = None) -> Any:
    """Return the cached value for ``key`` or compute, store and return it."""
    cached = get_json(key)
    if cached is not None:
        return cached
    value = producer()
    set_json(key, value, ttl=ttl)
    return value

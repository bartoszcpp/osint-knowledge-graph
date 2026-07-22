"""Public graph API (Phase 5).

Endpoints the React frontend calls to explore the knowledge graph:
- GET /entities            trending entities in a time window (paginated)
- GET /graph/{entity_id}   ego-graph around an entity (1-2 hops)
- GET /articles            articles connecting two entities (the edge evidence)

Expensive graph reads are cached in Redis for a few minutes (best-effort).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from app.core import cache
from app.core.config import settings
from app.core.logging import get_logger
from app.graph import reader
from app.schemas.analysis import EntityType
from app.schemas.api import EgoGraph, PaginatedArticles, PaginatedEntities

logger = get_logger(__name__)

router = APIRouter(tags=["graph"])


def _guard(producer):
    """Run a reader call, translating Neo4j outages into 503s."""
    try:
        return producer()
    except (ServiceUnavailable, Neo4jError) as exc:
        logger.warning("Graph query failed: %s", exc)
        raise HTTPException(status_code=503, detail="Graph database unavailable") from exc


@router.get("/entities", response_model=PaginatedEntities, summary="Trending entities")
def list_entities(
    window_hours: int = Query(
        default=settings.api_entities_window_hours,
        ge=1,
        le=24 * 30,
        description="Look-back window in hours (default 24h).",
    ),
    limit: int = Query(default=settings.api_default_page_size, ge=1, le=settings.api_max_page_size),
    offset: int = Query(default=0, ge=0),
    type: EntityType | None = Query(default=None, description="Filter by entity type."),
) -> Any:
    """Most frequently mentioned entities in the last ``window_hours`` (paginated)."""
    type_value = type.value if type else None
    key = cache.make_key(
        "entities", window_hours=window_hours, limit=limit, offset=offset, type=type_value
    )
    cached = cache.get_json(key)
    if cached is not None:
        return cached

    result = _guard(lambda: reader.top_entities(window_hours, limit, offset, type_value))
    payload = result.model_dump(mode="json")
    cache.set_json(key, payload)
    return payload


@router.get("/graph/{entity_id}", response_model=EgoGraph, summary="Ego-graph for an entity")
def get_ego_graph(
    entity_id: str = Path(description="Entity canonical id, e.g. 'person:elon-musk'."),
    depth: int = Query(default=1, ge=1, le=2, description="Neighborhood depth (1 or 2)."),
    limit: int = Query(
        default=settings.graph_default_neighbor_limit,
        ge=1,
        le=settings.graph_max_neighbor_limit,
        description="Max neighbors expanded per hop.",
    ),
    min_weight: int = Query(default=1, ge=1, description="Minimum edge weight to include."),
    window_days: int | None = Query(
        default=None, ge=1, description="Only relations from the last N days."
    ),
) -> Any:
    """Return the center entity, its neighbors up to ``depth`` hops, and their edges."""
    key = cache.make_key(
        "graph",
        entity_id=entity_id,
        depth=depth,
        limit=limit,
        min_weight=min_weight,
        window_days=window_days,
    )
    cached = cache.get_json(key)
    if cached is not None:
        return cached

    result = _guard(
        lambda: reader.ego_graph(entity_id, depth, limit, min_weight, window_days=window_days)
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_id}' not found")

    payload = result.model_dump(mode="json")
    cache.set_json(key, payload)
    return payload


@router.get("/articles", response_model=PaginatedArticles, summary="Articles linking two entities")
def list_connecting_articles(
    source: str = Query(description="First entity canonical id."),
    target: str = Query(description="Second entity canonical id."),
    limit: int = Query(default=settings.api_default_page_size, ge=1, le=settings.api_max_page_size),
    offset: int = Query(default=0, ge=0),
    window_days: int | None = Query(
        default=None, ge=1, description="Only articles from the last N days."
    ),
) -> Any:
    """Articles mentioning both entities - the evidence behind a co-occurrence edge."""
    key = cache.make_key(
        "articles",
        source=source,
        target=target,
        limit=limit,
        offset=offset,
        window_days=window_days,
    )
    cached = cache.get_json(key)
    if cached is not None:
        return cached

    result = _guard(
        lambda: reader.connecting_articles(source, target, limit, offset, window_days=window_days)
    )
    payload = result.model_dump(mode="json")
    cache.set_json(key, payload)
    return payload

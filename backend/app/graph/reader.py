"""Read side of the knowledge graph: queries powering the public API.

Design note on time filtering: relationships are derived two ways.
- All-time (no ``since``): we read the pre-aggregated ``CO_OCCURS_WITH`` edges
  built in Phase 4 (fast).
- Time-windowed (``since`` set): we recompute co-occurrence on the fly from the
  articles the entities share within the window
  ``(e1)-[:MENTIONED_IN]->(:Article)<-[:MENTIONED_IN]-(e2)``, so "last week only"
  is always accurate rather than reflecting stale aggregate weights.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.logging import get_logger
from app.db import neo4j
from app.schemas.api import (
    ArticleSummary,
    EgoGraph,
    EntitySummary,
    GraphEdge,
    GraphNode,
    PaginatedArticles,
    PaginatedEntities,
)

logger = get_logger(__name__)


def _since(hours: int | None = None, days: int | None = None) -> datetime | None:
    if hours is not None:
        return datetime.now(tz=UTC) - timedelta(hours=hours)
    if days is not None:
        return datetime.now(tz=UTC) - timedelta(days=days)
    return None


def _read(query: str, **params: Any) -> list[dict]:
    driver = neo4j.get_driver()
    with driver.session() as session:
        return session.execute_read(lambda tx: [r.data() for r in tx.run(query, **params)])


def _to_datetime(value: Any) -> datetime | None:
    """Convert a Neo4j DateTime to a native python datetime."""
    if value is None:
        return None
    return value.to_native() if hasattr(value, "to_native") else value


# ---------------------------------------------------------------------------
# 5.1: trending entities in a time window
# ---------------------------------------------------------------------------

_TOP_ENTITIES = """
MATCH (e:Entity)-[m:MENTIONED_IN]->(a:Article)
WHERE a.published_at >= $since AND ($type IS NULL OR e.type = $type)
WITH e, count(DISTINCT a) AS article_count, coalesce(sum(m.count), 0) AS mention_count
RETURN e.canonical_id AS canonical_id, e.name AS name, e.type AS type,
       article_count, mention_count
ORDER BY article_count DESC, mention_count DESC
SKIP $offset LIMIT $limit
"""

_TOP_ENTITIES_TOTAL = """
MATCH (e:Entity)-[:MENTIONED_IN]->(a:Article)
WHERE a.published_at >= $since AND ($type IS NULL OR e.type = $type)
RETURN count(DISTINCT e) AS total
"""


def top_entities(
    window_hours: int,
    limit: int,
    offset: int,
    entity_type: str | None = None,
) -> PaginatedEntities:
    """Most frequently mentioned entities within the last ``window_hours``."""
    params = {
        "since": _since(hours=window_hours),
        "type": entity_type,
        "limit": limit,
        "offset": offset,
    }
    rows = _read(_TOP_ENTITIES, **params)
    total = _read(_TOP_ENTITIES_TOTAL, since=params["since"], type=entity_type)[0]["total"]

    items = [
        EntitySummary(
            canonical_id=r["canonical_id"],
            name=r["name"],
            type=r["type"],
            article_count=r["article_count"],
            mention_count=r["mention_count"],
        )
        for r in rows
    ]
    return PaginatedEntities(
        items=items, total=total, limit=limit, offset=offset, window_hours=window_hours
    )


# ---------------------------------------------------------------------------
# 5.2 + 5.4: ego-graph around an entity (optionally time-windowed)
# ---------------------------------------------------------------------------

# Neighbor discovery, all-time (pre-aggregated edges).
_NEIGHBORS_ALLTIME = """
UNWIND $seeds AS seed
MATCH (s:Entity {canonical_id: seed})-[r:CO_OCCURS_WITH]-(n:Entity)
WHERE r.weight >= $min_weight AND NOT n.canonical_id IN $exclude
WITH n.canonical_id AS id, max(r.weight) AS w
RETURN id ORDER BY w DESC LIMIT $limit
"""

# Neighbor discovery, time-windowed (recomputed from shared articles).
_NEIGHBORS_WINDOW = """
UNWIND $seeds AS seed
MATCH (s:Entity {canonical_id: seed})-[:MENTIONED_IN]->(a:Article)<-[:MENTIONED_IN]-(n:Entity)
WHERE a.published_at >= $since AND NOT n.canonical_id IN $exclude
WITH n.canonical_id AS id, count(DISTINCT a) AS w
WHERE w >= $min_weight
RETURN id ORDER BY w DESC LIMIT $limit
"""

_NODES = """
MATCH (e:Entity) WHERE e.canonical_id IN $ids
RETURN e.canonical_id AS id, e.name AS name, e.type AS type
"""

_EDGES_ALLTIME = """
MATCH (x:Entity)-[r:CO_OCCURS_WITH]-(y:Entity)
WHERE x.canonical_id IN $ids AND y.canonical_id IN $ids AND x.canonical_id < y.canonical_id
RETURN x.canonical_id AS source, y.canonical_id AS target, r.weight AS weight
"""

_EDGES_WINDOW = """
MATCH (x:Entity)-[:MENTIONED_IN]->(a:Article)<-[:MENTIONED_IN]-(y:Entity)
WHERE x.canonical_id IN $ids AND y.canonical_id IN $ids AND x.canonical_id < y.canonical_id
  AND a.published_at >= $since
WITH x.canonical_id AS source, y.canonical_id AS target, count(DISTINCT a) AS weight
RETURN source, target, weight
"""


def ego_graph(
    center_id: str,
    depth: int,
    neighbor_limit: int,
    min_weight: int,
    window_days: int | None = None,
) -> EgoGraph | None:
    """Return the ego-graph (center + neighbors up to ``depth`` hops) or None.

    None means the center entity does not exist in the graph.
    """
    since = _since(days=window_days)
    neighbor_q = _NEIGHBORS_WINDOW if since else _NEIGHBORS_ALLTIME
    edges_q = _EDGES_WINDOW if since else _EDGES_ALLTIME

    node_ids: set[str] = {center_id}

    # Level 1.
    seeds = [center_id]
    level1 = _read(
        neighbor_q,
        seeds=seeds,
        exclude=list(node_ids),
        min_weight=min_weight,
        limit=neighbor_limit,
        since=since,
    )
    level1_ids = [r["id"] for r in level1]
    node_ids.update(level1_ids)

    # Level 2 (neighbors of level-1 neighbors).
    if depth >= 2 and level1_ids:
        level2 = _read(
            neighbor_q,
            seeds=level1_ids,
            exclude=list(node_ids),
            min_weight=min_weight,
            limit=neighbor_limit,
            since=since,
        )
        node_ids.update(r["id"] for r in level2)

    ids = list(node_ids)
    node_rows = _read(_NODES, ids=ids)
    if not any(r["id"] == center_id for r in node_rows):
        return None

    edge_rows = _read(edges_q, ids=ids, since=since)

    return EgoGraph(
        center=center_id,
        depth=depth,
        nodes=[GraphNode(id=r["id"], name=r["name"], type=r["type"]) for r in node_rows],
        edges=[
            GraphEdge(source=r["source"], target=r["target"], weight=r["weight"]) for r in edge_rows
        ],
    )


# ---------------------------------------------------------------------------
# 5.3 + 5.4: articles connecting two entities (optionally time-windowed)
# ---------------------------------------------------------------------------

_CONNECTING_ARTICLES = """
MATCH (x:Entity {canonical_id: $source})-[:MENTIONED_IN]->(art:Article)
      <-[:MENTIONED_IN]-(y:Entity {canonical_id: $target})
WHERE ($since IS NULL OR art.published_at >= $since)
RETURN DISTINCT art.article_id AS article_id, art.url AS url, art.title AS title,
       art.published_at AS published_at, art.source AS source
ORDER BY published_at DESC
SKIP $offset LIMIT $limit
"""

_CONNECTING_ARTICLES_TOTAL = """
MATCH (x:Entity {canonical_id: $source})-[:MENTIONED_IN]->(art:Article)
      <-[:MENTIONED_IN]-(y:Entity {canonical_id: $target})
WHERE ($since IS NULL OR art.published_at >= $since)
RETURN count(DISTINCT art) AS total
"""


def connecting_articles(
    source_id: str,
    target_id: str,
    limit: int,
    offset: int,
    window_days: int | None = None,
) -> PaginatedArticles:
    """Articles in which both entities are mentioned (the evidence for an edge)."""
    since = _since(days=window_days)
    params = {"source": source_id, "target": target_id, "since": since}

    rows = _read(_CONNECTING_ARTICLES, **params, limit=limit, offset=offset)
    total = _read(_CONNECTING_ARTICLES_TOTAL, **params)[0]["total"]

    items = [
        ArticleSummary(
            article_id=r["article_id"],
            url=r["url"],
            title=r["title"],
            published_at=_to_datetime(r["published_at"]),
            source=r["source"],
        )
        for r in rows
    ]
    return PaginatedArticles(items=items, total=total, limit=limit, offset=offset)

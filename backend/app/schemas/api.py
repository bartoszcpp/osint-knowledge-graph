"""Response models for the public graph API (Phase 5)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.analysis import EntityType


class EntitySummary(BaseModel):
    """An entity ranked by how often it appears in a time window."""

    canonical_id: str
    name: str
    type: EntityType
    article_count: int  # distinct articles the entity appears in
    mention_count: int  # total mentions across those articles


class PaginatedEntities(BaseModel):
    items: list[EntitySummary]
    total: int
    limit: int
    offset: int
    window_hours: int | None = None


class GraphNode(BaseModel):
    id: str  # canonical_id
    name: str
    type: EntityType


class GraphEdge(BaseModel):
    source: str  # canonical_id
    target: str  # canonical_id
    weight: int


class EgoGraph(BaseModel):
    """Ego-graph around a center entity: neighbors up to N hops + their edges."""

    center: str
    depth: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class ArticleSummary(BaseModel):
    article_id: str
    url: str
    title: str | None = None
    published_at: datetime | None = None
    source: str


class PaginatedArticles(BaseModel):
    items: list[ArticleSummary]
    total: int
    limit: int
    offset: int

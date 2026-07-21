"""Payload shapes for a batched Neo4j write.

These mirror exactly what the ``UNWIND $rows`` Cypher statements expect, so the
(pure, testable) payload builder and the Neo4j writer share one contract.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GraphArticle(BaseModel):
    article_id: str
    url: str
    title: str | None = None
    published_at: datetime
    source: str


class GraphEntity(BaseModel):
    canonical_id: str
    name: str
    type: str


class GraphMention(BaseModel):
    """(:Entity)-[:MENTIONED_IN {count}]->(:Article)"""

    entity_id: str
    url: str
    count: int


class GraphCooccurrence(BaseModel):
    """(:Entity)-[:CO_OCCURS_WITH {weight}]-(:Entity), undirected."""

    source_id: str
    target_id: str
    weight: int


class GraphBatch(BaseModel):
    """Everything needed to write one batch of articles into the graph."""

    articles: list[GraphArticle] = []
    entities: list[GraphEntity] = []
    mentions: list[GraphMention] = []
    cooccurrences: list[GraphCooccurrence] = []

    def is_empty(self) -> bool:
        return not (self.articles or self.entities or self.mentions or self.cooccurrences)

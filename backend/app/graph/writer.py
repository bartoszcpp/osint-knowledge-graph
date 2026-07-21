"""Batched writes of NLP analysis into the Neo4j knowledge graph.

The whole point of Phase 4 is to move the detected entities/relations into Neo4j
*efficiently*: instead of firing thousands of tiny queries, we assemble a batch
(default 100 articles) and push it with a handful of ``UNWIND``-driven Cypher
statements - one round-trip per node/edge type.

``build_batch`` is a pure function (no I/O) so the payload assembly, entity
de-duplication and co-occurrence aggregation are unit-testable without a database.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from app.core.logging import get_logger
from app.db import neo4j
from app.schemas.analysis import ArticleAnalysis
from app.schemas.article import Article
from app.schemas.graph import (
    GraphArticle,
    GraphBatch,
    GraphCooccurrence,
    GraphEntity,
    GraphMention,
)

logger = get_logger(__name__)

# ---- Cypher (each MERGEs on the unique business key, so writes are idempotent) ----

# 4.1: Article nodes.
Q_ARTICLES = """
UNWIND $rows AS row
MERGE (a:Article {url: row.url})
SET a.article_id = row.article_id,
    a.title = row.title,
    a.published_at = row.published_at,
    a.source = row.source
"""

# 4.1: Entity nodes (keep the most informative display name on conflict).
Q_ENTITIES = """
UNWIND $rows AS row
MERGE (e:Entity {canonical_id: row.canonical_id})
ON CREATE SET e.name = row.name, e.type = row.type
ON MATCH SET e.type = row.type,
             e.name = CASE
                 WHEN size(row.name) > size(coalesce(e.name, '')) THEN row.name
                 ELSE e.name
             END
"""

# 4.2: (:Entity)-[:MENTIONED_IN {count}]->(:Article)
Q_MENTIONS = """
UNWIND $rows AS row
MATCH (e:Entity {canonical_id: row.entity_id})
MATCH (a:Article {url: row.url})
MERGE (e)-[m:MENTIONED_IN]->(a)
SET m.count = row.count
"""

# 4.3: (:Entity)-[:CO_OCCURS_WITH {weight}]-(:Entity), weight grows per article.
Q_COOCCUR = """
UNWIND $rows AS row
MATCH (a:Entity {canonical_id: row.source_id})
MATCH (b:Entity {canonical_id: row.target_id})
MERGE (a)-[r:CO_OCCURS_WITH]-(b)
ON CREATE SET r.weight = row.weight
ON MATCH SET r.weight = r.weight + row.weight
"""


def build_batch(articles: Sequence[Article], analyses: Sequence[ArticleAnalysis]) -> GraphBatch:
    """Assemble the UNWIND payload from articles and their stored analyses."""
    article_by_id = {a.id: a for a in articles}

    graph_articles: list[GraphArticle] = []
    entities: dict[str, GraphEntity] = {}
    mentions: list[GraphMention] = []
    cooccur_weights: Counter[tuple[str, str]] = Counter()

    for analysis in analyses:
        article = article_by_id.get(analysis.article_id)
        if article is None:
            continue

        graph_articles.append(
            GraphArticle(
                article_id=article.id,
                url=article.url,
                title=article.title,
                published_at=article.published_at,
                source=article.source.value,
            )
        )

        for entity in analysis.entities:
            existing = entities.get(entity.canonical_id)
            # De-dupe entities across the batch, keeping the longest name.
            if existing is None or len(entity.name) > len(existing.name):
                entities[entity.canonical_id] = GraphEntity(
                    canonical_id=entity.canonical_id,
                    name=entity.name,
                    type=entity.type.value,
                )
            mentions.append(
                GraphMention(
                    entity_id=entity.canonical_id,
                    url=article.url,
                    count=entity.mention_count,
                )
            )

        # One increment per (pair, article): weight == number of articles the pair
        # co-occurs in. De-dupe pairs within the article defensively.
        seen_pairs: set[tuple[str, str]] = set()
        for relation in analysis.relations:
            pair = tuple(sorted((relation.source_id, relation.target_id)))
            if pair[0] == pair[1] or pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            cooccur_weights[pair] += 1

    cooccurrences = [
        GraphCooccurrence(source_id=a, target_id=b, weight=weight)
        for (a, b), weight in cooccur_weights.items()
    ]

    return GraphBatch(
        articles=graph_articles,
        entities=list(entities.values()),
        mentions=mentions,
        cooccurrences=cooccurrences,
    )


def _write_tx(tx, batch: GraphBatch) -> None:
    if batch.articles:
        tx.run(Q_ARTICLES, rows=[a.model_dump() for a in batch.articles])
    if batch.entities:
        tx.run(Q_ENTITIES, rows=[e.model_dump() for e in batch.entities])
    if batch.mentions:
        tx.run(Q_MENTIONS, rows=[m.model_dump() for m in batch.mentions])
    if batch.cooccurrences:
        tx.run(Q_COOCCUR, rows=[c.model_dump() for c in batch.cooccurrences])


def write_batch(batch: GraphBatch) -> None:
    """Write one assembled batch to Neo4j in a single transaction."""
    if batch.is_empty():
        return
    driver = neo4j.get_driver()
    with driver.session() as session:
        session.execute_write(_write_tx, batch)
    logger.info(
        "Graph batch written: %d article(s), %d entit(y/ies), %d mention(s), %d edge(s)",
        len(batch.articles),
        len(batch.entities),
        len(batch.mentions),
        len(batch.cooccurrences),
    )


def sync_articles(article_ids: Sequence[str]) -> dict[str, int]:
    """Load analyses for the given articles and write them to the graph."""
    from app.db import analysis as analysis_store
    from app.db import articles as article_store

    articles = article_store.fetch_articles(article_ids)
    analyses = analysis_store.fetch_analyses(article_ids)
    batch = build_batch(articles, analyses)
    write_batch(batch)
    return {
        "articles": len(batch.articles),
        "entities": len(batch.entities),
        "mentions": len(batch.mentions),
        "cooccurrences": len(batch.cooccurrences),
    }

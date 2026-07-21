"""Persistence for NLP analysis output (entities + relations).

Structured NER results live in Postgres alongside the raw articles. Writing the
same entities/relations into the Neo4j knowledge graph is Phase 4; keeping them
in Postgres now makes the pipeline testable and queryable end-to-end.

Each ``save_analysis`` call is idempotent per article: existing rows for the
article are replaced, so re-processing never duplicates data.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from app.core.logging import get_logger
from app.db.postgres import get_connection
from app.schemas.analysis import ArticleAnalysis, EntityType, Relation, ResolvedEntity

logger = get_logger(__name__)

_CREATE_ENTITIES = """
CREATE TABLE IF NOT EXISTS article_entities (
    article_id     TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    canonical_id   TEXT NOT NULL,
    name           TEXT NOT NULL,
    type           TEXT NOT NULL,
    mention_count  INT  NOT NULL DEFAULT 0,
    surface_forms  JSONB NOT NULL DEFAULT '[]'::jsonb,
    PRIMARY KEY (article_id, canonical_id)
)
"""

_CREATE_RELATIONS = """
CREATE TABLE IF NOT EXISTS article_relations (
    article_id   TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    source_id    TEXT NOT NULL,
    target_id    TEXT NOT NULL,
    source_name  TEXT NOT NULL,
    target_name  TEXT NOT NULL,
    source_type  TEXT NOT NULL,
    target_type  TEXT NOT NULL,
    weight       INT  NOT NULL DEFAULT 1,
    scope        TEXT NOT NULL,
    PRIMARY KEY (article_id, source_id, target_id)
)
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS article_entities_canonical_idx ON article_entities (canonical_id)",
    "CREATE INDEX IF NOT EXISTS article_entities_type_idx ON article_entities (type)",
    "CREATE INDEX IF NOT EXISTS article_relations_source_idx ON article_relations (source_id)",
    "CREATE INDEX IF NOT EXISTS article_relations_target_idx ON article_relations (target_id)",
)


def init_schema() -> None:
    """Create the entity/relation tables and indexes. Idempotent."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(_CREATE_ENTITIES)
        cur.execute(_CREATE_RELATIONS)
        for stmt in _INDEXES:
            cur.execute(stmt)
        conn.commit()
    logger.info("PostgreSQL schema ready (article_entities + article_relations)")


def save_analysis(analysis: ArticleAnalysis) -> None:
    """Replace stored entities/relations for the analysis' article."""
    from psycopg.types.json import Jsonb

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM article_entities WHERE article_id = %s", (analysis.article_id,))
        cur.execute("DELETE FROM article_relations WHERE article_id = %s", (analysis.article_id,))

        if analysis.entities:
            cur.executemany(
                "INSERT INTO article_entities "
                "(article_id, canonical_id, name, type, mention_count, surface_forms) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                [
                    (
                        analysis.article_id,
                        e.canonical_id,
                        e.name,
                        e.type.value,
                        e.mention_count,
                        Jsonb(e.surface_forms),
                    )
                    for e in analysis.entities
                ],
            )

        if analysis.relations:
            cur.executemany(
                "INSERT INTO article_relations "
                "(article_id, source_id, target_id, source_name, target_name, "
                "source_type, target_type, weight, scope) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                [
                    (
                        analysis.article_id,
                        r.source_id,
                        r.target_id,
                        r.source_name,
                        r.target_name,
                        r.source_type.value,
                        r.target_type.value,
                        r.weight,
                        r.scope,
                    )
                    for r in analysis.relations
                ],
            )

        conn.commit()

    logger.info(
        "Saved analysis for %s: %d entit(y/ies), %d relation(s)",
        analysis.article_id,
        len(analysis.entities),
        len(analysis.relations),
    )


def fetch_analyses(article_ids: Sequence[str]) -> list[ArticleAnalysis]:
    """Reconstruct stored analyses (entities + relations) for the given articles."""
    if not article_ids:
        return []
    ids = list(article_ids)

    entities_by_article: dict[str, list[ResolvedEntity]] = defaultdict(list)
    relations_by_article: dict[str, list[Relation]] = defaultdict(list)

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT article_id, canonical_id, name, type, mention_count, surface_forms "
            "FROM article_entities WHERE article_id = ANY(%s)",
            (ids,),
        )
        for article_id, canonical, name, etype, count, surfaces in cur.fetchall():
            entities_by_article[article_id].append(
                ResolvedEntity(
                    canonical_id=canonical,
                    name=name,
                    type=EntityType(etype),
                    surface_forms=surfaces or [],
                    mention_count=count,
                )
            )

        cur.execute(
            "SELECT article_id, source_id, target_id, source_name, target_name, "
            "source_type, target_type, weight, scope "
            "FROM article_relations WHERE article_id = ANY(%s)",
            (ids,),
        )
        for row in cur.fetchall():
            article_id = row[0]
            relations_by_article[article_id].append(
                Relation(
                    source_id=row[1],
                    target_id=row[2],
                    source_name=row[3],
                    target_name=row[4],
                    source_type=EntityType(row[5]),
                    target_type=EntityType(row[6]),
                    weight=row[7],
                    scope=row[8],
                )
            )

    return [
        ArticleAnalysis(
            article_id=article_id,
            entities=entities_by_article.get(article_id, []),
            relations=relations_by_article.get(article_id, []),
        )
        for article_id in ids
        if article_id in entities_by_article or article_id in relations_by_article
    ]

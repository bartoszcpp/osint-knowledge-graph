"""Raw-article persistence in PostgreSQL.

Postgres is the durable, canonical backup of everything we ingest. If the Neo4j
knowledge graph ever needs to be rebuilt from scratch, we can replay these rows
instead of re-hitting the source APIs.

We stick with raw ``psycopg`` (no ORM) to match the rest of the project and keep
schema creation idempotent, mirroring the Neo4j ``init_schema`` approach.
"""

from __future__ import annotations

from collections.abc import Iterable

from psycopg.types.json import Jsonb

from app.core.logging import get_logger
from app.db.postgres import get_connection
from app.schemas.article import Article

logger = get_logger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS articles (
    id            TEXT PRIMARY KEY,
    source        TEXT        NOT NULL,
    url           TEXT        NOT NULL,
    title         TEXT,
    text_content  TEXT,
    published_at  TIMESTAMPTZ NOT NULL,
    raw           JSONB       NOT NULL DEFAULT '{}'::jsonb,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS articles_url_key ON articles (url)",
    "CREATE INDEX IF NOT EXISTS articles_source_idx ON articles (source)",
    "CREATE INDEX IF NOT EXISTS articles_published_at_idx ON articles (published_at DESC)",
)

_COLUMNS = ("id", "source", "url", "title", "text_content", "published_at", "raw", "fetched_at")


def init_schema() -> None:
    """Create the ``articles`` table and indexes. Idempotent (IF NOT EXISTS)."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(_CREATE_TABLE)
        for stmt in _INDEXES:
            cur.execute(stmt)
        conn.commit()
    logger.info("PostgreSQL schema ready (articles table + indexes)")


def upsert_articles(articles: Iterable[Article]) -> int:
    """Insert articles, skipping ones already stored.

    De-duplication happens on the deterministic ``id`` via ``ON CONFLICT DO
    NOTHING``. Returns the number of *newly* inserted rows.
    """
    # De-dupe within the batch so a single INSERT never lists the same id twice.
    by_id: dict[str, Article] = {a.id: a for a in articles}
    if not by_id:
        return 0

    values_sql = ",".join(["(%s, %s, %s, %s, %s, %s, %s, %s)"] * len(by_id))
    query = (
        f"INSERT INTO articles ({', '.join(_COLUMNS)}) "
        f"VALUES {values_sql} "
        "ON CONFLICT (id) DO NOTHING "
        "RETURNING id"
    )

    params: list[object] = []
    for article in by_id.values():
        params.extend(
            [
                article.id,
                article.source.value,
                article.url,
                article.title,
                article.text_content,
                article.published_at,
                Jsonb(article.raw),
                article.fetched_at,
            ]
        )

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(query, params)
        inserted = cur.fetchall()
        conn.commit()

    logger.info("Stored %d new article(s) (%d in batch)", len(inserted), len(by_id))
    return len(inserted)

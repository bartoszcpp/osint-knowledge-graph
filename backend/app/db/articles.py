"""Raw-article persistence in PostgreSQL.

Postgres is the durable, canonical backup of everything we ingest. If the Neo4j
knowledge graph ever needs to be rebuilt from scratch, we can replay these rows
instead of re-hitting the source APIs.

We stick with raw ``psycopg`` (no ORM) to match the rest of the project and keep
schema creation idempotent, mirroring the Neo4j ``init_schema`` approach.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from psycopg.types.json import Jsonb

from app.core.logging import get_logger
from app.db.postgres import get_connection
from app.schemas.article import Article, SourceType

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
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at  TIMESTAMPTZ
)
"""

# For databases created before Phase 3, add the NLP tracking column in place.
_MIGRATIONS = ("ALTER TABLE articles ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ",)

_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS articles_url_key ON articles (url)",
    "CREATE INDEX IF NOT EXISTS articles_source_idx ON articles (source)",
    "CREATE INDEX IF NOT EXISTS articles_published_at_idx ON articles (published_at DESC)",
    # Partial index: the NLP dispatcher only ever scans unprocessed rows.
    "CREATE INDEX IF NOT EXISTS articles_unprocessed_idx "
    "ON articles (fetched_at) WHERE processed_at IS NULL",
)

_COLUMNS = ("id", "source", "url", "title", "text_content", "published_at", "raw", "fetched_at")
_SELECT_COLUMNS = "id, source, url, title, text_content, published_at, raw, fetched_at"


def init_schema() -> None:
    """Create the ``articles`` table and indexes. Idempotent (IF NOT EXISTS)."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(_CREATE_TABLE)
        for stmt in _MIGRATIONS:
            cur.execute(stmt)
        for stmt in _INDEXES:
            cur.execute(stmt)
        conn.commit()
    logger.info("PostgreSQL schema ready (articles table + indexes)")


def _row_to_article(row: tuple) -> Article:
    """Reconstruct an Article from a SELECT row (bypassing url re-validation)."""
    return Article.model_construct(
        id=row[0],
        source=SourceType(row[1]),
        url=row[2],
        title=row[3],
        text_content=row[4],
        published_at=row[5],
        raw=row[6] or {},
        fetched_at=row[7],
    )


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


def fetch_article(article_id: str) -> Article | None:
    """Load a single article by id, or None if it does not exist."""
    query = f"SELECT {_SELECT_COLUMNS} FROM articles WHERE id = %s"  # noqa: S608 - fixed columns
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(query, (article_id,))
        row = cur.fetchone()
    return _row_to_article(row) if row else None


def fetch_unprocessed_ids(limit: int) -> list[str]:
    """Return ids of articles that have not been through NLP yet (oldest first)."""
    query = "SELECT id FROM articles WHERE processed_at IS NULL ORDER BY fetched_at LIMIT %s"
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(query, (limit,))
        return [row[0] for row in cur.fetchall()]


def mark_processed(article_ids: Sequence[str]) -> None:
    """Stamp ``processed_at`` on the given articles."""
    if not article_ids:
        return
    query = "UPDATE articles SET processed_at = now() WHERE id = ANY(%s)"
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(query, (list(article_ids),))
        conn.commit()

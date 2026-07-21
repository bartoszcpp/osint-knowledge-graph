"""Neo4j driver management and schema initialization.

The knowledge graph models OSINT entities as nodes and their co-occurrence /
relationships as edges. We create uniqueness constraints (which are backed by
indexes) plus lookup indexes so that MATCH-by-key is effectively O(1).
"""

from __future__ import annotations

from neo4j import Driver, GraphDatabase
from neo4j.exceptions import ServiceUnavailable

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_driver: Driver | None = None

# Node labels tracked in the graph.
#   Entity  - a resolved PERSON/ORG/GPE (property `type` distinguishes them).
#   Article - a source document the entity was mentioned in.
ENTITY_LABELS: tuple[str, ...] = (
    "Entity",
    "Article",
)

# Constraints guarantee uniqueness AND create a backing range index -> O(1) lookups.
CONSTRAINTS: dict[str, str] = {
    "Entity": "canonical_id",
    "Article": "url",
}

# Additional non-unique indexes for common filter/search fields.
EXTRA_INDEXES: list[tuple[str, str]] = [
    ("Entity", "type"),
    ("Entity", "name"),
    ("Article", "published_at"),
    ("Article", "source"),
]


def get_driver() -> Driver:
    """Return a lazily-initialized, shared Neo4j driver."""
    global _driver
    if _driver is None:
        logger.info("Initializing Neo4j driver -> %s", settings.neo4j_uri)
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _driver


def close_driver() -> None:
    """Close the shared driver (call on shutdown)."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
        logger.info("Neo4j driver closed")


def verify_connectivity() -> bool:
    """Return True if the Neo4j server is reachable."""
    try:
        get_driver().verify_connectivity()
        return True
    except (ServiceUnavailable, OSError) as exc:  # pragma: no cover - network path
        logger.warning("Neo4j not reachable: %s", exc)
        return False


def init_schema() -> None:
    """Create constraints and indexes. Idempotent (IF NOT EXISTS)."""
    driver = get_driver()
    statements: list[str] = []

    for label, key in CONSTRAINTS.items():
        cname = f"{label.lower()}_{key}_unique"
        statements.append(
            f"CREATE CONSTRAINT {cname} IF NOT EXISTS FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
        )

    for label, prop in EXTRA_INDEXES:
        iname = f"{label.lower()}_{prop}_idx"
        statements.append(f"CREATE INDEX {iname} IF NOT EXISTS FOR (n:{label}) ON (n.{prop})")

    with driver.session() as session:
        for stmt in statements:
            logger.info("Neo4j schema: %s", stmt)
            session.run(stmt)

    logger.info("Neo4j schema initialized (%d statements)", len(statements))

"""Standalone script to initialize the Neo4j schema (constraints + indexes).

Run inside the api/worker container or locally with env vars set:

    python -m scripts.init_neo4j
"""

from __future__ import annotations

import sys

from app.core.logging import get_logger
from app.db import neo4j

logger = get_logger("scripts.init_neo4j")


def main() -> int:
    if not neo4j.verify_connectivity():
        logger.error("Neo4j is not reachable at %s", neo4j.settings.neo4j_uri)
        return 1

    neo4j.init_schema()
    logger.info("Done. Constraints and indexes are in place.")
    neo4j.close_driver()
    return 0


if __name__ == "__main__":
    sys.exit(main())

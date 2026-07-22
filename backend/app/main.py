"""FastAPI application factory and entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import graph, health
from app.core.config import settings
from app.core.logging import get_logger
from app.db import analysis, articles, neo4j, postgres

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup, clean up on shutdown."""
    logger.info("Starting OSINT API (env=%s)", settings.environment)
    try:
        if neo4j.verify_connectivity():
            neo4j.init_schema()
        else:
            logger.warning("Skipping Neo4j schema init - database not reachable yet")
    except Exception:  # noqa: BLE001 - never block startup on schema init
        logger.exception("Neo4j schema initialization failed")

    try:
        if postgres.verify_connectivity():
            articles.init_schema()
            analysis.init_schema()
        else:
            logger.warning("Skipping Postgres schema init - database not reachable yet")
    except Exception:  # noqa: BLE001 - never block startup on schema init
        logger.exception("Postgres schema initialization failed")

    yield

    neo4j.close_driver()
    logger.info("OSINT API stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="OSINT Knowledge Graph API",
        description="Entity tracker & knowledge graph over GDELT / HackerNews / Reddit.",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(graph.router)

    @app.get("/", tags=["root"], summary="Service root")
    def root() -> dict[str, str]:
        return {"service": "osint-knowledge-graph", "version": __version__}

    return app


app = create_app()

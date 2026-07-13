"""Health / readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import __version__
from app.core.config import settings
from app.db import neo4j, postgres

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


class DependencyStatus(BaseModel):
    neo4j: bool
    postgres: bool


class ReadinessResponse(BaseModel):
    status: str
    dependencies: DependencyStatus


@router.get("/healthcheck", response_model=HealthResponse, summary="Liveness probe")
def healthcheck() -> HealthResponse:
    """Basic liveness check - the process is up and serving requests."""
    return HealthResponse(
        status="ok",
        version=__version__,
        environment=settings.environment,
    )


@router.get("/readiness", response_model=ReadinessResponse, summary="Readiness probe")
def readiness() -> ReadinessResponse:
    """Deep check verifying downstream dependencies are reachable."""
    deps = DependencyStatus(
        neo4j=neo4j.verify_connectivity(),
        postgres=postgres.verify_connectivity(),
    )
    status = "ok" if (deps.neo4j and deps.postgres) else "degraded"
    return ReadinessResponse(status=status, dependencies=deps)

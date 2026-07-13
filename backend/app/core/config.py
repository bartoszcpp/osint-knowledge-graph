"""Application settings loaded from environment variables / .env."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central, typed configuration for the backend."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- General ----
    environment: str = "development"
    log_level: str = "INFO"

    # ---- API ----
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # ---- PostgreSQL ----
    postgres_user: str = "osint"
    postgres_password: str = "change_me_postgres"
    postgres_db: str = "osint"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # ---- Neo4j ----
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "change_me_neo4j"

    # ---- Redis ----
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0

    # ---- Celery ----
    celery_broker_url: str = "amqp://osint:change_me_rabbit@rabbitmq:5672//"
    celery_result_backend: str = "redis://redis:6379/0"

    # ---- Data sources ----
    gdelt_enabled: bool = True
    hackernews_enabled: bool = True
    reddit_enabled: bool = False

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


settings = get_settings()

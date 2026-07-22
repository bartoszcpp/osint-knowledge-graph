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

    # ---- Data sources (feature flags) ----
    gdelt_enabled: bool = True
    hackernews_enabled: bool = True
    reddit_enabled: bool = False

    # ---- GDELT 2.0 ----
    # Base of the GDELT v2 update feed. `lastupdate.txt` lists the freshest
    # 15-minute export/mentions/GKG files.
    gdelt_base_url: str = "http://data.gdeltproject.org/gdeltv2"
    # Safety cap so a single 15-minute GKG file (can hold tens of thousands of
    # rows) never floods the pipeline in one run. Set 0 for "no limit".
    gdelt_gkg_max_records: int = 250

    # ---- Reddit API (PRAW) ----
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "osint-knowledge-graph/0.1"
    # Comma-separated list of subreddits to pull "hot" threads from.
    reddit_subreddits: str = "worldnews,business"
    reddit_hot_limit: int = 25

    # ---- Ingestion schedule (Celery Beat, minutes) ----
    ingest_gdelt_interval_minutes: int = 15
    ingest_reddit_interval_minutes: int = 15

    # ---- NLP / NER (Phase 3) ----
    nlp_enabled: bool = True
    # spaCy model. Start with the fast `en_core_web_sm`; swap for the more
    # accurate transformer `en_core_web_trf` later without code changes.
    spacy_model: str = "en_core_web_sm"
    # Dedicated Celery queue for CPU-heavy NLP work.
    nlp_queue_name: str = "nlp_tasks"
    # Co-occurrence granularity for relation detection: "sentence" or "paragraph".
    nlp_cooccurrence_scope: str = "sentence"
    # How many unprocessed articles the dispatcher enqueues per run.
    nlp_dispatch_batch_size: int = 100
    # How often Celery Beat scans Postgres for unprocessed articles (minutes).
    nlp_dispatch_interval_minutes: int = 5

    # ---- Knowledge graph sync (Phase 4) ----
    graph_sync_enabled: bool = True
    # Articles pushed to Neo4j per batch. UNWIND writes the whole batch in one
    # transaction instead of thousands of tiny queries.
    graph_sync_batch_size: int = 100
    # How often Celery Beat flushes analyzed-but-not-graphed articles to Neo4j.
    graph_sync_interval_minutes: int = 5

    # ---- Graph API (Phase 5) ----
    # Default time window (hours) for the "trending entities" endpoint.
    api_entities_window_hours: int = 24
    # Neighbor fan-out limits for the ego-graph endpoint.
    graph_default_neighbor_limit: int = 25
    graph_max_neighbor_limit: int = 200
    # Default pagination page size and hard cap.
    api_default_page_size: int = 50
    api_max_page_size: int = 200

    # ---- Redis cache (Phase 5) ----
    cache_enabled: bool = True
    # TTL for cached graph queries (seconds). Graph reads are expensive, so we
    # cache the hottest ones for a few minutes.
    cache_ttl_seconds: int = 300
    cache_key_prefix: str = "osint:cache"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]

    @property
    def reddit_subreddit_list(self) -> list[str]:
        return [s.strip() for s in self.reddit_subreddits.split(",") if s.strip()]

    @property
    def reddit_configured(self) -> bool:
        """True when the minimum OAuth credentials for PRAW are present."""
        return bool(self.reddit_client_id and self.reddit_client_secret)

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

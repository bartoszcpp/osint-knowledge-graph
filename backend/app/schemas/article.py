"""Unified article schema.

Every ingestion source (GDELT, Reddit, HackerNews, ...) maps its native payload
onto this single :class:`Article` model so that everything downstream - Postgres
storage, NLP, the knowledge graph - only ever deals with one shape.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator


class SourceType(StrEnum):
    """Where an article originated. Values are stored verbatim in Postgres."""

    GDELT = "gdelt"
    REDDIT = "reddit"
    HACKERNEWS = "hackernews"


def article_id(source: SourceType | str, url: str) -> str:
    """Deterministic content-addressable id for an article.

    Using ``sha256(source|url)`` means re-fetching the same document (which
    happens constantly with 15-minute GDELT windows) always produces the same
    id, so ``ON CONFLICT`` de-duplication in Postgres is trivial and stable.
    """
    source_value = source.value if isinstance(source, SourceType) else str(source)
    digest = hashlib.sha256(f"{source_value}|{url}".encode()).hexdigest()
    return f"{source_value}:{digest[:32]}"


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class Article(BaseModel):
    """Source-agnostic representation of a single news item / post."""

    id: str
    source: SourceType
    url: str
    title: str | None = None
    text_content: str | None = None
    published_at: datetime

    # Provenance / source-specific extras kept for later NLP + auditing.
    raw: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=_utcnow)

    @field_validator("published_at", "fetched_at")
    @classmethod
    def _ensure_tz_aware(cls, value: datetime) -> datetime:
        """Normalize naive datetimes to UTC so storage is unambiguous."""
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @classmethod
    def from_source(
        cls,
        *,
        source: SourceType | str,
        url: str,
        published_at: datetime,
        title: str | None = None,
        text_content: str | None = None,
        raw: dict[str, Any] | None = None,
    ) -> Article:
        """Build an :class:`Article`, deriving the deterministic id from the url."""
        source_enum = source if isinstance(source, SourceType) else SourceType(source)
        # Validate the url shape early; keep the plain string for storage.
        HttpUrl(url)
        return cls(
            id=article_id(source_enum, url),
            source=source_enum,
            url=url,
            title=title.strip() if title else None,
            text_content=text_content.strip() if text_content else None,
            published_at=published_at,
            raw=raw or {},
        )

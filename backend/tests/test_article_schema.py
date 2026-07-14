"""Tests for the unified Article schema."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.schemas.article import Article, SourceType, article_id


def test_article_id_is_deterministic():
    url = "https://example.com/news/story"
    assert article_id(SourceType.GDELT, url) == article_id("gdelt", url)


def test_article_id_differs_by_source_and_url():
    assert article_id(SourceType.GDELT, "https://a.com") != article_id(
        SourceType.REDDIT, "https://a.com"
    )
    assert article_id(SourceType.GDELT, "https://a.com") != article_id(
        SourceType.GDELT, "https://b.com"
    )


def test_from_source_sets_id_and_strips_text():
    article = Article.from_source(
        source="reddit",
        url="https://www.reddit.com/r/worldnews/comments/x/y/",
        published_at=datetime(2026, 7, 14, 10, 0, tzinfo=UTC),
        title="  Big News  ",
        text_content="  body  ",
    )
    assert article.source is SourceType.REDDIT
    assert article.id.startswith("reddit:")
    assert article.title == "Big News"
    assert article.text_content == "body"


def test_naive_datetime_is_made_utc_aware():
    article = Article.from_source(
        source=SourceType.GDELT,
        url="https://example.com/a",
        published_at=datetime(2026, 1, 1, 0, 0),
    )
    assert article.published_at.tzinfo is not None
    assert article.published_at.utcoffset() == UTC.utcoffset(None)


def test_invalid_url_rejected():
    with pytest.raises(ValueError):
        Article.from_source(
            source=SourceType.GDELT,
            url="not-a-url",
            published_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

"""Tests for Reddit submission -> Article mapping (offline, no PRAW/network)."""

from __future__ import annotations

from datetime import UTC
from types import SimpleNamespace

from app.ingestion.reddit import map_submission
from app.schemas.article import SourceType


def _submission(**overrides):
    base = {
        "id": "abc123",
        "permalink": "/r/worldnews/comments/abc123/some_title/",
        "created_utc": 1_768_000_000.0,
        "title": "Some Title",
        "selftext": "Body text",
        "subreddit": "worldnews",
        "author": "someuser",
        "score": 4200,
        "num_comments": 321,
        "upvote_ratio": 0.95,
        "over_18": False,
        "stickied": False,
        "url": "https://external.example.com/article",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_map_submission_basic_fields():
    article = map_submission(_submission(), "worldnews")

    assert article.source is SourceType.REDDIT
    assert article.url == "https://www.reddit.com/r/worldnews/comments/abc123/some_title/"
    assert article.title == "Some Title"
    assert article.text_content == "Body text"
    assert article.published_at.tzinfo == UTC
    assert article.raw["reddit_id"] == "abc123"
    assert article.raw["subreddit"] == "worldnews"
    assert article.raw["author"] == "someuser"
    assert article.raw["score"] == 4200
    assert article.raw["external_url"] == "https://external.example.com/article"


def test_map_submission_link_post_has_no_body():
    article = map_submission(_submission(selftext=""), "business")
    assert article.text_content is None


def test_map_submission_handles_missing_author():
    article = map_submission(_submission(author=None), "worldnews")
    assert article.raw["author"] is None

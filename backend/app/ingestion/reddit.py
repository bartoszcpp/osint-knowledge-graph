"""Reddit ingestion via PRAW.

Pulls the "hot" threads from the configured subreddits (default: r/worldnews and
r/business) and maps each submission onto the unified :class:`Article` model.

PRAW is imported lazily inside :func:`fetch_hot_articles` so that the pure mapping
logic (and its tests) don't require the dependency or network access.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.article import Article, SourceType

logger = get_logger(__name__)


def map_submission(submission: Any, subreddit: str) -> Article:
    """Map a PRAW submission (or any object exposing the same attrs) to Article.

    We treat the Reddit *thread* itself as the canonical document, so the
    permalink is the article url. ``selftext`` becomes the body for text posts;
    link posts keep their outbound target in ``raw['external_url']``.
    """
    permalink = getattr(submission, "permalink", "")
    url = f"https://www.reddit.com{permalink}" if permalink.startswith("/") else permalink

    created_utc = float(getattr(submission, "created_utc", 0.0))
    published_at = datetime.fromtimestamp(created_utc, tz=UTC)

    author = getattr(submission, "author", None)
    selftext = getattr(submission, "selftext", "") or None

    raw = {
        "reddit_id": getattr(submission, "id", None),
        "subreddit": str(getattr(submission, "subreddit", subreddit)),
        "author": str(author) if author else None,
        "score": getattr(submission, "score", None),
        "num_comments": getattr(submission, "num_comments", None),
        "upvote_ratio": getattr(submission, "upvote_ratio", None),
        "over_18": getattr(submission, "over_18", None),
        "permalink": permalink,
        "external_url": getattr(submission, "url", None),
    }

    return Article.from_source(
        source=SourceType.REDDIT,
        url=url,
        published_at=published_at,
        title=getattr(submission, "title", None),
        text_content=selftext,
        raw=raw,
    )


def _build_client():
    """Create a read-only PRAW Reddit client from settings."""
    import praw  # local import: optional at runtime, absent in unit tests

    return praw.Reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent,
        check_for_updates=False,
    )


def fetch_hot_articles(
    subreddits: list[str] | None = None,
    limit: int | None = None,
) -> list[Article]:
    """Fetch hot threads from the configured subreddits and map to Articles."""
    if not settings.reddit_configured:
        logger.warning("Reddit credentials not configured - skipping Reddit ingestion")
        return []

    subs = subreddits or settings.reddit_subreddit_list
    hot_limit = settings.reddit_hot_limit if limit is None else limit

    reddit = _build_client()
    reddit.read_only = True

    articles: list[Article] = []
    for name in subs:
        try:
            for submission in reddit.subreddit(name).hot(limit=hot_limit):
                if getattr(submission, "stickied", False):
                    continue  # skip pinned mod/meta posts
                articles.append(map_submission(submission, name))
        except Exception:
            logger.exception("Failed to fetch hot threads from r/%s", name)

    logger.info("Fetched %d Reddit thread(s) from %s", len(articles), ", ".join(subs))
    return articles

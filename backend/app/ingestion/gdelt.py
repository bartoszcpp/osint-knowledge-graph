"""GDELT 2.0 ingestion.

GDELT publishes a fresh batch of files every 15 minutes. ``lastupdate.txt`` lists
the three newest files (Events "export", "mentions", and the GKG). We consume the
**GKG (Global Knowledge Graph)** file because it is document-centric: one row per
news article, carrying the source URL, publication timestamp, and pre-extracted
people/organizations/themes - exactly what an OSINT graph wants.

Note: the raw GKG file does not contain the article title or body. We derive a
best-effort title from the URL slug and keep the extracted entity metadata in
``Article.raw`` for the NLP stage; full-text fetching happens later (Phase 3).
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from urllib.parse import unquote, urlparse

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.article import Article, SourceType

logger = get_logger(__name__)

# Tab-separated GKG 2.1 column indices (subset we care about).
_COL_DATE = 1  # V2.1DATE      -> YYYYMMDDHHMMSS
_COL_DOMAIN = 3  # V2SourceCommonName
_COL_URL = 4  # V2DocumentIdentifier
_COL_PERSONS = 11  # V1Persons  (';'-separated)
_COL_ORGS = 13  # V1Organizations (';'-separated)
_COL_TONE = 15  # V1.5Tone (comma-separated, first value = average tone)
_MIN_COLS = _COL_URL + 1

_HTTP_TIMEOUT = httpx.Timeout(60.0, connect=15.0)


def _parse_gkg_datetime(raw: str) -> datetime:
    """Parse a GKG ``YYYYMMDDHHMMSS`` stamp into an aware UTC datetime."""
    return datetime.strptime(raw.strip(), "%Y%m%d%H%M%S").replace(tzinfo=UTC)


def _title_from_url(url: str) -> str | None:
    """Best-effort human title from a URL slug (GKG has no real title field)."""
    path = urlparse(url).path.rstrip("/")
    slug = path.rsplit("/", 1)[-1] if path else ""
    slug = slug.rsplit(".", 1)[0]  # drop extension like .html
    slug = unquote(slug).replace("-", " ").replace("_", " ").strip()
    if not slug or slug.isdigit():
        return None
    return slug.title()


def _split_list(field: str) -> list[str]:
    """Split a GKG ';'-separated list, stripping the trailing offset tokens."""
    items: list[str] = []
    for chunk in field.split(";"):
        name = chunk.split(",", 1)[0].strip()
        if name:
            items.append(name)
    # Preserve order but drop duplicates.
    seen: set[str] = set()
    return [n for n in items if not (n in seen or seen.add(n))]


def parse_gkg(content: str, max_records: int = 0) -> list[Article]:
    """Map the tab-separated GKG file body to a list of :class:`Article`.

    Pure function (no I/O) so it is trivially unit-testable.
    ``max_records=0`` means "no limit".
    """
    articles: list[Article] = []
    seen_ids: set[str] = set()

    for line in content.splitlines():
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) < _MIN_COLS:
            continue

        url = cols[_COL_URL].strip()
        if not url.startswith("http"):
            continue

        try:
            published_at = _parse_gkg_datetime(cols[_COL_DATE])
        except ValueError:
            continue

        raw = {
            "domain": cols[_COL_DOMAIN].strip() if len(cols) > _COL_DOMAIN else None,
            "persons": _split_list(cols[_COL_PERSONS]) if len(cols) > _COL_PERSONS else [],
            "organizations": _split_list(cols[_COL_ORGS]) if len(cols) > _COL_ORGS else [],
            "tone": (
                cols[_COL_TONE].split(",", 1)[0].strip()
                if len(cols) > _COL_TONE and cols[_COL_TONE]
                else None
            ),
        }

        try:
            article = Article.from_source(
                source=SourceType.GDELT,
                url=url,
                published_at=published_at,
                title=_title_from_url(url),
                raw=raw,
            )
        except ValueError:
            # Invalid URL shape - skip rather than fail the whole batch.
            continue

        if article.id in seen_ids:
            continue
        seen_ids.add(article.id)
        articles.append(article)

        if max_records and len(articles) >= max_records:
            break

    return articles


def _resolve_latest_gkg_url(client: httpx.Client) -> str | None:
    """Read ``lastupdate.txt`` and return the newest GKG ``.csv.zip`` URL."""
    resp = client.get(f"{settings.gdelt_base_url}/lastupdate.txt")
    resp.raise_for_status()
    for line in resp.text.splitlines():
        parts = line.split()
        if not parts:
            continue
        file_url = parts[-1]
        if file_url.endswith(".gkg.csv.zip"):
            return file_url
    return None


def _download_and_extract(client: httpx.Client, zip_url: str) -> str:
    """Download the GKG zip and return the decoded CSV body of its first entry."""
    resp = client.get(zip_url)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        name = zf.namelist()[0]
        return zf.read(name).decode("utf-8", errors="replace")


def fetch_latest_articles(max_records: int | None = None) -> list[Article]:
    """Fetch and map the most recent GDELT 2.0 GKG batch to Articles."""
    limit = settings.gdelt_gkg_max_records if max_records is None else max_records
    with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        zip_url = _resolve_latest_gkg_url(client)
        if not zip_url:
            logger.warning("No GKG file found in GDELT lastupdate.txt")
            return []
        logger.info("Downloading GDELT GKG file: %s", zip_url)
        body = _download_and_extract(client, zip_url)

    articles = parse_gkg(body, max_records=limit)
    logger.info("Parsed %d article(s) from GDELT GKG (limit=%d)", len(articles), limit)
    return articles

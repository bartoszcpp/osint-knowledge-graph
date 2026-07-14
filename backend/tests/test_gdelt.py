"""Tests for GDELT GKG parsing (pure, offline)."""

from __future__ import annotations

from app.ingestion.gdelt import _title_from_url, parse_gkg
from app.schemas.article import SourceType


def _gkg_row(date: str, domain: str, url: str, persons: str = "", orgs: str = "") -> str:
    """Build a minimal tab-separated GKG 2.1 row (columns 0..15)."""
    cols = [""] * 16
    cols[0] = "20260714103000-1"
    cols[1] = date
    cols[3] = domain
    cols[4] = url
    cols[11] = persons
    cols[13] = orgs
    cols[15] = "1.5,2.0,0.5,0"
    return "\t".join(cols)


def test_parse_gkg_maps_rows_to_articles():
    body = "\n".join(
        [
            _gkg_row(
                "20260714103000",
                "bbc.com",
                "https://www.bbc.com/news/world-europe-12345",
                persons="joe biden,10;vladimir putin,55",
                orgs="nato,3;european union,20",
            ),
            _gkg_row("20260714103000", "cnn.com", "https://cnn.com/2026/07/14/politics/story"),
        ]
    )

    articles = parse_gkg(body)

    assert len(articles) == 2
    first = articles[0]
    assert first.source is SourceType.GDELT
    assert first.url == "https://www.bbc.com/news/world-europe-12345"
    assert first.published_at.year == 2026
    assert first.raw["domain"] == "bbc.com"
    assert first.raw["persons"] == ["joe biden", "vladimir putin"]
    assert first.raw["organizations"] == ["nato", "european union"]
    assert first.raw["tone"] == "1.5"


def test_parse_gkg_skips_non_http_and_short_rows():
    body = "\n".join(
        [
            _gkg_row("20260714103000", "x.com", "not-a-real-url"),
            "too\tshort",
            _gkg_row("badstamp", "x.com", "https://x.com/a"),
            _gkg_row("20260714103000", "ok.com", "https://ok.com/valid-story"),
        ]
    )
    articles = parse_gkg(body)
    assert len(articles) == 1
    assert articles[0].url == "https://ok.com/valid-story"


def test_parse_gkg_dedupes_and_respects_limit():
    dup = _gkg_row("20260714103000", "ok.com", "https://ok.com/same")
    body = "\n".join([dup, dup, _gkg_row("20260714103000", "ok.com", "https://ok.com/other")])

    assert len(parse_gkg(body)) == 2  # duplicate collapsed
    assert len(parse_gkg(body, max_records=1)) == 1


def test_title_from_url():
    assert _title_from_url("https://bbc.com/news/some-big-story.html") == "Some Big Story"
    assert _title_from_url("https://bbc.com/12345") is None

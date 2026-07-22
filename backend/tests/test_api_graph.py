"""Tests for the Phase 5 graph API (reader + cache mocked, no Neo4j/Redis)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.core import cache
from app.graph import reader
from app.main import create_app
from app.schemas.api import (
    ArticleSummary,
    EgoGraph,
    EntitySummary,
    GraphEdge,
    GraphNode,
    PaginatedArticles,
    PaginatedEntities,
)
from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable

client = TestClient(create_app())


@pytest.fixture(autouse=True)
def _bypass_cache(monkeypatch):
    """Disable Redis so tests exercise the reader path deterministically."""
    monkeypatch.setattr(cache, "get_json", lambda key: None)
    monkeypatch.setattr(cache, "set_json", lambda key, value, ttl=None: None)


def test_list_entities(monkeypatch):
    captured = {}

    def fake_top_entities(window_hours, limit, offset, entity_type=None):
        captured.update(
            window_hours=window_hours, limit=limit, offset=offset, entity_type=entity_type
        )
        return PaginatedEntities(
            items=[
                EntitySummary(
                    canonical_id="person:elon-musk",
                    name="Elon Musk",
                    type="PERSON",
                    article_count=12,
                    mention_count=30,
                )
            ],
            total=1,
            limit=limit,
            offset=offset,
            window_hours=window_hours,
        )

    monkeypatch.setattr(reader, "top_entities", fake_top_entities)

    resp = client.get("/entities", params={"window_hours": 48, "limit": 10, "type": "PERSON"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["canonical_id"] == "person:elon-musk"
    assert captured == {"window_hours": 48, "limit": 10, "offset": 0, "entity_type": "PERSON"}


def test_list_entities_rejects_oversized_limit():
    resp = client.get("/entities", params={"limit": 100000})
    assert resp.status_code == 422


def test_ego_graph_found(monkeypatch):
    def fake_ego(center_id, depth, neighbor_limit, min_weight, window_days=None):
        return EgoGraph(
            center=center_id,
            depth=depth,
            nodes=[
                GraphNode(id=center_id, name="Elon Musk", type="PERSON"),
                GraphNode(id="org:tesla", name="Tesla", type="ORG"),
            ],
            edges=[GraphEdge(source="org:tesla", target=center_id, weight=5)],
        )

    monkeypatch.setattr(reader, "ego_graph", fake_ego)

    resp = client.get("/graph/person:elon-musk", params={"depth": 2, "window_days": 7})
    assert resp.status_code == 200
    body = resp.json()
    assert body["center"] == "person:elon-musk"
    assert body["depth"] == 2
    assert len(body["nodes"]) == 2
    assert body["edges"][0]["weight"] == 5


def test_ego_graph_not_found(monkeypatch):
    monkeypatch.setattr(reader, "ego_graph", lambda *a, **k: None)
    resp = client.get("/graph/person:nobody")
    assert resp.status_code == 404


def test_ego_graph_depth_out_of_range():
    resp = client.get("/graph/person:elon-musk", params={"depth": 3})
    assert resp.status_code == 422


def test_connecting_articles(monkeypatch):
    def fake_articles(source_id, target_id, limit, offset, window_days=None):
        return PaginatedArticles(
            items=[
                ArticleSummary(
                    article_id="gdelt:abc",
                    url="https://example.com/a",
                    title="Musk meets Macron",
                    published_at=datetime(2026, 7, 20, tzinfo=UTC),
                    source="gdelt",
                )
            ],
            total=1,
            limit=limit,
            offset=offset,
        )

    monkeypatch.setattr(reader, "connecting_articles", fake_articles)

    resp = client.get(
        "/articles",
        params={"source": "person:elon-musk", "target": "person:emmanuel-macron"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["url"] == "https://example.com/a"


def test_articles_requires_source_and_target():
    resp = client.get("/articles", params={"source": "person:elon-musk"})
    assert resp.status_code == 422


def test_graph_db_unavailable_returns_503(monkeypatch):
    def boom(*a, **k):
        raise ServiceUnavailable("down")

    monkeypatch.setattr(reader, "top_entities", boom)
    resp = client.get("/entities")
    assert resp.status_code == 503


def test_cache_hit_short_circuits_reader(monkeypatch):
    cached_payload = {
        "items": [],
        "total": 7,
        "limit": 50,
        "offset": 0,
        "window_hours": 24,
    }
    monkeypatch.setattr(cache, "get_json", lambda key: cached_payload)

    def fail(*a, **k):
        raise AssertionError("reader should not be called on cache hit")

    monkeypatch.setattr(reader, "top_entities", fail)

    resp = client.get("/entities")
    assert resp.status_code == 200
    assert resp.json()["total"] == 7

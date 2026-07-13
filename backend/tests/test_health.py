"""Tests for the health endpoints."""

from __future__ import annotations

from app.main import create_app
from fastapi.testclient import TestClient

client = TestClient(create_app())


def test_healthcheck_ok():
    resp = client.get("/healthcheck")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["service"] == "osint-knowledge-graph"

"""Tests for api.bainluck.com /robots.txt (#13350, held for Decision 327)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_robots_txt_disallows_crawlers_on_api_origin():
    from app.main import app

    client = TestClient(app)
    resp = client.get("/robots.txt")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert resp.headers["cache-control"] == "public, max-age=86400"
    assert resp.text == "User-agent: *\nDisallow: /\n"

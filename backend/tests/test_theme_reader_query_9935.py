"""Theme pagination must not reject existing sports hub HTTP requests (#9935)."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import containers as route


@pytest.fixture
def client(monkeypatch):
    async def db():
        yield object()

    async def published(_db, slug, **kwargs):
        return SimpleNamespace(state=route.READ_PUBLISHED, slug=slug, revision=7,
                               reason=None, container_id=1, members=[])

    async def sports_payload(*args):
        return {"state": "published", "revision": 7, "sections": []}

    monkeypatch.setattr(route, "containers_read_enabled", lambda: True)
    monkeypatch.setattr(route, "container_read_cache_enabled", lambda: False)
    monkeypatch.setattr(route, "read_published", published)
    monkeypatch.setattr(route, "_build_published_payload", sports_payload)
    app = FastAPI()
    app.include_router(route.router, prefix="/api/containers")
    app.dependency_overrides[route.get_db] = db
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("param,value", [("revision", "1" * 13), ("cursor", "a" * 65),
                                         ("limit", "1" * 5)])
def test_sports_hub_ignores_theme_query_lengths_at_http_boundary(client, param, value):
    url = "/api/containers/nfl-2026-week-5"
    baseline = client.get(url)
    response = client.get(url, params={param: value})
    assert baseline.status_code == response.status_code == 200
    assert response.json() == baseline.json()


@pytest.mark.parametrize("param,value", [("revision", "1" * 13), ("cursor", "a" * 65),
                                         ("limit", "1" * 5)])
def test_theme_query_lengths_remain_bounded(client, param, value):
    response = client.get("/api/containers/ai", params={param: value})
    assert response.status_code == 422
    assert response.json()["detail"] == {"reason": f"invalid_{param}"}

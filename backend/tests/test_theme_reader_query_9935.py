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


@pytest.mark.asyncio
async def test_9936_a_settled_member_without_a_time_hydrates_with_its_stored_grade(monkeypatch):
    """#9936 C: the retained member reaches the reader as any member does — the
    hydration loads by id with no status or time filter and prints the stored
    graded legs. Nothing here writes a result; the grade is the row's own."""
    from app.models import FuturesMarket, FuturesOutcome
    from app.routes import futures as futures_route

    market = FuturesMarket(
        id=61461524, source="kalshi", external_id="KXCLAUDE-CLAUDE6",
        name="Claude 6 released before 2027?", status="resolved", settled_at=None,
        category="tech", llm_sport_category="tech", market_tier=2,
    )
    market.sport = None
    market.outcomes = [
        FuturesOutcome(id=1, market_id=market.id, name="Yes", is_winner=True,
                       resolution_source="kalshi", current_probability=1.0),
        FuturesOutcome(id=2, market_id=market.id, name="No", is_winner=False,
                       resolution_source="kalshi", current_probability=0.0),
    ]

    class _Rows:
        def scalars(self):
            return self

        def all(self):
            return [market]

    class _DB:
        async def execute(self, stmt):
            return _Rows()

    async def nothing_withheld(_db, markets):
        return {}

    monkeypatch.setattr(futures_route, "withheld_price_outcome_ids_for_markets", nothing_withheld)
    cards, _events, failed = await route._hydrate_market_cards(_DB(), [market.id])

    assert failed == {}
    card = cards[market.id]
    assert card["status"] == "resolved"
    graded = {o["name"]: (o["is_winner"], o["resolution_source"]) for o in card["top_outcomes"]}
    assert graded.get("Yes") == (True, "kalshi")

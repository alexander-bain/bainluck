"""Real HTTP entry routes keep public contracts and fail closed publication."""

import copy
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import container_discovery as producer
from app.utils import request_cache as cache
from app.utils.feed_cache import FEED_RESPONSE_CACHE_PREFIX


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("CONTAINER_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")


@pytest.fixture
def card():
    path = (
        Path(__file__).parents[1]
        / "fixtures/container_discovery_9653/search_by_games.json"
    )
    return json.loads(path.read_text())["response"]["collections"][0]


async def test_browse_static_route_returns_only_producer_cards(
    client, monkeypatch, enabled, card
):
    read = AsyncMock(
        return_value=SimpleNamespace(
            collections=[card], reason="internal", excluded={"private": 1}, truncated={}
        )
    )
    monkeypatch.setattr(producer, "discover_collections", read)
    response = await client.get(
        "/api/containers/discover?league=nfl&season=2026&limit=20"
    )
    assert response.status_code == 200  # static route, not slug='discover'
    assert response.json() == {"collections": [card]}
    assert read.await_args.kwargs == {"league": "nfl", "season": 2026, "limit": 20}


@pytest.mark.parametrize(
    "change,offered",
    [
        ({}, True),
        ({"publication_state": "unpublished"}, False),
        ({"publication_state": "withdrawn"}, False),
        ({"publication_state": "unknown"}, False),
        ({"slug": "nfl-2025-week-5"}, False),
        ({"slug": "mlb-2026-postseason"}, False),
        ({"parent_container_id": 12}, False),
        ({"game_count": 0, "question_count": 0}, False),
    ],
)
async def test_browse_http_enforces_publication_and_edition(
    client, mock_db, enabled, card, change, offered
):
    values = {**card, "parent_container_id": None, "publication_state": "published"}
    values["matched_event_ids"] = []  # Browse has no event relevance filter.
    for key in ("window_start", "window_end"):
        values[key] = datetime.fromisoformat(values[key])
    values.update(change)
    row = tuple(values[key] for key in producer._COLUMNS)

    async def execute(sql, params=None):
        if "to_regclass" in str(sql):
            return SimpleNamespace(fetchone=lambda: (True, True))
        assert str(sql).startswith("WITH hub AS")
        return SimpleNamespace(fetchall=lambda: [row])

    mock_db.execute.side_effect = execute
    response = await client.get("/api/containers/discover?league=nfl&season=2026")
    assert response.status_code == 200
    assert set(response.json()) == {"collections"}
    assert len(response.json()["collections"]) == int(offered)
    assert mock_db.execute.await_count == 2
    if offered:
        assert response.json()["collections"][0] == {**card, "matched_event_ids": []}


@pytest.mark.parametrize("query", ["league=nba", "limit=21", "limit=0", "season=bogus"])
async def test_browse_rejects_invalid_filters(client, monkeypatch, query):
    read = AsyncMock()
    monkeypatch.setattr(producer, "discover_collections", read)
    response = await client.get("/api/containers/discover?" + query)
    assert response.status_code == 422
    read.assert_not_awaited()


@pytest.mark.parametrize(
    "flag", ["CONTAINER_DISCOVERY_ENABLED", "CONTAINERS_READ_ENABLED"]
)
async def test_browse_off_returns_empty_without_reading_database(
    client, mock_db, monkeypatch, enabled, flag
):
    monkeypatch.setenv(flag, "false")
    response = await client.get("/api/containers/discover?league=mlb&season=2026")
    assert response.status_code == 200
    assert response.json() == {"collections": []}
    mock_db.execute.assert_not_awaited()


@pytest.fixture
def ordinary_deck(monkeypatch):
    from app.routes import feed

    cards = [
        {
            "type": "event",
            "score": 80 - i,
            "_rank_score": 80 - i,
            "_sort_time": 1,
            "reason": "Game",
            "headline": None,
            "data": {"id": 501 + i, "status": "scheduled"},
        }
        for i in range(25)
    ]
    monkeypatch.setattr(
        feed,
        "_score_events",
        AsyncMock(side_effect=lambda *a, **k: copy.deepcopy(cards)),
    )
    for name in (
        "enrich_event_team_data",
        "_apply_manual_review_decisions",
        "_attach_feed_venue_settlement",
    ):
        monkeypatch.setattr(feed, name, AsyncMock())
    monkeypatch.setattr(feed, "_score_golf_tournaments", AsyncMock(return_value=[]))
    monkeypatch.setattr(feed, "_score_event_concepts", AsyncMock(return_value=[]))
    # Supply a composed ordinary deck; exercise the real consumer + pagination,
    # scrubbing, edition and cache route boundaries instead of ranking fixtures.
    monkeypatch.setattr(
        feed, "apply_discover_display_chain", lambda items, **kw: (items, {})
    )
    cache._reset_last_good_for_tests()
    cache._reset_inflight_for_tests()
    return cards


class Redis:
    def __init__(self):
        self.keys = []

    async def mget(self, keys):
        return [await self.get(key) for key in keys]

    async def get(self, key):
        self.keys.append(key)
        # A previous public page must not substitute for a fresh publication.
        return json.dumps({"items": [], "total": 0, "has_more": False})

    async def setex(self, *args):
        return True


@pytest.mark.usefixtures("opening_seating_off")
async def test_discover_paginate_full_deck_and_recheck_revocation(
    client, monkeypatch, enabled, card, ordinary_deck
):
    read = AsyncMock(return_value=SimpleNamespace(collections=[card]))
    monkeypatch.setattr(producer, "discover_collections", read)
    redis = Redis()
    monkeypatch.setattr(cache, "get_shared_async_redis", AsyncMock(return_value=redis))
    pages = []
    editions = []
    for offset in (0, 10, 20):
        response = await client.get(
            f"/api/feed?limit=10&offset={offset}"
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 26
        assert len(body["items"]) == min(10, 26 - offset)
        pages.extend(body["items"])
        editions.append(body["edition"])
    assert len(set(editions)) == 1
    assert len(pages) == 26
    assert {item["data"]["id"] for item in pages if item["type"] == "event"} == set(
        range(501, 526)
    )
    collection = next(item for item in pages if item["type"] == "collection")
    assert collection["data"] == card
    assert not any(key.startswith("_") for item in pages for key in item)
    # Principal-independent scoring artifacts are still usable; public page
    # responses, stale mirrors and page bases must not be read. #10003: this
    # session double cannot answer the publication fingerprint, and a
    # collection-bearing page with no fingerprint is never served from cache.
    # (Discover shape — `include_futures=false` no longer offers collections.)
    assert redis.keys
    assert not any(key.startswith(FEED_RESPONSE_CACHE_PREFIX) for key in redis.keys), (
        redis.keys
    )
    assert list(read.await_args.kwargs["event_ids"]) == list(range(501, 521))

    read.return_value = SimpleNamespace(collections=[])
    withdrawn = await client.get("/api/feed?limit=10")
    assert withdrawn.json()["total"] == 25
    assert all(item["type"] != "collection" for item in withdrawn.json()["items"])


@pytest.mark.usefixtures("opening_seating_on")
async def test_seated_discover_paginates_a_deck_whose_collection_holds_no_live_games(
    client, monkeypatch, enabled, card, ordinary_deck
):
    """#5105: the authentic producer card, with a non-live hub status, is a
    supported seated deck — every page of one edition, the card intact."""
    scheduled_card = {**card, "status": "scheduled"}
    read = AsyncMock(return_value=SimpleNamespace(collections=[scheduled_card]))
    monkeypatch.setattr(producer, "discover_collections", read)
    monkeypatch.setattr(cache, "get_shared_async_redis", AsyncMock(return_value=Redis()))
    pages, editions = [], []
    for offset in (0, 10, 20):
        body = (await client.get(f"/api/feed?limit=10&offset={offset}")).json()
        assert body["total"] == 26, body.get("cache")
        pages.extend(body["items"])
        editions.append(body["edition"])
    assert len(set(editions)) == 1
    assert len(pages) == 26
    collection = next(item for item in pages if item["type"] == "collection")
    assert collection["data"] == scheduled_card


@pytest.mark.usefixtures("opening_seating_on")
async def test_seated_discover_paginates_the_unchanged_live_hub_of_scheduled_games(
    client, monkeypatch, enabled, card, ordinary_deck
):
    """#5105: the producer card exactly as published — ``state: published``,
    the hub's own ``status: live`` (an NFL week in progress) — over a deck whose
    represented games are all scheduled. The hub's status is its authority's
    lifecycle, not its games'; this deck was once refused whole as
    ``unavailable``/``opening_unsupported``. Every page, one edition."""
    assert card["state"] == "published" and card["status"] == "live"
    assert all(c["data"]["status"] == "scheduled" for c in ordinary_deck)
    published = copy.deepcopy(card)
    read = AsyncMock(return_value=SimpleNamespace(collections=[card]))
    monkeypatch.setattr(producer, "discover_collections", read)
    monkeypatch.setattr(cache, "get_shared_async_redis", AsyncMock(return_value=Redis()))
    pages, editions = [], []
    for offset in (0, 10, 20):
        response = await client.get(f"/api/feed?limit=10&offset={offset}")
        body = response.json()
        assert response.headers.get("x-feed-cache") != "unavailable", body.get("cache")
        assert body["total"] == 26, body.get("cache")
        pages.extend(body["items"])
        editions.append(body["edition"])
    assert len(set(editions)) == 1 and editions[0]
    assert len(pages) == 26
    assert len({(item["type"], item["data"]["id"]) for item in pages}) == 26
    collection = next(item for item in pages if item["type"] == "collection")
    assert collection["data"] == card == published


@pytest.mark.usefixtures("opening_seating_on")
@pytest.mark.parametrize("hub_status", ["live", "scheduled"])
@pytest.mark.parametrize(
    "live_id,matched",
    [(502, None), (519, [501, 519])],  # a member in the opening / past seat ten
)
async def test_seated_discover_seats_a_hub_naming_a_represented_live_game(
    client, monkeypatch, enabled, card, ordinary_deck, hub_status, live_id, matched
):
    """#5105 correction A: whatever the hub's own status, a matched member the
    deck carries as an ordinary live game no longer refuses the whole deck. The
    hub inherits the game's restriction and both leave the opening by the stable
    move: every page of one edition, all 26 cards once, the card intact, and
    neither the hub nor its live game laundered into the first ten."""
    hub = {**card, "status": hub_status}
    if matched is not None:
        hub["matched_event_ids"] = matched
    member = next(c for c in ordinary_deck if c["data"]["id"] == live_id)
    member["data"]["status"] = "live"
    published = copy.deepcopy(hub)
    read = AsyncMock(return_value=SimpleNamespace(collections=[hub]))
    monkeypatch.setattr(producer, "discover_collections", read)
    monkeypatch.setattr(cache, "get_shared_async_redis", AsyncMock(return_value=Redis()))
    pages, editions = [], []
    for offset in (0, 10, 20):
        response = await client.get(f"/api/feed?limit=10&offset={offset}")
        body = response.json()
        assert response.status_code == 200
        assert response.headers.get("x-feed-cache") != "unavailable", body.get("cache")
        assert body["total"] == 26, body.get("cache")
        pages.extend(body["items"])
        editions.append(body["edition"])
    assert len(set(editions)) == 1 and editions[0]
    keys = [(item["type"], item["data"]["id"]) for item in pages]
    assert len(set(keys)) == len(keys) == 26
    opening = keys[:10]
    assert all(kind == "event" for kind, _ in opening), opening
    assert ("event", live_id) not in opening, opening
    # The hub takes the first seat after the opening; its game is not moved
    # earlier than that (502 follows it, 519 keeps its own seat twenty).
    assert keys[10][0] == "collection", keys
    assert keys.index(("event", live_id)) == (11 if live_id == 502 else 19), keys
    assert pages[10]["data"] == hub == published


async def test_flag_off_preserves_cached_ordinary_response(
    client, monkeypatch, ordinary_deck
):
    monkeypatch.setenv("CONTAINER_DISCOVERY_ENABLED", "false")
    redis = Redis()
    monkeypatch.setattr(cache, "get_shared_async_redis", AsyncMock(return_value=redis))
    read = AsyncMock()
    monkeypatch.setattr(producer, "discover_collections", read)
    response = await client.get("/api/feed?include_futures=false&limit=10")
    assert response.status_code == 200
    assert response.headers["x-feed-cache"] == "hit"
    assert response.json()["items"] == []
    read.assert_not_awaited()

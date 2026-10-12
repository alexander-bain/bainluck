"""#9925 — the theme card's `collection_ref` through the real `GET /api/feed`.

SHIP: tap "View collection" on an eligible Discover theme and open its full
page. Pillars DISCOVER / TRUTH. These drive the real route through the ASGI app
(the #10003 route test's doubles) and pin what only the route can show:

1. The served theme bundle carries the ref the producer computed, alongside
   its unchanged preview members and preview count.
2. One publication state is served from cache, with no second read.
3. A revision bump or a withdrawal moves the cache key: a miss, a rebuild, and
   the new ref (or none). An old ref never outlives its revision.
4. Nothing published leaves the response key byte-identical and does no
   per-build read.
"""

import copy
from unittest.mock import AsyncMock

import pytest

from app.utils import feed_collections as consumer
from app.utils import request_cache as _rc
from app.utils import theme_collection_ref as tcr

AI_IDS = [61461524, 13791997, 5550001]
AI_CID = 10


def _bundle():
    return {
        "type": "bundle",
        "score": 90,
        "_rank_score": 90,
        "_sort_time": 1,
        "reason": "What happens next in AI?",
        "headline": "AI",
        "data": {
            "id": "theme:story:ai:" + "-".join(map(str, AI_IDS)),
            "title": "AI", "kind": "theme", "story_key": "story:ai",
            "shared_question": "What happens next in AI?",
            "item_count": len(AI_IDS), "member_ids": list(AI_IDS),
            "items": [{"type": "futures", "data": {"id": i}} for i in AI_IDS],
            "debug_bundles": {"grouped_by": "story_key", "member_ids": list(AI_IDS)},
        },
    }


@pytest.fixture
def deck(monkeypatch):
    """A composed deck holding one AI theme bundle among ordinary games."""
    from app.routes import feed

    cards = [_bundle()] + [
        {
            "type": "event", "score": 80 - i, "_rank_score": 80 - i, "_sort_time": 1,
            "reason": "Game", "headline": None,
            "data": {"id": 501 + i, "status": "scheduled"},
        }
        for i in range(12)
    ]
    monkeypatch.setattr(feed, "_DISCOVER_OPENING_SEATING_SERVED", False)
    monkeypatch.setattr(
        feed, "_score_events", AsyncMock(side_effect=lambda *a, **k: copy.deepcopy(cards))
    )
    for name in (
        "enrich_event_team_data",
        "_apply_manual_review_decisions",
        "_attach_feed_venue_settlement",
    ):
        monkeypatch.setattr(feed, name, AsyncMock())
    monkeypatch.setattr(feed, "_score_golf_tournaments", AsyncMock(return_value=[]))
    monkeypatch.setattr(feed, "_score_event_concepts", AsyncMock(return_value=[]))
    monkeypatch.setattr(feed, "apply_discover_display_chain", lambda items, **kw: (items, {}))
    return cards


class _DictRedis:
    def __init__(self):
        self.store: dict[str, str] = {}

    async def mget(self, keys):
        return [self.store.get(k) for k in keys]

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value
        return True


async def _async(value):
    return value


@pytest.fixture
def redis(monkeypatch):
    fake = _DictRedis()
    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _rc._reset_shared_client_for_tests()
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))
    scheduled: list = []
    monkeypatch.setattr(_rc, "schedule_background", scheduled.append)
    yield fake, scheduled
    for coro in scheduled:
        coro.close()


async def _drain(scheduled):
    while scheduled:
        await scheduled.pop(0)


@pytest.fixture
def world(monkeypatch):
    """The theme publication state, read three ways the route reaches it: the
    published read (cache key), the edge read and the page's snapshot."""
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_DISCOVERY_ENABLED", "false")
    state = {"pub": "published", "rev": 18, "shown": [*AI_IDS, 777, 778]}

    async def published(db, *, max_age_seconds=0.0):
        if state["pub"] != "published":
            return tcr.PublishedThemes()
        return tcr.PublishedThemes((tcr.PublishedTheme(AI_CID, "ai", state["rev"]),))

    async def rows(db, ids):
        return [
            tcr.CandidateRow(AI_CID, "ai", "AI", state["pub"], state["rev"], i)
            for i in ids if i in AI_IDS
        ]

    async def snap(cid, rev):
        if (cid, rev) != (AI_CID, state["rev"]):
            return None
        return {
            "container_id": cid, "slug": "ai", "name": "AI", "revision": rev,
            "inventory_complete": True, "shown_ids": state["shown"], "folded_ids": [],
            "withheld": {"row_missing": []}, "shown_count": len(state["shown"]),
            "eligible_count": len(state["shown"]),
        }

    read_published = AsyncMock(side_effect=published)
    read_rows = AsyncMock(side_effect=rows)
    monkeypatch.setattr(tcr, "read_published_themes", read_published)
    monkeypatch.setattr(tcr, "read_candidate_rows", read_rows)
    monkeypatch.setattr(tcr, "_hub_snapshot", snap)
    return state, read_published, read_rows


def _theme(body):
    (bundle,) = [i for i in body["items"] if i["type"] == "bundle"]
    return bundle["data"]


async def test_the_served_card_carries_the_ref_and_a_revision_bump_misses(
    client, deck, redis, world
):
    fake, scheduled = redis
    state, read_published, read_rows = world

    first = await client.get("/api/feed?limit=10")
    assert first.status_code == 200 and first.headers["x-feed-cache"] == "miss"
    data = _theme(first.json())
    assert data["collection_ref"] == {
        "slug": "ai", "name": "AI", "revision": 18, "collection_count": 5,
    }
    assert data["item_count"] == 3 and [m["data"]["id"] for m in data["items"]] == AI_IDS
    assert read_rows.await_count == 1
    await _drain(scheduled)

    # One publication state: served from cache, no second edge read.
    second = await client.get("/api/feed?limit=10")
    assert second.headers["x-feed-cache"] != "miss", second.headers["x-feed-cache"]
    assert _theme(second.json())["collection_ref"]["revision"] == 18
    assert read_rows.await_count == 1

    # An assembly/correction bump: the key moves, the page rebuilds, new ref.
    state["rev"], state["shown"] = 19, [*AI_IDS, 777]
    third = await client.get("/api/feed?limit=10")
    assert third.headers["x-feed-cache"] == "miss"
    assert _theme(third.json())["collection_ref"] == {
        "slug": "ai", "name": "AI", "revision": 19, "collection_count": 4,
    }
    await _drain(scheduled)

    # Withdrawn: a miss, and the card no longer links anywhere.
    state["pub"] = "withdrawn"
    fourth = await client.get("/api/feed?limit=10")
    assert fourth.headers["x-feed-cache"] == "miss"
    assert "collection_ref" not in _theme(fourth.json())
    assert read_published.await_count == 4


async def test_nothing_published_keeps_the_key_and_reads_nothing_per_build(
    client, deck, redis, world, monkeypatch
):
    state, _, read_rows = world
    state["pub"] = "unpublished"
    seen_keys = []
    from app.routes import feed

    real = feed.feed_response_cache_key

    def spy(**kwargs):
        seen_keys.append(kwargs.get("collections"))
        return real(**kwargs)

    monkeypatch.setattr(feed, "feed_response_cache_key", spy)
    body = (await client.get("/api/feed?limit=10")).json()
    assert "collection_ref" not in _theme(body)
    assert seen_keys and set(seen_keys) == {None}  # byte-identical to today's key
    read_rows.assert_not_awaited()


async def test_an_unreadable_publication_state_is_never_cached_and_never_links(
    client, deck, redis, monkeypatch
):
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setattr(tcr, "read_published_themes", AsyncMock(return_value=None))
    read_rows = AsyncMock()
    monkeypatch.setattr(tcr, "read_candidate_rows", read_rows)
    fake, scheduled = redis
    for _ in range(2):
        response = await client.get("/api/feed?limit=10")
        assert response.headers["x-feed-cache"] == "disabled"
        assert "collection_ref" not in _theme(response.json())
        await _drain(scheduled)
    read_rows.assert_not_awaited()
    assert not any(k.startswith("feed_cache:") for k in fake.store)

"""#10003 — a collection-bearing Discover page is cached under its publication state.

Turning the collection flags on (01:54Z 10/1) disabled every response, stale,
last-good and page-base cache for every Discover request and for the native
Sports tab's events-only backfill: 1.4–3.3 s of server time per open, against
a ~50 ms shared hit before. These tests drive the real route through the real
ASGI app and pin the three claims the fix makes:

1. Same publication state ⇒ the second open is served from cache and does not
   rebuild (the collection read is not repeated).
2. A changed publication state (here a withdrawal) ⇒ a miss, a rebuild, and
   the withdrawn hub is gone — revocation stays live authority.
3. An events-only request is not collection-eligible, so it keeps its cache
   and never pays the publication reads at all.

#5105: claims 1–2 and the unreadable-fingerprint rule are pinned on BOTH sides
of the seated-opening switch. The legacy tests set it OFF themselves. Under ON,
a supported (non-live) collection keeps all three guarantees; the original
fixture (``status: live``) is grouped-live input seating refuses, so ON must
answer it with a truthful ``unavailable`` and publish nothing reusable.
"""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import container_discovery as producer
from app.utils import feed_collections as consumer
from app.utils import request_cache as _rc


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("CONTAINER_DISCOVERY_ENABLED", "true")
    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")


@pytest.fixture
def unseated(monkeypatch):
    """#5105 served switch OFF: the legacy contract, stated, not inherited."""
    from app.routes import feed

    monkeypatch.setattr(feed, "_DISCOVER_OPENING_SEATING_SERVED", False)


@pytest.fixture
def seated(monkeypatch):
    """#5105 served switch ON, stated whatever the branch default is. Returns
    the route's seated compositions (deck types in, usable out), so a test
    proves the seated path ran rather than inferring it from a header."""
    from app.routes import feed

    monkeypatch.setattr(feed, "_DISCOVER_OPENING_SEATING_SERVED", True)
    real = feed.compose_opening_edition
    calls: list[tuple[list, bool]] = []

    def spy(items, *args, **kwargs):
        outcome = real(items, *args, **kwargs)
        calls.append(([item.get("type") for item in items], outcome.usable))
        return outcome

    monkeypatch.setattr(feed, "compose_opening_edition", spy)
    return calls


@pytest.fixture
def card():
    path = (
        Path(__file__).parent.parent
        / "fixtures/container_discovery_9653/search_by_games.json"
    )
    return json.loads(path.read_text())["response"]["collections"][0]


@pytest.fixture
def scheduled_card(card):
    """A SYNTHETIC copy of the 9653 hub that is not live — the collection
    shape seating supports. The shared fixture itself is left untouched."""
    synthetic = copy.deepcopy(card)
    assert synthetic["status"] == "live"
    synthetic["status"] = "scheduled"
    synthetic["name"] = synthetic["text"] = "SYNTHETIC #5105 scheduled hub"
    return synthetic


@pytest.fixture
def ordinary_deck(monkeypatch):
    """The 9653 route-boundary deck: a composed list of 25 games, real
    consumer, pagination, edition and cache boundaries."""
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
    monkeypatch.setattr(
        feed, "apply_discover_display_chain", lambda items, **kw: (items, {})
    )
    return cards


class _DictRedis:
    """A dict with a Redis face (the LAT-P141 route test's shape)."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.reads: list[str] = []

    async def mget(self, keys):
        return [await self.get(key) for key in keys]

    async def get(self, key):
        self.reads.append(key)
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


def _collections(body):
    return [item for item in body["items"] if item["type"] == "collection"]


async def test_one_publication_state_is_served_from_cache_and_a_withdrawal_misses(
    client, monkeypatch, enabled, unseated, card, ordinary_deck, redis
):
    fake, scheduled = redis
    state = {"fingerprint": "published-rev-1"}
    fingerprint = AsyncMock(
        side_effect=lambda db, *, max_age_seconds: state["fingerprint"]
    )
    monkeypatch.setattr(consumer, "feed_collections_cache_fingerprint", fingerprint)
    read = AsyncMock(return_value=SimpleNamespace(collections=[card]))
    monkeypatch.setattr(producer, "discover_collections", read)

    first = await client.get("/api/feed?limit=10")
    assert first.status_code == 200
    assert first.headers["x-feed-cache"] == "miss"
    assert [c["data"] for c in _collections(first.json())] == [card]
    assert read.await_count == 1
    await _drain(scheduled)
    assert any(key.startswith("feed_cache:") for key in fake.store), fake.store

    # Claim 1: same publication state — served from cache, no rebuild.
    second = await client.get("/api/feed?limit=10")
    assert second.status_code == 200
    assert second.headers["x-feed-cache"] != "miss", second.headers["x-feed-cache"]
    assert second.json()["items"] == first.json()["items"]
    assert read.await_count == 1, "a cached open must not re-read publication"

    # Claim 2: the hub is withdrawn — its revision moves, so the fingerprint
    # does, and the cached page (which still holds the hub) is unreachable.
    state["fingerprint"] = "withdrawn-rev-2"
    read.return_value = SimpleNamespace(collections=[])
    third = await client.get("/api/feed?limit=10")
    assert third.status_code == 200
    assert third.headers["x-feed-cache"] == "miss"
    assert _collections(third.json()) == []
    assert read.await_count == 2
    assert fingerprint.await_count == 3


async def test_an_unreadable_fingerprint_is_never_served_from_cache(
    client, monkeypatch, enabled, unseated, card, ordinary_deck, redis
):
    """``None`` = could not tell. The page is built fresh every time — the
    pre-#10003 behaviour, so a failed read costs speed, never truth."""
    fake, scheduled = redis
    monkeypatch.setattr(
        consumer, "feed_collections_cache_fingerprint", AsyncMock(return_value=None)
    )
    read = AsyncMock(return_value=SimpleNamespace(collections=[card]))
    monkeypatch.setattr(producer, "discover_collections", read)

    for _ in range(2):
        response = await client.get("/api/feed?limit=10")
        assert response.status_code == 200
        assert response.headers["x-feed-cache"] == "disabled"
        assert len(_collections(response.json())) == 1
        await _drain(scheduled)
    assert read.await_count == 2
    assert not any(key.startswith("feed_cache:") for key in fake.reads), fake.reads
    assert not any(key.startswith("feed_cache:") for key in fake.store), fake.store


async def test_the_sports_events_backfill_keeps_its_cache_and_skips_publication(
    client, monkeypatch, enabled, ordinary_deck, redis
):
    """The native Sports tab's ``limit=200&include_futures=false`` backfill
    renders no collection card on any client; it was a 33 ms shared hit until
    the flags made it a 0.6–3.3 s cold build on every open."""
    fake, scheduled = redis
    fingerprint = AsyncMock(return_value="published-rev-1")
    monkeypatch.setattr(consumer, "feed_collections_cache_fingerprint", fingerprint)
    read = AsyncMock()
    monkeypatch.setattr(producer, "discover_collections", read)

    url = "/api/feed?limit=200&offset=0&include_futures=false"
    first = await client.get(url)
    assert first.status_code == 200
    assert first.headers["x-feed-cache"] == "miss"
    await _drain(scheduled)
    second = await client.get(url)
    assert second.headers["x-feed-cache"] != "miss"
    assert second.json()["items"] == first.json()["items"]
    read.assert_not_awaited()
    fingerprint.assert_not_awaited()


# ---------------------------------------------------------------------------
# #5105 — the same guarantees with the seated opening ON
# ---------------------------------------------------------------------------


async def test_seated_a_supported_collection_reuses_one_publication_and_a_withdrawal_misses(
    client, monkeypatch, enabled, seated, scheduled_card, ordinary_deck, redis
):
    fake, scheduled = redis
    state = {"fingerprint": "published-rev-1"}
    fingerprint = AsyncMock(
        side_effect=lambda db, *, max_age_seconds: state["fingerprint"]
    )
    monkeypatch.setattr(consumer, "feed_collections_cache_fingerprint", fingerprint)
    read = AsyncMock(return_value=SimpleNamespace(collections=[scheduled_card]))
    monkeypatch.setattr(producer, "discover_collections", read)

    first = await client.get("/api/feed?limit=10")
    assert first.status_code == 200
    assert first.headers["x-feed-cache"] == "miss"
    assert [c["data"] for c in _collections(first.json())] == [scheduled_card]
    assert read.await_count == 1
    assert [usable for _, usable in seated] == [True]
    assert "collection" in seated[0][0], "the seated deck carried the hub"
    await _drain(scheduled)
    assert any(key.startswith("feed_cache:") for key in fake.store), fake.store

    second = await client.get("/api/feed?limit=10")
    assert second.status_code == 200
    assert second.headers["x-feed-cache"] != "miss", second.headers["x-feed-cache"]
    assert second.json()["items"] == first.json()["items"]
    assert read.await_count == 1, "a cached seated open must not re-read publication"

    state["fingerprint"] = "withdrawn-rev-2"
    read.return_value = SimpleNamespace(collections=[])
    third = await client.get("/api/feed?limit=10")
    assert third.status_code == 200
    assert third.headers["x-feed-cache"] == "miss"
    assert _collections(third.json()) == []
    assert third.json()["items"], "the withdrawal leaves the games, not a blank page"
    assert read.await_count == 2
    assert fingerprint.await_count == 3
    assert "collection" not in seated[-1][0] and seated[-1][1] is True


async def test_seated_an_unreadable_fingerprint_builds_fresh_and_caches_nothing(
    client, monkeypatch, enabled, seated, scheduled_card, ordinary_deck, redis
):
    fake, scheduled = redis
    monkeypatch.setattr(
        consumer, "feed_collections_cache_fingerprint", AsyncMock(return_value=None)
    )
    read = AsyncMock(return_value=SimpleNamespace(collections=[scheduled_card]))
    monkeypatch.setattr(producer, "discover_collections", read)

    for _ in range(2):
        response = await client.get("/api/feed?limit=10")
        assert response.status_code == 200
        assert response.headers["x-feed-cache"] == "disabled"
        assert len(_collections(response.json())) == 1
        await _drain(scheduled)
    assert read.await_count == 2
    assert [usable for _, usable in seated] == [True, True], "built fresh, seated"
    assert not any(key.startswith("feed_cache:") for key in fake.reads), fake.reads
    assert not any(key.startswith("feed_cache:") for key in fake.store), fake.store


async def test_seated_the_live_collection_is_refused_truthfully_and_publishes_nothing(
    client, monkeypatch, enabled, seated, card, ordinary_deck, redis
):
    """The original fixture is a LIVE hub: grouped-live input the seating
    helper refuses. ON answers it with the existing ``unavailable`` shape (the
    client keeps its accepted deck), never a flat or blank opening, and leaves
    no seated page, base or manifest a later open could reuse."""
    fake, scheduled = redis
    state = {"fingerprint": "published-rev-1"}
    fingerprint = AsyncMock(
        side_effect=lambda db, *, max_age_seconds: state["fingerprint"]
    )
    monkeypatch.setattr(consumer, "feed_collections_cache_fingerprint", fingerprint)
    read = AsyncMock(return_value=SimpleNamespace(collections=[card]))
    monkeypatch.setattr(producer, "discover_collections", read)

    for attempt in (1, 2):
        response = await client.get("/api/feed?limit=10")
        assert response.status_code == 200
        assert response.headers["x-feed-cache"] == "unavailable"
        body = response.json()
        assert body["items"] == [] and body["total"] == 0
        assert body["has_more"] is False
        assert body["cache"]["status"] == "unavailable"
        assert body["cache"]["reason"] == "opening_unsupported"
        await _drain(scheduled)
        assert read.await_count == attempt, "a refusal is rebuilt, never reused"
        assert seated[-1][1] is False and "collection" in seated[-1][0]
        assert not any(key.startswith("feed_cache:") for key in fake.store), fake.store

    # Control: the same route, once the live hub is withdrawn, serves the deck —
    # the refusal above is the live hub's, not a dark seated route.
    state["fingerprint"] = "withdrawn-rev-2"
    read.return_value = SimpleNamespace(collections=[])
    recovered = await client.get("/api/feed?limit=10")
    assert recovered.status_code == 200
    assert recovered.headers["x-feed-cache"] == "miss"
    assert len(recovered.json()["items"]) == 10

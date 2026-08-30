"""LAT-P141 — route-level proof that the page base reaches the RENDER.

Every helper in ``app/utils/feed_cache.py`` can be perfect while ``get_feed``
never consults them, or consults them and folds the result back into a cold
build. That failure is invisible to a unit test and invisible to a latency
reading taken on a warm minute, so it gets its own file that drives the real
route through the real ASGI app.

Three claims, each of which a helper test cannot make:

1. The route DERIVES the base key the helper computes — a base warmed under a
   key nobody reads is LAT-P001's silent warmer wearing a new hat.
2. The route SLICES it and serves it, with an honest ``X-Feed-Cache`` label, so
   a field debugger can tell a base serve from a page hit.
3. The route PUBLISHES it after a build, including on the warmer's build, which
   is what makes the whole scroll warm at no extra cost to the warmer.
"""

import json
from contextlib import asynccontextmanager
from importlib import import_module
from unittest.mock import MagicMock

import pytest

from app.utils import request_cache as _rc
from app.utils.feed_cache import (
    FEED_PAGE_BASE_BUILT_AT_FIELD,
    FEED_PAGE_BASE_ENV,
    feed_page_base_cache_key,
)

pcp = import_module("app.tasks.precompute_category_pages")

#: The native Discover shape, and the one the production measurement used.
NATIVE = "limit=50&offset={offset}&event_pct=0.15"
NATIVE_BASE_KEY = feed_page_base_cache_key(limit=50, event_pct=0.15)

TOTAL = 105


def _base_body(n=TOTAL):
    return {
        "items": [{"type": "futures", "data": {"id": i}} for i in range(n)],
        "total": n,
        FEED_PAGE_BASE_BUILT_AT_FIELD: 1_700_000_000.0,
    }


class _DictRedis:
    """A dict with a Redis face. Records reads, honours TTL-less setex."""

    def __init__(self, seed=None):
        self.store: dict[str, str] = dict(seed or {})
        self.reads: list[str] = []
        self.writes: list[tuple[str, int]] = []

    async def get(self, key):
        self.reads.append(key)
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.writes.append((key, int(ttl)))
        self.store[key] = value
        return True

    def written_keys(self):
        return [k for k, _ in self.writes]

    def ttl_for(self, key):
        return next(ttl for k, ttl in self.writes if k == key)


def _reset_rc():
    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _rc._reset_shared_client_for_tests()


async def _async(value):
    return value


#: Publications are scheduled detached. They are captured here so a test can
#: await them deliberately instead of racing them, and so the ones a test does
#: not care about are CLOSED rather than left as un-awaited coroutines — an
#: "was never awaited" warning is noise that hides the next real one.
_SCHEDULED: list = []


@pytest.fixture(autouse=True)
def _close_undrained_publications():
    _SCHEDULED.clear()
    yield
    for coro in _SCHEDULED:
        coro.close()
    _SCHEDULED.clear()


def _install(monkeypatch, fake):
    _reset_rc()
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    def _capture(coro):
        _SCHEDULED.append(coro)
        return None

    monkeypatch.setattr(_rc, "schedule_background", _capture)
    return _SCHEDULED


async def _drain(scheduled):
    for coro in list(scheduled):
        await coro
    scheduled.clear()


# ---------------------------------------------------------------------------
# 1. The key the route derives
# ---------------------------------------------------------------------------


async def test_the_route_reads_the_base_key_the_helper_computes(client, monkeypatch):
    fake = _DictRedis()
    _install(monkeypatch, fake)

    resp = await client.get("/api/feed?" + NATIVE.format(offset=50))
    assert resp.status_code == 200

    assert NATIVE_BASE_KEY in fake.reads, (
        "get_feed never consulted the page base — a base nobody reads is a "
        "warmer that warms nothing (LAT-P001)"
    )


async def test_the_base_is_read_after_the_per_offset_entry_not_instead_of_it(
    client, monkeypatch
):
    """Order matters: the per-offset entry is this exact page, the base is the
    list it came from. Reading the base first would serve a slice of an older
    list while a fresher page sat unread."""
    fake = _DictRedis()
    _install(monkeypatch, fake)

    await client.get("/api/feed?" + NATIVE.format(offset=50))

    assert fake.reads.index(NATIVE_BASE_KEY) > 0
    assert NATIVE_BASE_KEY not in fake.reads[:1]


# ---------------------------------------------------------------------------
# 2. The serve
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "offset,expected_ids,expected_more",
    [
        (0, list(range(0, 50)), True),
        (50, list(range(50, 100)), True),
        (100, [100, 101, 102, 103, 104], False),
    ],
)
async def test_every_page_of_the_scroll_comes_off_one_stored_build(
    client, monkeypatch, offset, expected_ids, expected_more
):
    fake = _DictRedis({NATIVE_BASE_KEY: json.dumps(_base_body())})
    _install(monkeypatch, fake)

    resp = await client.get("/api/feed?" + NATIVE.format(offset=offset))
    assert resp.status_code == 200
    body = resp.json()

    assert [it["data"]["id"] for it in body["items"]] == expected_ids
    assert body["total"] == TOTAL
    assert body["offset"] == offset
    assert body["limit"] == 50
    assert body["has_more"] is expected_more


async def test_the_header_says_page_base_so_a_debugger_can_tell_the_tiers_apart(
    client, monkeypatch
):
    fake = _DictRedis({NATIVE_BASE_KEY: json.dumps(_base_body())})
    _install(monkeypatch, fake)

    resp = await client.get("/api/feed?" + NATIVE.format(offset=50))
    assert resp.headers["X-Feed-Cache"] == "page_base_hit"
    assert resp.json()["cache"]["status"] == "page_base_hit"
    assert resp.json()["cache"]["reason"] == "page_base"


async def test_a_stale_only_base_is_served_and_says_so(client, monkeypatch):
    fake = _DictRedis({f"{NATIVE_BASE_KEY}:stale": json.dumps(_base_body())})
    _install(monkeypatch, fake)

    resp = await client.get("/api/feed?" + NATIVE.format(offset=50))
    assert resp.headers["X-Feed-Cache"] == "page_base_stale_hit"
    assert len(resp.json()["items"]) == 50


async def test_the_bases_build_time_survives_the_hop(client, monkeypatch):
    """CERT-409: the live ceiling bounds how old a SCORE may be, so every tier
    carries the build time rather than stamping its own read time."""
    fake = _DictRedis({NATIVE_BASE_KEY: json.dumps(_base_body())})
    _install(monkeypatch, fake)

    resp = await client.get("/api/feed?" + NATIVE.format(offset=50))
    assert resp.json()["cache"]["built_at"] == 1_700_000_000.0


async def test_the_internal_build_time_field_never_reaches_the_client(
    client, monkeypatch
):
    fake = _DictRedis({NATIVE_BASE_KEY: json.dumps(_base_body())})
    _install(monkeypatch, fake)

    body = (await client.get("/api/feed?" + NATIVE.format(offset=50))).json()
    assert FEED_PAGE_BASE_BUILT_AT_FIELD not in body


async def test_a_truncated_base_falls_through_to_a_build(client, monkeypatch):
    """Fail closed. A base whose ``total`` its items cannot support would end
    the user's scroll early — slow is recoverable, wrong is not."""
    broken = _base_body()
    broken["items"] = broken["items"][:40]
    fake = _DictRedis({NATIVE_BASE_KEY: json.dumps(broken)})
    _install(monkeypatch, fake)

    resp = await client.get("/api/feed?" + NATIVE.format(offset=50))
    assert resp.headers["X-Feed-Cache"] != "page_base_hit"


async def test_a_different_limit_does_not_read_another_limits_base(
    client, monkeypatch
):
    """``limit`` sizes windows inside the display chain, so 20 and 50 are two
    different lists. Serving one from the other's base would reshuffle the
    page."""
    fake = _DictRedis({NATIVE_BASE_KEY: json.dumps(_base_body())})
    _install(monkeypatch, fake)

    resp = await client.get("/api/feed?limit=20&offset=20&event_pct=0.15")
    assert resp.headers["X-Feed-Cache"] != "page_base_hit"


async def test_the_kill_switch_stops_the_base_being_read_at_all(
    client, monkeypatch
):
    monkeypatch.setenv(FEED_PAGE_BASE_ENV, "0")
    fake = _DictRedis({NATIVE_BASE_KEY: json.dumps(_base_body())})
    _install(monkeypatch, fake)

    resp = await client.get("/api/feed?" + NATIVE.format(offset=50))
    assert NATIVE_BASE_KEY not in fake.reads
    assert resp.headers["X-Feed-Cache"] != "page_base_hit"


async def test_a_my_teams_page_is_never_served_from_a_shared_list(
    client, monkeypatch
):
    fake = _DictRedis()
    _install(monkeypatch, fake)

    await client.get(
        "/api/feed?limit=50&offset=50&my_teams_only=true&include_futures=false"
    )
    assert not [k for k in fake.reads if "pagebase" in k]


# ---------------------------------------------------------------------------
# 3. The publish
# ---------------------------------------------------------------------------


async def test_an_ordinary_cold_build_publishes_the_base(client, monkeypatch):
    fake = _DictRedis()
    scheduled = _install(monkeypatch, fake)

    resp = await client.get("/api/feed?" + NATIVE.format(offset=0))
    assert resp.status_code == 200
    await _drain(scheduled)

    assert NATIVE_BASE_KEY in fake.written_keys()
    assert f"{NATIVE_BASE_KEY}:stale" in fake.written_keys()


async def test_the_published_base_carries_the_whole_list_and_no_page_fields(
    client, monkeypatch
):
    fake = _DictRedis()
    scheduled = _install(monkeypatch, fake)

    resp = await client.get("/api/feed?" + NATIVE.format(offset=0))
    await _drain(scheduled)

    stored = json.loads(fake.store[NATIVE_BASE_KEY])
    assert stored["total"] == resp.json()["total"]
    assert len(stored["items"]) == stored["total"]
    # ``limit``/``offset``/``has_more``/``cache`` describe one serve. Leaving
    # them on the base would let a later reader take one page's window for the
    # list's own.
    for per_serve in ("limit", "offset", "has_more", "cache"):
        assert per_serve not in stored
    assert FEED_PAGE_BASE_BUILT_AT_FIELD in stored


async def test_the_base_never_carries_an_internal_underscore_item_key(
    client, monkeypatch
):
    """The scrub was widened from ``paginated`` to ``feed_items`` for exactly
    this: a base scrubbed only in its first window ships ``_rank_score`` to
    every reader of page 2, and the public-item-contract test only ever sees
    page 1."""
    fake = _DictRedis()
    scheduled = _install(monkeypatch, fake)

    await client.get("/api/feed?" + NATIVE.format(offset=0))
    await _drain(scheduled)

    stored = json.loads(fake.store[NATIVE_BASE_KEY])
    for item in stored["items"]:
        assert not [k for k in item if k.startswith("_")], item


def _plant_a_real_list(monkeypatch, n=TOTAL):
    """Make the build produce ``n`` items instead of the fixture's zero.

    🔴 WITHOUT THIS THE PUBLISH TESTS PROVE ALMOST NOTHING, and the mutation
    battery found that out rather than this file claiming it. ``mock_db``
    answers every query empty, so the built list is ``[]`` and ``total`` is 0 —
    under which "store the whole list" and "store the served page" are the SAME
    zero items, and the mutant that publishes ``paginated`` as the base
    SURVIVED a green suite.

    ``apply_discover_display_chain`` is the correct seam: it is the last stage
    before the slice, so patching it exercises the real pagination, the real
    scrub, the real key derivation and the real publish over a list long enough
    for a window to differ from the whole.
    """
    feed_module = import_module("app.routes.feed")
    planted = [
        {
            "type": "futures",
            "score": 90 - i,
            # An internal key on EVERY item, so the scrub has to reach past the
            # first window for the base to come out clean.
            "_rank_score": 90.0 - i,
            "data": {"id": i},
        }
        for i in range(n)
    ]

    def _fake_chain(items, **kwargs):
        return [dict(it) for it in planted], {"reviewed_filtered_count": None}

    monkeypatch.setattr(feed_module, "apply_discover_display_chain", _fake_chain)
    return planted


async def test_a_build_publishes_the_WHOLE_list_and_serves_only_the_window(
    client, monkeypatch
):
    fake = _DictRedis()
    scheduled = _install(monkeypatch, fake)
    _plant_a_real_list(monkeypatch)

    resp = await client.get("/api/feed?" + NATIVE.format(offset=0))
    await _drain(scheduled)
    body = resp.json()

    # Served: one window.
    assert [it["data"]["id"] for it in body["items"]] == list(range(0, 50))
    assert body["total"] == TOTAL
    assert body["has_more"] is True

    # Stored: the whole list, which is the entire point.
    stored = json.loads(fake.store[NATIVE_BASE_KEY])
    assert stored["total"] == TOTAL
    assert [it["data"]["id"] for it in stored["items"]] == list(range(TOTAL))


async def test_the_scrub_reaches_past_the_first_window_into_the_stored_list(
    client, monkeypatch
):
    """Every planted item carries ``_rank_score``. Scrubbing only ``paginated``
    leaves it on items 50-104, which is exactly what page 2 would then ship."""
    fake = _DictRedis()
    scheduled = _install(monkeypatch, fake)
    _plant_a_real_list(monkeypatch)

    await client.get("/api/feed?" + NATIVE.format(offset=0))
    await _drain(scheduled)

    stored = json.loads(fake.store[NATIVE_BASE_KEY])
    leaked = [
        (i, k)
        for i, item in enumerate(stored["items"])
        for k in item
        if k.startswith("_")
    ]
    assert not leaked, f"internal keys survived outside the served window: {leaked[:5]}"


async def test_page_two_of_a_published_base_is_page_two_of_the_build(
    client, monkeypatch
):
    """The round trip, end to end: build page 1 (which publishes the base), then
    ask for page 2 and get the SECOND window of that same build — from the
    stored list, not from a rebuild."""
    fake = _DictRedis()
    scheduled = _install(monkeypatch, fake)
    _plant_a_real_list(monkeypatch)

    await client.get("/api/feed?" + NATIVE.format(offset=0))
    await _drain(scheduled)

    _reset_rc()
    resp = await client.get("/api/feed?" + NATIVE.format(offset=50))
    body = resp.json()

    assert resp.headers["X-Feed-Cache"] == "page_base_hit"
    assert [it["data"]["id"] for it in body["items"]] == list(range(50, 100))
    assert body["has_more"] is True
    assert not [k for it in body["items"] for k in it if k.startswith("_")]


async def test_the_base_gets_the_anonymous_lifetime_not_the_builders(
    client, monkeypatch
):
    """A fresh session builds the base too. Its own entry lives 5 s; the
    anonymous list lives 60 s. Stamping the builder's TTL on the base would
    expire it before the next scroll and this fix would measure as noise."""
    fake = _DictRedis()
    scheduled = _install(monkeypatch, fake)

    await client.get(
        "/api/feed?" + NATIVE.format(offset=0),
        headers={"x-session-id": "11111111-1111-4111-8111-111111111111"},
    )
    await _drain(scheduled)

    from app.utils.feed_cache import FEED_RESPONSE_TTL_ANON_SECONDS

    assert fake.ttl_for(NATIVE_BASE_KEY) == FEED_RESPONSE_TTL_ANON_SECONDS


async def test_the_warmers_build_publishes_the_base(client, monkeypatch, mock_db):
    """The whole scroll goes warm at zero extra cost to the warmer: it already
    builds this list for page 1."""
    fake = _DictRedis()
    scheduled = _install(monkeypatch, fake)

    @asynccontextmanager
    async def fake_session():
        yield mock_db

    monkeypatch.setattr("app.tasks.base.get_task_session", fake_session)

    shape = next(
        s for s in pcp.FEED_PREWARM_SHAPES if s["label"] == "discover_native"
    )
    await pcp._prewarm_feed_shape(dict(shape), MagicMock())
    await _drain(scheduled)

    assert NATIVE_BASE_KEY in fake.written_keys()


async def test_the_warmer_does_not_read_the_base_it_is_there_to_fill(
    client, monkeypatch, mock_db
):
    fake = _DictRedis({NATIVE_BASE_KEY: json.dumps(_base_body())})
    _install(monkeypatch, fake)

    @asynccontextmanager
    async def fake_session():
        yield mock_db

    monkeypatch.setattr("app.tasks.base.get_task_session", fake_session)

    shape = next(
        s for s in pcp.FEED_PREWARM_SHAPES if s["label"] == "discover_native"
    )
    await pcp._prewarm_feed_shape(dict(shape), MagicMock())

    assert NATIVE_BASE_KEY not in fake.reads

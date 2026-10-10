"""#5105 — the seated Discover opening, driven through the REAL ``get_feed``.

Alex, 2026-10-08: an ordinary live event does not take a first-ten seat (Option
A); under thin supply the eligible opening is followed by an explicit Live
events continuation; a pinned opening that stops being compliant EXPIRES WHOLE
and is recomposed from the CURRENT full deck.

``compose_opening_edition`` decides all of that and has its own tests. This file
proves the ROUTE wires it: the build and the cached page-base callers both
compose the final full deck at one request clock; per-offset tiers (fresh,
stale, last-good, a coalesced leader's page) can never certify an opening the
clock has since made noncompliant; an unsupported deck is a truthful
``unavailable``; and with the served switch OFF nothing about the route moves.

Every test drives the ASGI app with a mocked DB and a dict-backed Redis (no
services). Decks are planted at ``apply_discover_display_chain`` — the last
stage before collections and the seam — so pagination, the scrub, key
derivation and publication are all the real ones. Expected orders are written
out literally, never recomputed with the helper under test.
"""

from __future__ import annotations

import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone
from importlib import import_module

import pytest

from app.utils import request_cache as _rc
from app.utils.feed_cache import (
    FEED_PAGE_BASE_BUILT_AT_FIELD,
    feed_edition_token,
    feed_page_base_cache_key,
    feed_response_cache_key,
)
from app.utils.feed_editions import (
    EDITION_LEASE_SECONDS,
    edition_manifest_cache_key,
    edition_policy_fingerprint,
)

feed_module = import_module("app.routes.feed")

# The web Discover shape: `event_pct` given, so `mode` stays None.
WEB = dict(limit=20, event_pct=0.15)

T0 = datetime(2026, 10, 9, 17, 50, tzinfo=timezone.utc)
START = T0 + timedelta(minutes=10)
T1 = START + timedelta(minutes=5)


# ---------------------------------------------------------------------------
# Harness (the LAT-P141 route harness: dict Redis, captured publications)
# ---------------------------------------------------------------------------


class _DictRedis:
    def __init__(self, seed=None):
        self.store: dict[str, str] = dict(seed or {})
        self.reads: list[str] = []
        self.writes: list[tuple[str, int]] = []
        self.nx_refused: list[str] = []
        self.ops: list[tuple[str, str]] = []

    async def mget(self, keys):
        return [await self.get(key) for key in keys]

    async def get(self, key):
        self.ops.append(("get", key))
        self.reads.append(key)
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.ops.append(("setex", key))
        self.writes.append((key, int(ttl)))
        self.store[key] = value
        return True

    async def set(self, key, value, ex=None, nx=False):
        """redis-py ``SET ... EX NX`` only, atomic here as in Redis (one dict
        step). A plain ``SET`` stays unmodelled — it raises, exactly as it did
        before this fake had ``set`` — so unrelated writers keep their old
        (failed, swallowed) behaviour in every existing test."""
        if not nx:
            raise AttributeError("plain SET is not modelled by this fake")
        self.ops.append(("set_nx", key))
        if key in self.store:
            self.nx_refused.append(key)
            return None
        self.writes.append((key, int(ex or 0)))
        self.store[key] = value
        return True

    def written(self, key):
        """LANDED writes to ``key`` (an NX that found the key is not one)."""
        return [k for k, _ in self.writes if k == key]


_SCHEDULED: list = []


@pytest.fixture(autouse=True)
def _harness(monkeypatch):
    _SCHEDULED.clear()
    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _rc._reset_shared_client_for_tests()
    # Collections are planted explicitly where a test needs them.
    feed_collections = import_module("app.utils.feed_collections")
    monkeypatch.setattr(feed_collections, "feed_collections_enabled", lambda **_: False)
    # The golf base's inline fill opens its own DB session; no test here may
    # reach for a database, and a failed fill would degrade (and so unpublish)
    # the build under test.
    golf_base = import_module("app.utils.golf_base")

    async def _no_golf(db, now, *, stages=None):
        return [], "unavailable"

    monkeypatch.setattr(golf_base, "get_golf_base", _no_golf)
    yield
    for coro in _SCHEDULED:
        coro.close()
    _SCHEDULED.clear()
    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()


def _install(monkeypatch, fake):
    async def _redis():
        return fake

    monkeypatch.setattr(_rc, "get_shared_async_redis", _redis)
    monkeypatch.setattr(_rc, "schedule_background", lambda coro: _SCHEDULED.append(coro))
    return fake


async def _drain():
    for coro in list(_SCHEDULED):
        await coro
    _SCHEDULED.clear()


class _Clock:
    def __init__(self, now):
        self.now = now
        self.reads = 0

    def __call__(self):
        self.reads += 1
        return self.now


@pytest.fixture
def seated(monkeypatch):
    """The served switch ON for this test only, with a movable request clock."""
    monkeypatch.setattr(feed_module, "_DISCOVER_OPENING_SEATING_SERVED", True)
    clock = _Clock(T0)
    monkeypatch.setattr(feed_module, "_feed_request_clock", clock)
    return clock


@pytest.fixture
def unseated(monkeypatch):
    """The served switch OFF for this test only: the legacy controls state the
    value they test instead of inheriting the branch's default."""
    monkeypatch.setattr(feed_module, "_DISCOVER_OPENING_SEATING_SERVED", False)


def _plant(monkeypatch, deck):
    """The build's chain output is ``deck`` (fresh copies every build)."""
    holder = {"deck": deck}

    def _fake_chain(items, **kwargs):
        return copy.deepcopy(holder["deck"]), {"reviewed_filtered_count": None}

    monkeypatch.setattr(feed_module, "apply_discover_display_chain", _fake_chain)
    return holder


async def _get(client, **params):
    query = "&".join(f"{k}={v}" for k, v in {**WEB, **params}.items())
    resp = await client.get("/api/feed?" + query)
    assert resp.status_code == 200, resp.text
    return resp, resp.json()


def _ids(items):
    out = []
    for item in items:
        data = item["data"]
        out.append(f"{item['type']}:{data.get('id', data.get('key'))}")
    return out


# --- cards -------------------------------------------------------------------


def fut(i, probability=0.5):
    return {
        "type": "futures",
        "score": 90 - i,
        "_rank_score": 90.0 - i,
        "data": {"id": i, "probability": probability},
    }


def live(i, **flags):
    return {
        "type": "event",
        "score": 95,
        "data": {
            "id": i,
            "status": "live",
            "commence_time": (T0 - timedelta(hours=1)).isoformat(),
            **flags,
        },
    }


def scheduled(i, commence, **flags):
    return {
        "type": "event",
        "score": 80,
        "data": {"id": i, "status": "scheduled", "commence_time": commence.isoformat(), **flags},
    }


def tourney(key, **flags):
    return {
        "type": "tournament",
        "score": 88,
        "data": {
            "key": key,
            "start_date": START.isoformat(),
            "end_date": (START + timedelta(days=3)).isoformat(),
            **flags,
        },
    }


def F(*ids):
    return [f"futures:{i}" for i in ids]


SEATED_POLICY = edition_policy_fingerprint(
    limit=20, event_pct=0.15, opening_seating=True
)
SEATED_POLICY_5 = edition_policy_fingerprint(
    limit=5, event_pct=0.15, opening_seating=True
)
SEATED_BASE_KEY = feed_page_base_cache_key(limit=20, event_pct=0.15, opening_seating=True)
LEGACY_BASE_KEY = feed_page_base_cache_key(limit=20, event_pct=0.15)


def _response_key(*, offset, edition=None, opening_seating):
    return feed_response_cache_key(
        limit=20,
        offset=offset,
        event_pct=0.15,
        edition=edition,
        opening_seating=opening_seating,
    )


def _drop_base(fake, key=SEATED_BASE_KEY):
    """Remove a base AND its stale mirror (the route reads both)."""
    fake.store.pop(key, None)
    fake.store.pop(f"{key}:stale", None)


def _manifest(fake, token, policy=SEATED_POLICY):
    raw = fake.store.get(edition_manifest_cache_key(token=token, policy=policy))
    return json.loads(raw) if raw else None


# A full-supply deck: one ordinary live game at seat 2, twelve eligible cards.
FULL = [fut(0), live(100)] + [fut(i) for i in range(1, 12)]
FULL_SEATED = F(*range(0, 10)) + ["event:100"] + F(10, 11)

# Thin supply: three eligible cards, six ordinary live games.
SPARSE = [live(1), fut(0), live(2), fut(1), live(3), fut(2), live(4), live(5), live(6)]
SPARSE_SEATED = F(0, 1, 2) + [f"event:{i}" for i in range(1, 7)]


# ---------------------------------------------------------------------------
# A. OFF: the route is the pre-#5105 route
# ---------------------------------------------------------------------------


def test_the_served_switch_is_on_in_the_local_release_candidate():
    # The local switch-on candidate: the constant is the whole activation and
    # its rollback. The OFF controls below pin ``False`` themselves.
    assert feed_module._DISCOVER_OPENING_SEATING_SERVED is True


def test_the_policy_is_false_for_every_shape_while_off(unseated):
    for mode in (None, "discover", "sports"):
        assert not feed_module._feed_opening_seating_policy(
            mode=mode, sport=None, category=None, tags=None,
            my_teams_only=False, include_events=True, include_futures=True,
        )


def test_the_policy_names_only_the_discover_deck_when_on(monkeypatch):
    monkeypatch.setattr(feed_module, "_DISCOVER_OPENING_SEATING_SERVED", True)
    base = dict(mode=None, sport=None, category=None, tags=None,
                my_teams_only=False, include_events=True, include_futures=True)
    policy = feed_module._feed_opening_seating_policy
    assert policy(**base)
    assert policy(**{**base, "mode": "discover"})
    for other in (
        {"mode": "sports"}, {"sport": "golf"}, {"category": "politics"},
        {"tags": '["sport:golf"]'}, {"my_teams_only": True},
        {"include_events": False}, {"include_futures": False},
    ):
        assert not policy(**{**base, **other}), other


async def test_off_serves_the_unseated_deck_under_legacy_keys_and_shapes(client, monkeypatch, unseated):
    fake = _install(monkeypatch, _DictRedis())
    _plant(monkeypatch, FULL)

    def _no_clock():
        raise AssertionError("the seated clock is read only when seating is served")

    monkeypatch.setattr(feed_module, "_feed_request_clock", _no_clock)

    _, body = await _get(client, offset=0)
    await _drain()

    assert _ids(body["items"]) == _ids(FULL), "OFF must not reorder the deck"
    assert "continuation_start" not in body
    assert body["edition"] == feed_edition_token(body["items"])
    written = [k for k, _ in fake.writes]
    assert _response_key(offset=0, opening_seating=False) in written
    assert LEGACY_BASE_KEY in written
    assert SEATED_BASE_KEY not in written
    legacy_policy = edition_policy_fingerprint(limit=20, event_pct=0.15)
    manifest = _manifest(fake, body["edition"], legacy_policy)
    assert manifest is not None and "layout" not in manifest


async def test_off_still_serves_per_offset_and_last_good_tiers(client, monkeypatch, unseated):
    """The control for section D: the seeding below reaches the real keys."""
    page = {"items": [fut(7)], "total": 1, "limit": 20, "offset": 20, "has_more": False}
    fake = _install(
        monkeypatch,
        _DictRedis({_response_key(offset=20, opening_seating=False): json.dumps(page)}),
    )
    resp, body = await _get(client, offset=20)
    assert resp.headers["X-Feed-Cache"] == "hit"
    assert _ids(body["items"]) == F(7)
    assert fake.reads[0] == _response_key(offset=20, opening_seating=False)


# ---------------------------------------------------------------------------
# B. ON, build caller
# ---------------------------------------------------------------------------


async def test_a_build_seats_the_full_deck_and_publishes_a_section_aware_edition(
    client, monkeypatch, seated
):
    fake = _install(monkeypatch, _DictRedis())
    _plant(monkeypatch, FULL)

    resp, body = await _get(client, offset=0)
    await _drain()

    assert resp.headers["X-Feed-Cache"] == "miss"
    assert _ids(body["items"]) == FULL_SEATED
    assert "continuation_start" not in body
    assert "edition_status" not in body
    assert body["edition"] == feed_edition_token(body["items"], None)
    # Bodies, scores and probabilities ride through untouched.
    by_id = {f"{c['type']}:{c['data']['id']}": c for c in FULL}
    for item in body["items"]:
        source = by_id[_ids([item])[0]]
        assert item["score"] == source["score"]
        assert item["data"] == source["data"]
        assert not [k for k in item if k.startswith("_")]

    manifest = _manifest(fake, body["edition"])
    assert manifest["layout"] == {"version": 1, "continuation_start": None}
    assert manifest["built_at"] == T0.timestamp(), "minted at the request clock"
    base = json.loads(fake.store[SEATED_BASE_KEY])
    assert _ids(base["items"]) == _ids(FULL), "the base keeps the RAW full deck"
    assert base["total"] == len(FULL)
    assert base["edition"] == body["edition"]
    assert "edition_status" not in base
    assert not [k for it in base["items"] for k in it if k.startswith("_")]
    assert LEGACY_BASE_KEY not in fake.store


@pytest.mark.parametrize("offset", [0, 2, 4, 6, 8])
async def test_a_sparse_build_carries_the_global_boundary_on_every_page_cut(
    client, monkeypatch, seated, offset
):
    _install(monkeypatch, _DictRedis())
    _plant(monkeypatch, SPARSE)

    _, body = await _get(client, offset=offset, limit=2)

    assert _ids(body["items"]) == SPARSE_SEATED[offset : offset + 2]
    assert body["continuation_start"] == 3
    assert body["total"] == 9
    assert body["edition"] == feed_edition_token(
        [{"type": i.split(":")[0], "data": {"id": int(i.split(":")[1])}} for i in SPARSE_SEATED],
        3,
    )


async def test_boundary_zero_is_served_as_zero_not_absent(client, monkeypatch, seated):
    _install(monkeypatch, _DictRedis())
    deck = [live(1), live(2), live(3), live(4)]
    _plant(monkeypatch, deck)

    for offset in (0, 2):
        _, body = await _get(client, offset=offset, limit=2)
        assert "continuation_start" in body
        assert body["continuation_start"] == 0
        assert _ids(body["items"]) == _ids(deck)[offset : offset + 2]


async def test_exemptions_and_typed_non_live_keep_their_seats(client, monkeypatch, seated):
    _install(monkeypatch, _DictRedis())
    deck = [
        live(1, is_marquee=True),
        live(2, is_major=True),
        live(3, event_tags=["tier:1", "importance:playoff"]),
        scheduled(4, T0 - timedelta(minutes=30)),  # typed not-live, start passed
        live(5, event_tags=["tier:1"]),  # one tag alone is not an exemption
    ] + [fut(i) for i in range(0, 10)]
    _plant(monkeypatch, deck)

    _, body = await _get(client, offset=0)

    assert _ids(body["items"]) == (
        ["event:1", "event:2", "event:3", "event:4"]
        + F(*range(0, 6))
        + ["event:5"]
        + F(6, 7, 8, 9)
    )


async def test_the_composition_sees_collections_and_refuses_one_that_launders_live(
    client, monkeypatch, seated
):
    """The seam is AFTER collections: a collection naming an ordinary live game
    makes the deck unsupported — which only the post-collection deck shows."""
    fake = _install(monkeypatch, _DictRedis())
    _plant(monkeypatch, FULL)
    feed_collections = import_module("app.utils.feed_collections")
    monkeypatch.setattr(feed_collections, "feed_collections_enabled", lambda **_: True)

    async def _fp(db, **_):
        return "pub:1"

    async def _add(db, items, **_):
        return [
            {"type": "collection", "data": {"id": "c1", "matched_event_ids": [100]}}
        ] + items

    monkeypatch.setattr(feed_collections, "feed_collections_cache_fingerprint", _fp)
    monkeypatch.setattr(feed_collections, "add_feed_collections", _add)

    resp, body = await _get(client, offset=0)
    await _drain()

    assert body["items"] == [] and body["total"] == 0
    assert body["cache"]["status"] == "unavailable"
    assert body["cache"]["reason"] == "opening_unsupported"
    assert resp.headers["X-Feed-Cache"] == "unavailable"
    assert fake.writes == [], "an unsupported deck publishes nothing"


async def test_an_ordinary_collection_is_seated_like_any_card(client, monkeypatch, seated):
    _install(monkeypatch, _DictRedis())
    _plant(monkeypatch, FULL)
    feed_collections = import_module("app.utils.feed_collections")
    monkeypatch.setattr(feed_collections, "feed_collections_enabled", lambda **_: True)

    async def _fp(db, **_):
        return "pub:1"

    async def _add(db, items, **_):
        return [{"type": "collection", "data": {"id": "c1", "matched_event_ids": []}}] + items

    monkeypatch.setattr(feed_collections, "feed_collections_cache_fingerprint", _fp)
    monkeypatch.setattr(feed_collections, "add_feed_collections", _add)

    _, body = await _get(client, offset=0)
    assert _ids(body["items"])[:2] == ["collection:c1", "futures:0"]
    assert _ids(body["items"]).index("event:100") == 10


async def test_an_unsupported_deck_is_a_truthful_refusal_with_nothing_kept(
    client, monkeypatch, seated
):
    fake = _install(monkeypatch, _DictRedis())
    # A live game whose own start is in the future: conflicting typed fields,
    # unexempt, in the candidate opening.
    conflicted = live(9)
    conflicted["data"]["commence_time"] = (T0 + timedelta(hours=2)).isoformat()
    _plant(monkeypatch, [conflicted] + [fut(i) for i in range(12)])

    _, body = await _get(client, offset=0)
    await _drain()

    assert body["cache"]["status"] == "unavailable"
    assert body["cache"]["reason"] == "opening_unsupported"
    assert body["items"] == [] and "edition" not in body
    assert fake.writes == []
    key = _response_key(offset=0, opening_seating=True)
    assert _rc.recall_last_good(key) is None


# ---------------------------------------------------------------------------
# C. ON, cached page-base caller
# ---------------------------------------------------------------------------


async def test_every_page_cut_from_the_seated_base_matches_the_build(
    client, monkeypatch, seated
):
    fake = _install(monkeypatch, _DictRedis())
    _plant(monkeypatch, SPARSE)
    _, page0 = await _get(client, offset=0, limit=2)
    await _drain()
    # The base was published for limit=2; cut every later page from it.
    base_key = feed_page_base_cache_key(limit=2, event_pct=0.15, opening_seating=True)
    assert base_key in fake.store

    seen = list(page0["items"])
    for offset in (2, 4, 6, 8):
        resp, body = await _get(client, offset=offset, limit=2)
        assert resp.headers["X-Feed-Cache"] == "page_base_hit"
        assert body["continuation_start"] == 3
        assert body["edition"] == page0["edition"]
        assert "edition_status" not in body
        seen.extend(body["items"])
    assert _ids(seen) == SPARSE_SEATED


async def test_a_valid_pin_holds_with_current_prices_and_never_renews_its_lease(
    client, monkeypatch, seated
):
    fake = _install(monkeypatch, _DictRedis())
    holder = _plant(monkeypatch, FULL)
    _, page0 = await _get(client, offset=0, limit=5)
    await _drain()
    token = page0["edition"]
    manifest_key = edition_manifest_cache_key(token=token, policy=SEATED_POLICY_5)
    minted = fake.store[manifest_key]
    assert len(fake.written(manifest_key)) == 1

    # The current deck: every price moved and a newcomer arrived at the top.
    holder["deck"] = [fut(500)] + [
        {**c, "data": {**c["data"], "probability": 0.91}} if c["type"] == "futures" else c
        for c in FULL
    ]
    _drop_base(fake, feed_page_base_cache_key(limit=5, event_pct=0.15, opening_seating=True))
    seated.now = T0 + timedelta(minutes=1)
    await _get(client, offset=0, limit=5)  # republishes the base with the new deck
    await _drain()
    writes_before = len(fake.written(manifest_key))

    seated.now = T0 + timedelta(minutes=2)
    resp, body = await _get(client, offset=5, limit=5, edition=token)
    await _drain()

    assert resp.headers["X-Feed-Cache"] == "page_base_hit"
    assert body["edition_status"] == "pinned"
    assert body["edition"] == token
    assert _ids(body["items"]) == FULL_SEATED[5:10]
    assert {it["data"]["probability"] for it in body["items"]} == {0.91}
    assert body["total"] == len(FULL), "the pinned list, not the newcomer-swollen one"
    assert len(fake.written(manifest_key)) == writes_before
    assert fake.store[manifest_key] == minted


async def test_a_held_build_also_never_renews_the_pins_lease(client, monkeypatch, seated):
    fake = _install(monkeypatch, _DictRedis())
    _plant(monkeypatch, FULL)
    _, page0 = await _get(client, offset=0, limit=5)
    await _drain()
    token = page0["edition"]
    manifest_key = edition_manifest_cache_key(token=token, policy=SEATED_POLICY_5)
    _drop_base(fake, feed_page_base_cache_key(limit=5, event_pct=0.15, opening_seating=True))
    writes_before = len(fake.written(manifest_key))
    assert writes_before == 1, "the pin was minted once by page zero"

    seated.now = T0 + timedelta(minutes=3)
    resp, body = await _get(client, offset=5, limit=5, edition=token)
    await _drain()

    assert resp.headers["X-Feed-Cache"] == "miss"
    assert body["edition_status"] == "pinned" and body["edition"] == token
    assert len(fake.written(manifest_key)) == writes_before


@pytest.mark.parametrize("caller", ["base", "build"])
async def test_an_expired_pin_recomposes_from_the_current_deck_with_its_newcomers(
    client, monkeypatch, seated, caller
):
    fake = _install(monkeypatch, _DictRedis())
    game = scheduled(300, T0 + timedelta(hours=1))
    deck0 = [fut(0), game] + [fut(i) for i in range(1, 12)]
    holder = _plant(monkeypatch, deck0)
    _, page0 = await _get(client, offset=0, limit=20)
    await _drain()
    old = page0["edition"]
    assert _ids(page0["items"])[1] == "event:300"
    old_manifest = fake.store[edition_manifest_cache_key(token=old, policy=SEATED_POLICY)]

    # Now: the game went live (ordinary), and a newcomer joined the deck.
    went_live = live(300)
    holder["deck"] = [fut(0), went_live, fut(500)] + [fut(i) for i in range(1, 12)]
    _drop_base(fake)
    seated.now = T0 + timedelta(minutes=5)
    if caller == "base":
        await _get(client, offset=0)  # an unpinned reader republishes the base
        await _drain()

    resp, body = await _get(client, offset=0, edition=old)
    await _drain()

    expected = F(0, 500) + F(*range(1, 9)) + ["event:300"] + F(9, 10, 11)
    assert resp.headers["X-Feed-Cache"] == ("page_base_hit" if caller == "base" else "miss")
    assert body["edition_status"] == "expired"
    assert _ids(body["items"]) == expected
    assert body["edition"] != old
    replacement = _manifest(fake, body["edition"])
    assert replacement is not None and replacement["layout"]["continuation_start"] is None
    assert replacement["members"] == expected
    assert fake.store[edition_manifest_cache_key(token=old, policy=SEATED_POLICY)] == old_manifest


async def test_a_seated_base_the_slicer_would_not_vouch_for_is_rebuilt(
    client, monkeypatch, seated
):
    truncated = {"items": [fut(1)], "total": 5, FEED_PAGE_BASE_BUILT_AT_FIELD: 1.0}
    _install(monkeypatch, _DictRedis({SEATED_BASE_KEY: json.dumps(truncated)}))
    _plant(monkeypatch, FULL)

    resp, body = await _get(client, offset=0)
    assert resp.headers["X-Feed-Cache"] == "miss"
    assert _ids(body["items"]) == FULL_SEATED


async def test_an_unsupported_current_base_is_refused_not_served_flat(
    client, monkeypatch, seated
):
    unknown = {"type": "mystery", "data": {"id": 1}}
    base = {"items": [unknown, fut(2)], "total": 2, FEED_PAGE_BASE_BUILT_AT_FIELD: 1.0}
    fake = _install(monkeypatch, _DictRedis({SEATED_BASE_KEY: json.dumps(base)}))

    resp, body = await _get(client, offset=0)
    await _drain()
    assert body["cache"]["status"] == "unavailable"
    assert body["cache"]["reason"] == "opening_unsupported"
    assert fake.writes == []


async def test_a_composed_read_of_the_bases_own_edition_writes_no_manifest(
    client, monkeypatch, seated
):
    fake = _install(monkeypatch, _DictRedis())
    _plant(monkeypatch, FULL)
    _, page0 = await _get(client, offset=0)
    await _drain()
    count = len(fake.writes)

    resp, body = await _get(client, offset=0)
    await _drain()
    assert resp.headers["X-Feed-Cache"] == "page_base_hit"
    assert body["edition"] == page0["edition"]
    assert len(fake.writes) == count


# ---------------------------------------------------------------------------
# D. One request clock: a dated tournament crosses its start, fields unchanged
# ---------------------------------------------------------------------------

#: 45 cards; an unexempt tournament at seat 2 that starts at START.
CROSSING = [fut(0), tourney("t-open")] + [fut(i) for i in range(1, 44)]
#: At T1 the tournament is reliably live: it leaves the opening for seat 11.
CROSSED = F(*range(0, 10)) + ["tournament:t-open"] + F(*range(10, 44))


async def _mint_before_start(client, monkeypatch, seated, deck=CROSSING):
    fake = _install(monkeypatch, _DictRedis())
    _plant(monkeypatch, deck)
    seated.now = T0
    _, page0 = await _get(client, offset=0)
    await _drain()
    assert _ids(page0["items"]) == _ids(deck)[:20], "eligible before start"
    return fake, page0["edition"]


def _seed_stale_offset20(fake, token):
    """A pinned offset-20 page cut before START, in both per-offset tiers."""
    page = {
        "items": [fut(i) for i in range(19, 39)],
        "total": 45,
        "limit": 20,
        "offset": 20,
        "has_more": True,
        "edition": token,
        "edition_status": "pinned",
    }
    key = _response_key(offset=20, edition=token, opening_seating=True)
    fake.store[key] = json.dumps(page)
    fake.store[f"{key}:stale"] = json.dumps(page)
    return key


@pytest.mark.parametrize("tier", ["fresh", "stale"])
async def test_a_cached_offset_page_cannot_certify_an_opening_the_clock_retired(
    client, monkeypatch, seated, tier
):
    fake, token = await _mint_before_start(client, monkeypatch, seated)
    key = _seed_stale_offset20(fake, token)
    if tier == "stale":
        del fake.store[key]
    derived = []
    real_key = feed_module.feed_response_cache_key

    def _spy(**kwargs):
        out = real_key(**kwargs)
        derived.append(out)
        return out

    monkeypatch.setattr(feed_module, "feed_response_cache_key", _spy)
    fake.reads.clear()

    seated.now = T1
    resp, body = await _get(client, offset=20, edition=token)
    await _drain()

    assert key in derived, "the seeded entry sits at the key this request derives"
    assert key not in fake.reads and f"{key}:stale" not in fake.reads
    assert resp.headers["X-Feed-Cache"] == "page_base_hit"
    assert body["edition_status"] == "expired"
    assert body["edition"] != token
    assert _ids(body["items"]) == CROSSED[20:40]
    assert body["offset"] == 20
    assert _manifest(fake, body["edition"])["members"] == CROSSED


async def test_the_build_caller_retires_the_pin_at_the_request_clock(
    client, monkeypatch, seated
):
    fake, token = await _mint_before_start(client, monkeypatch, seated)
    _drop_base(fake)
    seated.now = T1
    resp, body = await _get(client, offset=20, edition=token)
    assert resp.headers["X-Feed-Cache"] == "miss"
    assert body["edition_status"] == "expired"
    assert _ids(body["items"]) == CROSSED[20:40]


async def test_last_good_cannot_certify_it_either(client, monkeypatch, seated):
    fake, token = await _mint_before_start(client, monkeypatch, seated)
    key = _response_key(offset=20, edition=token, opening_seating=True)
    stale_page = {"items": [fut(19)], "total": 45, "limit": 20, "offset": 20,
                  "has_more": True, "edition": token, "edition_status": "pinned"}
    _rc.remember_last_good(key, stale_page)

    async def _down():
        raise ConnectionError("redis down")

    monkeypatch.setattr(_rc, "get_shared_async_redis", _down)
    seated.now = T1
    resp, body = await _get(client, offset=20, edition=token)

    assert resp.headers["X-Feed-Cache"] != "last_good"
    assert body["cache"]["status"] == "error"
    # No Redis, so no manifest can be read: the pin is expired and the current
    # deck is composed at the request clock — never the remembered page.
    assert body["edition_status"] == "expired"
    assert _ids(body["items"]) == CROSSED[20:40]


async def test_last_good_off_control_is_served(client, monkeypatch, unseated):
    """Control for the test above: the same remembered page IS served unseated."""
    key = _response_key(offset=20, opening_seating=False)
    _rc.remember_last_good(key, {"items": [fut(19)], "total": 1, "limit": 20,
                                 "offset": 20, "has_more": False})

    async def _down():
        raise ConnectionError("redis down")

    monkeypatch.setattr(_rc, "get_shared_async_redis", _down)
    resp, body = await _get(client, offset=20)
    assert resp.headers["X-Feed-Cache"] == "last_good"
    assert _ids(body["items"]) == F(19)


async def _coalesce(client, monkeypatch, seated, *, waiter_now):
    """A leader paused before its build at T0; a waiter joins at ``waiter_now``."""
    fake = _install(monkeypatch, _DictRedis())
    _plant(monkeypatch, CROSSING)
    seated.now = T0
    entered, release, joined = asyncio.Event(), asyncio.Event(), asyncio.Event()
    real_config = feed_module._load_discover_runtime_config

    async def _paused_config():
        entered.set()
        await release.wait()
        return await real_config()

    monkeypatch.setattr(feed_module, "_load_discover_runtime_config", _paused_config)
    real_begin = _rc.begin_build

    def _begin(key):
        is_leader, fut_ = real_begin(key)
        if not is_leader:
            joined.set()
        return is_leader, fut_

    monkeypatch.setattr(_rc, "begin_build", _begin)

    leader = asyncio.create_task(_get(client, offset=20))
    await asyncio.wait_for(entered.wait(), 5)
    seated.now = waiter_now
    waiter = asyncio.create_task(_get(client, offset=20))
    await asyncio.wait_for(joined.wait(), 5)
    release.set()
    (lead_resp, lead_body), (wait_resp, wait_body) = await asyncio.gather(leader, waiter)
    await _drain()
    return fake, lead_resp, lead_body, wait_resp, wait_body


async def test_a_coalesced_page_is_refused_when_the_waiters_clock_crossed_start(
    client, monkeypatch, seated
):
    fake, lead_resp, lead_body, wait_resp, wait_body = await _coalesce(
        client, monkeypatch, seated, waiter_now=T1
    )
    assert lead_resp.headers["X-Feed-Cache"] == "miss"
    assert _ids(lead_body["items"]) == _ids(CROSSING)[20:40]
    assert wait_body["cache"]["status"] == "unavailable"
    assert wait_body["cache"]["reason"] == "opening_unverified"
    assert wait_body["items"] == []
    assert wait_resp.headers["X-Feed-Singleflight"] == "waiter_unavailable"


async def test_a_coalesced_page_is_served_when_the_waiters_clock_agrees(
    client, monkeypatch, seated
):
    fake, lead_resp, lead_body, wait_resp, wait_body = await _coalesce(
        client, monkeypatch, seated, waiter_now=T0 + timedelta(seconds=2)
    )
    assert wait_resp.headers["X-Feed-Cache"] == "coalesced"
    assert wait_body["items"] == lead_body["items"]
    assert wait_body["edition"] == lead_body["edition"]
    assert feed_module._OPENING_LEADER_DECK_KEY not in wait_body
    assert feed_module._OPENING_LEADER_DECK_KEY not in lead_body
    for raw in fake.store.values():
        assert feed_module._OPENING_LEADER_DECK_KEY not in raw


@pytest.mark.parametrize(
    "deck",
    [
        # A major is exempt whether or not it is live.
        [fut(0), tourney("t-open", is_major=True)] + [fut(i) for i in range(1, 44)],
        # An event's liveness is its typed status, never its start passing.
        [fut(0), scheduled(77, START)] + [fut(i) for i in range(1, 44)],
    ],
    ids=["major-tournament", "typed-scheduled-event"],
)
async def test_crossing_start_keeps_the_pin_for_exempt_and_typed_non_live_cards(
    client, monkeypatch, seated, deck
):
    fake, token = await _mint_before_start(client, monkeypatch, seated, deck=deck)
    _seed_stale_offset20(fake, token)
    seated.now = T1
    resp, body = await _get(client, offset=20, edition=token)
    assert resp.headers["X-Feed-Cache"] == "page_base_hit"
    assert body["edition_status"] == "pinned"
    assert body["edition"] == token
    assert _ids(body["items"]) == _ids(deck)[20:40]


# ---------------------------------------------------------------------------
# D2. A read is never a mint: a replacement keeps the lease it was minted with
# ---------------------------------------------------------------------------
#
# After a crossing the raw base still names its build's token, so EVERY later
# read of it composes the same replacement R. Root's repro (0a55b3a3f6): the
# retired token again, or an unpinned reader, re-published R at the later clock
# and so extended the lease of anyone already pinned to R.


async def _cross_and_mint_replacement(client, monkeypatch, seated):
    fake, old = await _mint_before_start(client, monkeypatch, seated)
    seated.now = T1
    resp, first = await _get(client, offset=20, edition=old)
    await _drain()
    assert resp.headers["X-Feed-Cache"] == "page_base_hit"
    replacement = first["edition"]
    assert replacement != old
    key = edition_manifest_cache_key(token=replacement, policy=SEATED_POLICY)
    assert json.loads(fake.store[key])["built_at"] == T1.timestamp()
    assert fake.written(key) == [key]
    return fake, old, replacement, key


@pytest.mark.parametrize("old_request", [True, False], ids=["retired-token", "unpinned"])
async def test_a_reread_of_the_crossed_base_keeps_the_replacements_lease(
    client, monkeypatch, seated, old_request
):
    fake, old, replacement, key = await _cross_and_mint_replacement(
        client, monkeypatch, seated
    )
    original = fake.store[key]

    seated.now = T1 + timedelta(seconds=5)
    params = {"offset": 20, **({"edition": old} if old_request else {})}
    resp, again = await _get(client, **params)
    await _drain()

    assert resp.headers["X-Feed-Cache"] == "page_base_hit"
    assert again["edition"] == replacement
    assert _ids(again["items"]) == CROSSED[20:40]
    assert again.get("edition_status") == ("expired" if old_request else None)
    assert fake.store[key] == original, "the replacement's built_at moved"
    assert fake.written(key) == [key], "a read landed a second write"
    assert ("setex", key) not in fake.ops


async def test_a_reader_pinned_to_the_replacement_is_held_on_its_original_lease(
    client, monkeypatch, seated
):
    fake, old, replacement, key = await _cross_and_mint_replacement(
        client, monkeypatch, seated
    )
    # Rereads by others (retired token, unpinned) at later clocks ...
    for seconds, params in ((5, {"edition": old}), (9, {})):
        seated.now = T1 + timedelta(seconds=seconds)
        await _get(client, offset=20, **params)
        await _drain()
    # ... and the pinned reader turns a page: held, under the T1 mint.
    seated.now = T1 + timedelta(seconds=12)
    resp, body = await _get(client, offset=40, edition=replacement)
    await _drain()
    assert body["edition_status"] == "pinned" and body["edition"] == replacement
    assert _ids(body["items"]) == CROSSED[40:60]
    assert json.loads(fake.store[key])["built_at"] == T1.timestamp()
    assert fake.written(key) == [key]


@pytest.mark.parametrize("land_first", ["earlier", "later"])
async def test_overlapping_publishers_land_one_mint_atomically(
    client, monkeypatch, seated, land_first
):
    """Two reads compose R before either publication lands (both saw no
    manifest). Whichever lands first is the mint; the other is refused by the
    write itself — not by a read the publisher made beforehand."""
    fake, old = await _mint_before_start(client, monkeypatch, seated)
    seated.now = T1
    _, a = await _get(client, offset=20, edition=old)
    pub_a = _SCHEDULED.pop()
    seated.now = T1 + timedelta(seconds=5)
    _, b = await _get(client, offset=20)
    pub_b = _SCHEDULED.pop()
    assert _SCHEDULED == []
    assert a["edition"] == b["edition"]
    key = edition_manifest_cache_key(token=a["edition"], policy=SEATED_POLICY)
    assert key not in fake.store, "neither publication has landed yet"

    fake.ops.clear()
    order = (pub_a, pub_b) if land_first == "earlier" else (pub_b, pub_a)
    for publication in order:
        await publication
    landed_at = T1 if land_first == "earlier" else T1 + timedelta(seconds=5)

    assert fake.ops == [("set_nx", key), ("set_nx", key)], "no read-then-write"
    assert fake.written(key) == [key]
    assert fake.nx_refused == [key]
    assert json.loads(fake.store[key])["built_at"] == landed_at.timestamp()
    assert dict(fake.writes)[key] == int(EDITION_LEASE_SECONDS)


async def test_a_lapsed_replacement_is_genuinely_reminted_by_the_next_read(
    client, monkeypatch, seated
):
    """Control: NX fills an ABSENT manifest. Once the key's TTL (the lease)
    lapses, the next read mints R afresh at its own clock."""
    fake, old, replacement, key = await _cross_and_mint_replacement(
        client, monkeypatch, seated
    )
    del fake.store[key]  # the Redis TTL lapsed
    seated.now = T1 + timedelta(seconds=20)
    _, again = await _get(client, offset=20)
    await _drain()
    assert again["edition"] == replacement
    assert json.loads(fake.store[key])["built_at"] == (T1 + timedelta(seconds=20)).timestamp()
    assert fake.written(key) == [key, key]


async def test_a_build_is_still_a_mint_unchanged(client, monkeypatch, seated):
    """Control on the scope: only the base READ publisher moved to NX. The
    build's own mint keeps its existing SETEX (same as the OFF route)."""
    fake = _install(monkeypatch, _DictRedis())
    _plant(monkeypatch, FULL)
    _, page0 = await _get(client, offset=0)
    await _drain()
    key = edition_manifest_cache_key(token=page0["edition"], policy=SEATED_POLICY)
    assert ("setex", key) in fake.ops
    assert ("set_nx", key) not in fake.ops


# ---------------------------------------------------------------------------
# D3. A seated build never completes a display capture
# ---------------------------------------------------------------------------


def _arm_capture(monkeypatch):
    from app.utils import discover_display_replay as ddr

    capture = ddr.DiscoverDisplayCapture(origin="synthetic")
    monkeypatch.setattr(feed_module, "display_capture_from_request", lambda request: capture)
    return ddr, capture


async def _get_native(client, **params):
    """The capture-supported shape: no ``event_pct``, so ``mode`` resolves to
    Discover (the recorder refuses the web shape's ``mode=None`` up front)."""
    query = "&".join(f"{k}={v}" for k, v in {"limit": 20, **params}.items())
    resp = await client.get("/api/feed?" + query)
    assert resp.status_code == 200, resp.text
    return resp, resp.json()


@pytest.mark.parametrize("requested", [False, True], ids=["unpinned", "retired-token"])
async def test_a_seated_build_abandons_its_capture_and_still_serves(
    client, monkeypatch, seated, requested
):
    fake = _install(monkeypatch, _DictRedis())
    _plant(monkeypatch, CROSSING)
    params = {"offset": 20}
    if requested:
        seated.now = T0
        _, page0 = await _get_native(client, offset=0)
        await _drain()
        assert _ids(page0["items"]) == _ids(CROSSING)[:20]
        # No base, so the edition request is a BUILD (its manifest goes too:
        # this test is about the capture, not why the pin expires).
        fake.store.clear()
        params["edition"] = page0["edition"]
    seated.now = T1
    ddr, capture = _arm_capture(monkeypatch)

    resp, body = await _get_native(client, **params)
    await _drain()

    assert resp.headers["X-Feed-Cache"] == "miss", "a real build reached the seam"
    assert _ids(body["items"]) == CROSSED[20:40]
    assert body.get("edition_status") == ("expired" if requested else None)
    assert capture.status == "abandoned", capture.refusal
    assert capture.refusal == {
        "code": ddr.INCOMPLETE,
        "detail": "build abandoned: " + feed_module._OPENING_SEATING_CAPTURE_UNSUPPORTED,
    }
    with pytest.raises(ddr.DisplayReplayError) as exc:
        capture.artifact()
    assert exc.value.code == ddr.INCOMPLETE


async def test_off_the_same_capture_is_not_abandoned(client, monkeypatch, unseated):
    """Control: the OFF route records this very build as before."""
    _install(monkeypatch, _DictRedis())
    _plant(monkeypatch, CROSSING)
    ddr, capture = _arm_capture(monkeypatch)
    resp, body = await _get_native(client, offset=20)
    assert resp.headers["X-Feed-Cache"] == "miss"
    assert _ids(body["items"]) == _ids(CROSSING)[20:40]
    assert capture.status == "complete", capture.refusal
    assert capture.artifact()["expected"]["full_deck_identities"] == _ids(CROSSING)


# ---------------------------------------------------------------------------
# E. One policy, one switch
# ---------------------------------------------------------------------------


def test_one_policy_value_drives_the_cache_shape_and_the_fingerprint():
    import inspect

    src = inspect.getsource(feed_module.get_feed)
    shape = src[src.index("_cache_shape = dict(") :]
    shape = shape[: shape.index("\n        )\n")]
    assert "opening_seating=_opening_seating," in shape
    policy = src[src.index("def _edition_policy_for(") :]
    policy = policy[: policy.index("\n\n")]
    assert "opening_seating=_opening_seating," in policy
    assert src.count("_opening_seating = ") == 1
    assert "opening_seating" not in inspect.signature(feed_module.get_feed).parameters


# ---------------------------------------------------------------------------
# F. The inert-principal share is an offset page too
# ---------------------------------------------------------------------------

_SESSION = {"x-session-id": "inert-5105"}
_FOREIGN_PAGE = {"items": [fut(999)], "total": 1, "limit": 20, "offset": 0, "has_more": False}


async def test_off_an_inert_session_takes_the_shared_anonymous_page(client, monkeypatch, unseated):
    """Control: in this harness a session principal reaches LAT-P089's share."""
    _install(
        monkeypatch,
        _DictRedis({_response_key(offset=0, opening_seating=False): json.dumps(_FOREIGN_PAGE)}),
    )
    resp = await client.get("/api/feed?limit=20&event_pct=0.15", headers=_SESSION)
    assert resp.headers["X-Feed-Cache"] == "shared_hit"
    assert _ids(resp.json()["items"]) == F(999)


async def test_a_seated_inert_session_takes_the_full_deck_base_not_the_shared_page(
    client, monkeypatch, seated
):
    fake = _install(monkeypatch, _DictRedis())
    _plant(monkeypatch, FULL)
    await _get(client, offset=0)  # an anonymous build publishes the seated base
    await _drain()
    fake.store[_response_key(offset=0, opening_seating=True)] = json.dumps(_FOREIGN_PAGE)

    resp = await client.get("/api/feed?limit=20&event_pct=0.15", headers=_SESSION)
    assert resp.headers["X-Feed-Cache"] == "page_base_hit"
    assert _ids(resp.json()["items"]) == FULL_SEATED

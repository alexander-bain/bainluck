"""Queue 275 (#1475): route-level proof that every /api/feed return path emits
the truthful cache/singleflight/coverage diagnostics, and that CORS exposes them.

Drives each of get_feed's return branches deterministically by faking the
process-shared Redis client and (where needed) the singleflight primitives, then
asserts the three observability headers are present with a truthful singleflight
label. An early return is NEVER labelled ``leader``. Also proves an allowed
browser origin can read all seven feed/request headers cross-origin.
"""

import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone
from importlib import import_module

import pytest

from app.utils import request_cache as _rc


class _FakeRedis:
    """Minimal async Redis fake driving get_feed's cache/singleflight branches.

    ``mode`` selects what ``.get`` returns:
    - ``fresh``: JSON payload for the primary key (fresh hit)
    - ``stale``: miss on primary, JSON payload on the ``:stale`` key
    - ``miss``: clean miss on both (drives a leader build)
    - ``error``: raise on ``.get`` (bounded_redis_call → failure → last-good)
    """

    def __init__(self, mode: str, payload: dict | None = None):
        self.mode = mode
        self._json = json.dumps(payload) if payload is not None else None

    async def mget(self, keys):
        return [await self.get(key) for key in keys]

    async def get(self, key):
        if self.mode == "error":
            raise RuntimeError("redis down")
        if self.mode == "fresh":
            return None if key.endswith(":stale") else self._json
        if self.mode == "stale":
            return self._json if key.endswith(":stale") else None
        return None  # clean miss

    async def setex(self, *a, **k):
        return True


async def _async(value):
    """Coroutine wrapper so a plain fake stands in for an async factory."""
    return value


def _reset_rc():
    _rc._reset_last_good_for_tests()
    _rc._reset_inflight_for_tests()
    _rc._reset_shared_client_for_tests()


_CACHED_PAYLOAD = {
    "items": [
        {"type": "futures", "data": {"id": 1}},
        {"type": "event", "data": {"id": 2}},
    ],
    "total": 2,
    "limit": 200,
    "offset": 0,
    "has_more": False,
}


@pytest.mark.usefixtures("opening_seating_off")
async def test_fresh_hit_emits_headers_singleflight_none(client, monkeypatch):
    _reset_rc()
    fake = _FakeRedis("fresh", _CACHED_PAYLOAD)
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert resp.headers["x-feed-cache"] == "hit"
    assert resp.headers["x-feed-singleflight"] == "none"
    counts = resp.headers["x-feed-counts"]
    assert "total=2" in counts
    assert "type_futures=1" in counts and "type_event=1" in counts


@pytest.mark.usefixtures("opening_seating_off")
async def test_stale_hit_emits_headers_singleflight_none(client, monkeypatch):
    _reset_rc()
    fake = _FakeRedis("stale", _CACHED_PAYLOAD)
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert resp.headers["x-feed-cache"] == "stale_hit"
    assert resp.headers["x-feed-singleflight"] == "none"
    assert "total=2" in resp.headers["x-feed-counts"]


@pytest.mark.usefixtures("opening_seating_off")
async def test_redis_error_last_good_emits_headers(client, monkeypatch):
    _reset_rc()
    fake = _FakeRedis("error")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))
    monkeypatch.setattr(_rc, "recall_last_good", lambda key, **k: dict(_CACHED_PAYLOAD))

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert resp.headers["x-feed-cache"] == "last_good"
    # A Redis-error bail predates singleflight participation.
    assert resp.headers["x-feed-singleflight"] == "none"
    assert "total=2" in resp.headers["x-feed-counts"]


@pytest.mark.usefixtures("opening_seating_off")
async def test_coalesced_waiter_emits_singleflight_coalesced(client, monkeypatch):
    _reset_rc()
    fake = _FakeRedis("miss")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    fut: asyncio.Future = asyncio.get_event_loop().create_future()
    fut.set_result(dict(_CACHED_PAYLOAD))
    monkeypatch.setattr(_rc, "begin_build", lambda key: (False, fut))

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert resp.headers["x-feed-cache"] == "coalesced"
    assert resp.headers["x-feed-singleflight"] == "coalesced"
    assert "total=2" in resp.headers["x-feed-counts"]


@pytest.mark.usefixtures("opening_seating_off")
async def test_waiter_last_good_distinguished_from_redis_last_good(client, monkeypatch):
    _reset_rc()
    fake = _FakeRedis("miss")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    fut: asyncio.Future = asyncio.get_event_loop().create_future()
    fut.set_result(None)  # leader produced nothing usable
    monkeypatch.setattr(_rc, "begin_build", lambda key: (False, fut))
    monkeypatch.setattr(_rc, "recall_last_good", lambda key, **k: dict(_CACHED_PAYLOAD))

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert resp.headers["x-feed-cache"] == "last_good"
    # Distinguishable from the Redis-error last-good (singleflight=none) above.
    assert resp.headers["x-feed-singleflight"] == "waiter_last_good"


async def test_waiter_budget_exhausted_serves_unavailable_without_building(
    client, monkeypatch
):
    """Queue 280: when the one absolute request budget is exhausted, a waiter on
    a still-running leader must NOT start a second build (never labelled leader).
    With no last-good it returns the truthful empty ``unavailable`` terminal."""
    _reset_rc()
    fake = _FakeRedis("miss")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    live = asyncio.get_event_loop().create_future()  # leader still running
    monkeypatch.setattr(_rc, "begin_build", lambda key: (False, live))
    # Zero budget => remaining is 0 => the waiter never awaits or builds.
    monkeypatch.setattr(_rc, "FEED_TOTAL_BUDGET_MS", 0)

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert resp.headers["x-feed-cache"] == "unavailable"
    assert resp.headers["x-feed-singleflight"] == "waiter_unavailable"
    body = resp.json()
    assert body["items"] == [] and body["total"] == 0
    live.cancel()  # silence the never-awaited leader future


@pytest.mark.usefixtures("opening_seating_off")
async def test_waiter_budget_exhausted_prefers_last_good(client, monkeypatch):
    """With budget exhausted, a waiter serves bounded last-good in preference to
    the empty unavailable terminal — still without a second build."""
    _reset_rc()
    fake = _FakeRedis("miss")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    live = asyncio.get_event_loop().create_future()
    monkeypatch.setattr(_rc, "begin_build", lambda key: (False, live))
    monkeypatch.setattr(_rc, "FEED_TOTAL_BUDGET_MS", 0)
    monkeypatch.setattr(_rc, "recall_last_good", lambda key, **k: dict(_CACHED_PAYLOAD))

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert resp.headers["x-feed-cache"] == "last_good"
    assert resp.headers["x-feed-singleflight"] == "waiter_last_good"
    live.cancel()


async def test_leader_build_is_the_only_leader_labelled_path(client, monkeypatch):
    _reset_rc()
    fake = _FakeRedis("miss")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    # Empty DB → miss → this request leads the build.
    assert resp.headers["x-feed-singleflight"] == "leader"
    assert "returned=0" in resp.headers["x-feed-counts"]


async def test_leader_emits_golf_provenance_header(client, monkeypatch):
    """Queue 281: the golf-base tier that served the leader build is surfaced as
    one allowlisted X-Feed-Golf-Provenance value so Ops can verify the publisher."""
    _reset_rc()
    fake = _FakeRedis("miss")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    async def _fresh_base(db, now, stages=None):
        return ([], "fresh")

    monkeypatch.setattr("app.utils.golf_base.get_golf_base", _fresh_base)

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert resp.headers["x-feed-singleflight"] == "leader"
    assert resp.headers["x-feed-golf-provenance"] == "fresh"


async def test_every_allowlisted_golf_provenance_reaches_the_header(client, monkeypatch):
    """All four allowlisted golf-base tiers (the 12 accepted C76 rows collapse to
    fresh/last_good/inline/unavailable) surface verbatim on the header."""
    for prov in ("fresh", "last_good", "inline", "unavailable"):
        _reset_rc()
        fake = _FakeRedis("miss")
        monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

        async def _base(db, now, stages=None, _p=prov):
            return ([], _p)

        monkeypatch.setattr("app.utils.golf_base.get_golf_base", _base)

        resp = await client.get("/api/feed?limit=5")
        assert resp.status_code == 200
        assert resp.headers["x-feed-golf-provenance"] == prov


async def test_leader_golf_unavailable_provenance_on_base_failure(client, monkeypatch):
    """A golf-base failure reports the truthful ``unavailable`` provenance, not a
    missing/opaque signal — the feed still serves its other cards."""
    _reset_rc()
    fake = _FakeRedis("miss")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    async def _boom_base(db, now, stages=None):
        raise RuntimeError("golf base down")

    monkeypatch.setattr("app.utils.golf_base.get_golf_base", _boom_base)

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert resp.headers["x-feed-golf-provenance"] == "unavailable"


async def test_golf_provenance_allowlist_blocks_freeform_or_identity(client, monkeypatch):
    """A free-form / identity-bearing provenance value can never reach the header
    (the C76 identity_bearing_signal / invalid_provenance guard)."""
    _reset_rc()
    fake = _FakeRedis("miss")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    async def _identity_base(db, now, stages=None):
        return ([], "fresh:user_42")

    monkeypatch.setattr("app.utils.golf_base.get_golf_base", _identity_base)

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert "x-feed-golf-provenance" not in resp.headers


@pytest.mark.usefixtures("opening_seating_off")
async def test_cache_hit_does_not_emit_golf_provenance(client, monkeypatch):
    """Golf isn't consulted on a served-from-cache path, so no golf provenance is
    fabricated there — the header appears only where golf actually ran."""
    _reset_rc()
    fake = _FakeRedis("fresh", _CACHED_PAYLOAD)
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    resp = await client.get("/api/feed?limit=5")

    assert resp.status_code == 200
    assert resp.headers["x-feed-cache"] == "hit"
    assert "x-feed-golf-provenance" not in resp.headers


async def test_requires_auth_early_return_reports_diagnostics(client, monkeypatch):
    _reset_rc()
    fake = _FakeRedis("miss")
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    resp = await client.get("/api/feed?my_teams_only=true")

    assert resp.status_code == 200
    assert resp.json()["requires_auth"] is True
    # Never labelled a leader; empty coverage reported honestly.
    assert resp.headers["x-feed-singleflight"] == "none"
    assert "returned=0" in resp.headers["x-feed-counts"]


async def test_no_pii_in_cached_path_headers(client, monkeypatch):
    _reset_rc()
    fake = _FakeRedis("fresh", _CACHED_PAYLOAD)
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    resp = await client.get(
        "/api/feed?limit=5", headers={"x-session-id": "secret-session-42"}
    )

    blob = (
        resp.headers.get("x-feed-stages", "")
        + resp.headers.get("x-feed-counts", "")
        + resp.headers.get("x-feed-singleflight", "")
    ).lower()
    for banned in ("secret-session-42", "session", "u:", "s:", "@", "http"):
        assert banned not in blob


async def test_cors_exposes_all_feed_headers(client, monkeypatch):
    """A browser on an allowed origin must be able to read all feed/request
    diagnostic headers cross-origin, including the golf-provenance signal
    (Item 2 / Queue 281)."""
    _reset_rc()
    fake = _FakeRedis("fresh", _CACHED_PAYLOAD)
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(fake))

    resp = await client.get(
        "/api/feed?limit=5", headers={"Origin": "https://bainluck.com"}
    )

    assert resp.status_code == 200
    exposed = resp.headers["access-control-expose-headers"].lower()
    for header in (
        "x-response-time",
        "x-request-id",
        "x-feed-elapsed-ms",
        "x-feed-cache",
        "x-feed-stages",
        "x-feed-counts",
        "x-feed-count-scope",
        "x-feed-singleflight",
        "x-feed-golf-provenance",
    ):
        assert header in exposed, f"CORS does not expose {header}"


# ---------------------------------------------------------------------------
# #5105: the SEATED waiter. A coalesced page is admitted only when the leader's
# own raw deck, re-composed at the waiter's clock, reproduces it; a waiter never
# serves last-good and never builds. The leader payload below is the one a real
# seated leader build handed `finish_build` — not a hand-written fixture.
# ---------------------------------------------------------------------------

_feed = import_module("app.routes.feed")

_T0 = datetime(2026, 10, 9, 17, 50, tzinfo=timezone.utc)
_START = _T0 + timedelta(minutes=10)
_T1 = _START + timedelta(minutes=5)


def _fut(i):
    return {"type": "futures", "score": 90 - i, "_rank_score": 90.0 - i,
            "data": {"id": i, "probability": 0.5}}


# An unexempt tournament that starts between the leader's clock (T0, eligible)
# and a late waiter's (T1, ordinary-live: it must leave the opening).
_SEATED_DECK = [_fut(0), {
    "type": "tournament", "score": 88,
    "data": {"key": "t-open", "start_date": _START.isoformat(),
             "end_date": (_START + timedelta(days=3)).isoformat()},
}] + [_fut(i) for i in range(1, 14)]


# The same tournament inside a bundle: at T1 the bundle inherits its child's
# restriction (#5105 correction A) and leaves the opening, so the leader's T0
# page no longer re-derives — the waiter refuses it as expired, never serves it.
_BUNDLED_DECK = [_fut(0), {
    "type": "bundle", "score": 89,
    "data": {"id": "b-open", "items": [_SEATED_DECK[1], _fut(99)]},
}] + [_fut(i) for i in range(1, 14)]


def _seated_route(monkeypatch, clock, deck=_SEATED_DECK):
    """A seated build over ``deck`` at ``clock['now']``."""
    monkeypatch.setattr(_feed, "_feed_request_clock", lambda: clock["now"])
    monkeypatch.setattr(
        _feed, "apply_discover_display_chain",
        lambda items, **kw: (copy.deepcopy(deck), {"reviewed_filtered_count": None}),
    )

    async def _no_golf(db, now, *, stages=None):
        return [], "unavailable"

    monkeypatch.setattr("app.utils.golf_base.get_golf_base", _no_golf)


async def _genuine_leader_payload(client, monkeypatch):
    """Run a real seated leader build; return (its response body, what it
    handed its coalesced waiters)."""
    handed = []
    real_finish = _rc.finish_build

    def _spy(key, future, *, result=None, exc=None):
        handed.append(result)
        return real_finish(key, future, result=result, exc=exc)

    monkeypatch.setattr(_rc, "finish_build", _spy)
    resp = await client.get("/api/feed?limit=5")
    monkeypatch.setattr(_rc, "finish_build", real_finish)
    assert resp.headers["x-feed-singleflight"] == "leader"
    assert len(handed) == 1 and isinstance(handed[0], dict)
    carried = handed[0].get(_feed._OPENING_LEADER_DECK_KEY)
    assert isinstance(carried, dict) and isinstance(carried.get("items"), list), (
        "the seated leader handed its waiters no raw deck — no waiter could "
        "ever be admitted"
    )
    return resp.json(), handed[0]


async def _wait_on(client, monkeypatch, leader_result):
    done: asyncio.Future = asyncio.get_event_loop().create_future()
    done.set_result(leader_result)
    monkeypatch.setattr(_rc, "begin_build", lambda key: (False, done))
    return await client.get("/api/feed?limit=5")


async def test_seated_waiter_admits_its_leaders_genuine_payload(
    client, monkeypatch, opening_seating_on
):
    _reset_rc()
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(_FakeRedis("miss")))
    clock = {"now": _T0}
    _seated_route(monkeypatch, clock)
    lead_body, handed = await _genuine_leader_payload(client, monkeypatch)
    assert [i["data"].get("id", i["data"].get("key")) for i in lead_body["items"]] == [
        0, "t-open", 1, 2, 3
    ]

    clock["now"] = _T0 + timedelta(seconds=2)
    resp = await _wait_on(client, monkeypatch, handed)

    assert resp.headers["x-feed-cache"] == "coalesced"
    assert resp.headers["x-feed-singleflight"] == "coalesced"
    body = resp.json()
    assert body["items"] == lead_body["items"]
    assert body["edition"] == lead_body["edition"]
    assert _feed._OPENING_LEADER_DECK_KEY not in body
    assert "total=15" in resp.headers["x-feed-counts"]


def _strip_deck(p):
    p.pop(_feed._OPENING_LEADER_DECK_KEY)


def _deck_not_a_list(p):
    p[_feed._OPENING_LEADER_DECK_KEY] = {**p[_feed._OPENING_LEADER_DECK_KEY], "items": "x"}


def _other_edition(p):
    p["edition"] = "not-the-leaders-token"


@pytest.mark.parametrize(
    "tamper,waiter_now,deck",
    [
        # the pre-#5105 page shape: no provenance at all
        (_strip_deck, _T0, _SEATED_DECK),
        (_deck_not_a_list, _T0, _SEATED_DECK),
        # the deck does not re-derive the page it rides
        (_other_edition, _T0, _SEATED_DECK),
        # genuine, but the tournament started under the waiter
        (None, _T1, _SEATED_DECK),
        # genuine, but the bundle now holds an ordinary-live child (grouped live)
        (None, _T1, _BUNDLED_DECK),
    ],
    ids=["missing-deck", "invalid-deck", "token-mismatch", "expired", "grouped-live"],
)
async def test_seated_waiter_refuses_a_leader_payload_it_cannot_reproduce(
    client, monkeypatch, opening_seating_on, tamper, waiter_now, deck
):
    _reset_rc()
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(_FakeRedis("miss")))
    clock = {"now": _T0}
    _seated_route(monkeypatch, clock, deck)
    _, handed = await _genuine_leader_payload(client, monkeypatch)
    leader_result = dict(handed)
    if tamper is not None:
        tamper(leader_result)

    clock["now"] = waiter_now
    resp = await _wait_on(client, monkeypatch, leader_result)

    assert resp.headers["x-feed-cache"] == "unavailable"
    assert resp.headers["x-feed-singleflight"] == "waiter_unavailable"
    body = resp.json()
    assert body["items"] == [] and body["total"] == 0
    assert body["cache"]["reason"] == "opening_unverified"


async def test_seated_waiter_never_serves_last_good(
    client, monkeypatch, opening_seating_on
):
    """Seated counterpart of ``test_waiter_last_good_distinguished_from_redis_last_good``:
    a remembered offset page is never consulted, so the truthful terminal is
    `unavailable` and the client keeps the deck it already accepted."""
    _reset_rc()
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(_FakeRedis("miss")))
    recalled = []
    monkeypatch.setattr(
        _rc, "recall_last_good",
        lambda key, **k: recalled.append(key) or dict(_CACHED_PAYLOAD),
    )

    resp = await _wait_on(client, monkeypatch, None)

    assert resp.headers["x-feed-cache"] == "unavailable"
    assert resp.headers["x-feed-singleflight"] == "waiter_unavailable"
    assert resp.json()["items"] == []
    assert recalled == []


async def test_seated_waiter_out_of_budget_neither_serves_last_good_nor_builds(
    client, monkeypatch, opening_seating_on
):
    _reset_rc()
    monkeypatch.setattr(_rc, "get_shared_async_redis", lambda: _async(_FakeRedis("miss")))
    live = asyncio.get_event_loop().create_future()
    monkeypatch.setattr(_rc, "begin_build", lambda key: (False, live))
    monkeypatch.setattr(_rc, "FEED_TOTAL_BUDGET_MS", 0)
    monkeypatch.setattr(_rc, "recall_last_good", lambda key, **k: dict(_CACHED_PAYLOAD))
    built = []
    monkeypatch.setattr(
        _feed, "apply_discover_display_chain",
        lambda items, **kw: built.append(1) or (items, {}),
    )

    resp = await client.get("/api/feed?limit=5")

    assert resp.headers["x-feed-cache"] == "unavailable"
    assert resp.headers["x-feed-singleflight"] == "waiter_unavailable"
    assert resp.json()["items"] == []
    assert built == [], "a waiter out of budget ran a second build"
    live.cancel()

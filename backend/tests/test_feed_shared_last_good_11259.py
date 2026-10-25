"""#11259: a build that runs out of time serves the anonymous base's durable
copy before it serves an empty Discover.

Production, 2026-10-19: `GET /api/feed?limit=20` returned 200 with 0 cards
after 25 s (`unavailable` / `events_timeout`) for ~2.5 min after release v5793
and again for ~3.3 min under the 06:30Z retention collapse. #10534's terminal
serves process-local last-good or `unavailable`; a release empties that store
on every dyno, and the Redis tiers last 300 s at most.

Pinned here, at the real route with the #10530/#10534 rig (only the DB/Redis
edges and the candidate stages faked):

* every published base also writes `<base>:last_good`, kept no longer than it
  may be served at (60 s live, 30 min otherwise);
* a fresh process whose events stage times out serves that copy as the
  requested page, labelled `last_good` with the base's own origin, and still
  publishes, remembers and hands its waiters nothing;
* a coalesced anonymous waiter does the same; a waiter that is not anonymous
  by identity keeps `waiter_unavailable`;
* process-local last-good still wins; a copy past its age bound, a live copy
  past the live ceiling, and a pinned request all keep `unavailable`;
* a copy that still calls a game `scheduled` after its start is held to the
  live ceiling, read at the READER's clock: the copy cannot see the kickoff.
"""

import asyncio
import json
import time

import pytest

import app.utils.request_cache as rc
from app.utils.feed_cache import (
    FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS,
    FEED_PAGE_BASE_BUILT_AT_FIELD,
    FEED_PAGE_BASE_LAST_GOOD_MAX_AGE_SECONDS,
    FEED_PAGE_BASE_LAST_GOOD_SUFFIX,
    feed_page_base_last_good_key,
    base_from_last_good,
    base_has_started_scheduled_game,
    encode_base_last_good,
    feed_page_base_last_good_max_age_s,
)
from app.utils.principal_independent_cache import wire_decode
from tests.test_feed_event_stage_budget_10534 import (
    SCORE,
    _enrich,
    _score,
    _StageSession,
)
from tests.test_feed_review_stage_budget_10530 import (
    DISCOVER,
    SPORTS,
    _card,
    _get,
    _ids,
    _Redis,
    _SHORT_BUDGET_MS,
)
from tests.test_feed_review_stage_budget_10530 import rig as _rig_10530

rig = _rig_10530


def _upcoming(oid: int) -> dict:
    """A scheduled (not live) game card — the page a 30-minute bound covers."""
    card = _card(oid)
    card["data"] = {**card["data"], "status": "scheduled"}
    card["headline"] = "Tonight"
    return card


class _StoreRedis(_Redis):
    """#10530's Redis, but every write is kept and read back, with its TTL."""

    def __init__(self, store=None):
        super().__init__()
        self.store = dict(store or {})
        self.ttls: dict[str, int] = {}

    async def get(self, key, *a, **k):
        self.reads.append(key)
        if key == self._kill_key:
            return self._kill_value
        return self.store.get(key)

    async def setex(self, key, ttl, val):
        self.setex_keys.append(key)
        self.store[key] = val
        self.ttls[key] = ttl
        return True


async def _drain():
    for _ in range(50):
        await asyncio.sleep(0)


async def _durable_copy_after_a_complete_build(monkeypatch, cards, *, path=DISCOVER):
    """Run one complete build, then model what a fresh dyno ~5 minutes later
    sees: no process-local last-good, every Redis tier lapsed except the
    durable copy. Returns ``(complete_body, redis, durable_key)``."""
    db = _StageSession(cards)
    redis = _StoreRedis()
    complete = (
        await _get(monkeypatch, db, redis, path=path, score=_score(db), enrich=_enrich)
    ).json()
    await _drain()
    durable = [k for k in redis.store if k.endswith(FEED_PAGE_BASE_LAST_GOOD_SUFFIX)]
    assert len(durable) == 1, redis.store.keys()
    [key] = durable
    rc._reset_last_good_for_tests()
    rc._reset_inflight_for_tests()
    fresh_dyno = _StoreRedis({key: redis.store[key]})
    return complete, redis, fresh_dyno, key


def _age_copy(redis: _StoreRedis, key: str, seconds: float) -> float:
    base = json.loads(wire_decode(redis.store[key]))
    base[FEED_PAGE_BASE_BUILT_AT_FIELD] = time.time() - seconds
    redis.store[key] = encode_base_last_good(json.dumps(base))
    return base[FEED_PAGE_BASE_BUILT_AT_FIELD]


def _reset_spies(rig):
    rig.remembered.clear()
    rig.published.clear()
    rig.finished.clear()


# --- the pure reader --------------------------------------------------------


def _base(items, *, age_s, now=1_000_000.0):
    return encode_base_last_good(
        json.dumps(
            {
                "items": items,
                "total": len(items),
                FEED_PAGE_BASE_BUILT_AT_FIELD: now - age_s,
            }
        )
    )


def _item(i, status="scheduled"):
    return {"type": "event", "data": {"id": i, "status": status}}


NOW = 1_000_000.0


def test_a_copy_without_a_live_game_serves_up_to_thirty_minutes():
    items = [_item(i) for i in range(30)]
    bound = FEED_PAGE_BASE_LAST_GOOD_MAX_AGE_SECONDS
    base, origin = base_from_last_good(_base(items, age_s=bound - 1), now=NOW)
    assert [it["data"]["id"] for it in base["items"]] == list(range(30))
    assert origin == NOW - (bound - 1)
    assert base_from_last_good(_base(items, age_s=bound + 1), now=NOW) == (None, None)


def test_a_live_game_anywhere_in_the_base_bounds_it_at_the_live_ceiling():
    # The live card sits at position 25 — outside page 1 — and still bounds it.
    items = [_item(i) for i in range(25)] + [_item(25, status="live")]
    ceiling = FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS
    assert base_from_last_good(_base(items, age_s=ceiling - 1), now=NOW)[0]
    assert base_from_last_good(_base(items, age_s=ceiling + 1), now=NOW) == (
        None,
        None,
    )


def _iso(epoch: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _starting(i, start, status="scheduled", kind="event"):
    return {"type": kind, "data": {"id": i, "status": status, "commence_time": start}}


@pytest.mark.parametrize(
    "start",
    [
        _iso(NOW - 60),  # kicked off after the build, before this read
        _iso(NOW - 600),  # already past its start at the build (status lag)
        _iso(NOW),  # starts this second
        _iso(NOW - 60).replace("+00:00", "Z"),
        _iso(NOW - 60).replace("+00:00", ""),  # naive is read as UTC
    ],
    ids=["after-build", "before-build", "at-read", "zulu", "naive"],
)
def test_a_scheduled_game_past_its_start_holds_the_copy_to_the_live_ceiling(start):
    # Position 25: outside page 1, and it still bounds the whole copy.
    items = [_item(i) for i in range(25)] + [_starting(25, start)]
    ceiling = FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS
    assert base_from_last_good(_base(items, age_s=ceiling - 1), now=NOW)[0]
    assert base_from_last_good(_base(items, age_s=240), now=NOW) == (None, None)


@pytest.mark.parametrize(
    "card",
    [
        _starting(1, _iso(NOW + 1)),  # has not started yet
        _starting(1, None),
        _starting(1, "tonight"),
        _starting(1, 1_000.0),  # not the serialized form
        _starting(1, _iso(NOW - 60), status="completed"),
        _starting(1, _iso(NOW - 60), kind="futures"),
    ],
    ids=["future", "missing", "unparseable", "number", "completed", "futures"],
)
def test_a_card_that_cannot_prove_a_missed_kickoff_keeps_the_ordinary_bound(card):
    items = [_item(i) for i in range(3)] + [card]
    assert base_from_last_good(_base(items, age_s=240), now=NOW)[0]
    assert not base_has_started_scheduled_game(
        json.loads(wire_decode(_base(items, age_s=240))), now=NOW
    )


def test_a_naive_start_is_utc_whatever_the_process_timezone(monkeypatch):
    """CI runs in UTC, where reading a naive stamp as local time is invisible.
    West of UTC, local reading puts a start that passed 60 s ago hours ahead."""
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    time.tzset()
    try:
        naive = _iso(NOW - 60).replace("+00:00", "")
        wire = _base([_item(1), _starting(2, naive)], age_s=240)
        assert base_from_last_good(wire, now=NOW) == (None, None)
    finally:
        monkeypatch.undo()
        time.tzset()


def test_the_kickoff_is_judged_at_the_readers_clock_not_the_builds():
    """The same bytes: served before the game starts, refused after it."""
    start = NOW + 100
    wire = _base([_item(1), _starting(2, _iso(start))], age_s=240)
    assert base_from_last_good(wire, now=start - 1)[0]
    assert base_from_last_good(wire, now=start) == (None, None)


_w = encode_base_last_good


@pytest.mark.parametrize(
    "raw",
    [
        None,
        b"not zlib",
        # A predecessor's (or a typo's) uncompressed JSON is not our wire form.
        json.dumps({"items": [_item(1)], "total": 1, FEED_PAGE_BASE_BUILT_AT_FIELD: NOW}),
        _w("not json"),
        _w(json.dumps([1, 2])),
        # No stored origin: the age cannot be bounded.
        _w(json.dumps({"items": [_item(1)], "total": 1})),
        # Truncated: the slicer's rule — total must equal the deck.
        _w(json.dumps({"items": [_item(1)], "total": 2, FEED_PAGE_BASE_BUILT_AT_FIELD: NOW})),
        _w(json.dumps({"items": "x", "total": 1, FEED_PAGE_BASE_BUILT_AT_FIELD: NOW})),
    ],
)
def test_anything_unvouchable_is_refused(raw):
    assert base_from_last_good(raw, now=NOW) == (None, None)


def test_the_stored_copy_is_compressed():
    body = json.dumps(
        {"items": [_item(i) for i in range(100)], "total": 100,
         FEED_PAGE_BASE_BUILT_AT_FIELD: NOW}
    )
    wire = encode_base_last_good(body)
    assert len(wire) < len(body) / 3
    base, origin = base_from_last_good(wire, now=NOW + 1)
    assert base["total"] == 100 and origin == NOW


def test_the_copy_is_kept_no_longer_than_it_may_be_served():
    assert feed_page_base_last_good_max_age_s(live=True) == (
        FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS
    )
    assert feed_page_base_last_good_max_age_s(live=False) == (
        FEED_PAGE_BASE_LAST_GOOD_MAX_AGE_SECONDS
    )
    assert feed_page_base_last_good_key("feed_cache:pagebase:abc") == (
        "feed_cache:pagebase:abc:last_good"
    )


# --- the route: publish ------------------------------------------------------


@pytest.mark.parametrize(
    "cards, ttl",
    [
        ([_upcoming(1), _upcoming(2)], FEED_PAGE_BASE_LAST_GOOD_MAX_AGE_SECONDS),
        ([_card(1), _card(2)], FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS),
    ],
)
async def test_a_complete_build_publishes_the_durable_copy_with_its_bound(
    monkeypatch, rig, cards, ttl
):
    db = _StageSession(cards)
    redis = _StoreRedis()
    await _get(monkeypatch, db, redis, score=_score(db), enrich=_enrich)
    await _drain()

    [key] = [k for k in redis.store if k.endswith(FEED_PAGE_BASE_LAST_GOOD_SUFFIX)]
    base_key = key[: -len(FEED_PAGE_BASE_LAST_GOOD_SUFFIX)]
    assert wire_decode(redis.store[key]) == redis.store[base_key], (
        "the same body as the base"
    )
    assert redis.ttls[key] == ttl


# --- the route: the incomplete-build terminal --------------------------------


@pytest.mark.parametrize("path", [DISCOVER, SPORTS])
async def test_a_fresh_process_serves_the_durable_copy_when_events_time_out(
    monkeypatch, rig, path
):
    complete, _, redis, key = await _durable_copy_after_a_complete_build(
        monkeypatch, [_upcoming(1), _upcoming(2)], path=path
    )
    # Four minutes old: the measured outages' age, inside the 30-minute bound.
    origin = _age_copy(redis, key, 240)
    _reset_spies(rig)
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _StageSession([_upcoming(1), _upcoming(2), _upcoming(3)], stall=SCORE)
    rig.db = db

    resp = await _get(monkeypatch, db, redis, path=path, score=_score(db), enrich=_enrich)
    body = resp.json()

    assert f"{SCORE}_cancelled" in db.log, "the build really did time out"
    assert resp.headers["x-feed-cache"] == "last_good"
    assert resp.headers["x-feed-singleflight"] == "none"
    assert "cache_shared_last_good=" in resp.headers["x-feed-stages"]
    assert body["cache"]["status"] == "last_good"
    assert body["cache"]["reason"] == "events_timeout"
    assert body["cache"]["built_at"] == pytest.approx(origin)
    assert body["cache"]["live"] is False
    assert _ids(body) == _ids(complete) == [1, 2], "the prior page, not the new build"
    # Still an incomplete build: nothing shared, waiters released empty-handed,
    # and the copy is not promoted into the unbounded process store.
    assert rig.remembered == [] and rig.published == [] and redis.setex_keys == []
    assert rig.finished == ["None"]
    assert rc._inflight == {}


async def test_process_local_last_good_still_wins_over_the_durable_copy(
    monkeypatch, rig
):
    # Unseated: a seated request admits no process-local last-good (#5105).
    _, _, redis, key = await _durable_copy_after_a_complete_build(
        monkeypatch, [_upcoming(1), _upcoming(2)], path=SPORTS
    )
    # A different, complete prior in THIS process, under the same response key.
    db_prior = _StageSession([_upcoming(7)])
    await _get(monkeypatch, db_prior, _Redis(), score=_score(db_prior), enrich=_enrich)
    assert rc._last_good
    _reset_spies(rig)
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _StageSession([_upcoming(1)], stall=SCORE)

    body = (
        await _get(monkeypatch, db, redis, score=_score(db), enrich=_enrich)
    ).json()

    assert body["cache"]["status"] == "last_good"
    assert _ids(body) == [7]
    assert feed_page_base_last_good_key(key[: -len(FEED_PAGE_BASE_LAST_GOOD_SUFFIX)]) not in (
        redis.reads
    ), "the durable copy is not even read when the process holds one"


@pytest.mark.parametrize(
    "cards, age_s",
    [
        ([_upcoming(1)], FEED_PAGE_BASE_LAST_GOOD_MAX_AGE_SECONDS + 5),
        ([_card(1)], FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS + 5),
    ],
    ids=["past-thirty-minutes", "live-past-the-ceiling"],
)
async def test_a_copy_past_its_bound_keeps_the_truthful_unavailable(
    monkeypatch, rig, cards, age_s
):
    _, _, redis, key = await _durable_copy_after_a_complete_build(monkeypatch, cards)
    _age_copy(redis, key, age_s)
    _reset_spies(rig)
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _StageSession(cards, stall=SCORE)

    resp = await _get(monkeypatch, db, redis, score=_score(db), enrich=_enrich)
    body = resp.json()

    assert body["cache"]["status"] == "unavailable"
    assert body["cache"]["reason"] == "events_timeout"
    assert body["items"] == []


@pytest.mark.parametrize("path", [DISCOVER, SPORTS])
@pytest.mark.parametrize("kicked_off", [True, False], ids=["kicked-off", "not-yet"])
async def test_a_copy_whose_game_kicked_off_since_the_build_is_not_served(
    monkeypatch, rig, path, kicked_off
):
    """Four minutes old, inside the 30-minute bound, but one of its games has
    started since the build and the copy still calls it scheduled. The control
    is the same copy with the start still ahead: it is served."""
    start = time.time() + (-60 if kicked_off else 3600)
    cards = [_upcoming(1), _upcoming(2)]
    cards[1]["data"] = {**cards[1]["data"], "commence_time": _iso(start)}
    _, _, redis, key = await _durable_copy_after_a_complete_build(
        monkeypatch, cards, path=path
    )
    assert "commence_time" in json.dumps(json.loads(wire_decode(redis.store[key])))
    _age_copy(redis, key, 240)
    _reset_spies(rig)
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _StageSession(cards, stall=SCORE)

    resp = await _get(monkeypatch, db, redis, path=path, score=_score(db), enrich=_enrich)
    body = resp.json()

    assert f"{SCORE}_cancelled" in db.log
    if kicked_off:
        assert body["cache"]["status"] == "unavailable"
        assert body["items"] == []
    else:
        assert body["cache"]["status"] == "last_good"
        assert _ids(body) == [1, 2]
    assert rig.remembered == [] and rig.published == [] and redis.setex_keys == []


async def test_an_unseated_pinned_request_admits_no_durable_copy(monkeypatch, rig):
    """An unseated pin is an ORDER minted from some earlier build; the base
    tier applies it from a manifest, and this terminal does not try to."""
    _, _, redis, _ = await _durable_copy_after_a_complete_build(
        monkeypatch, [_upcoming(1), _upcoming(2)], path=SPORTS
    )
    _reset_spies(rig)
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _StageSession([_upcoming(1)], stall=SCORE)

    body = (
        await _get(
            monkeypatch,
            db,
            redis,
            path=SPORTS + "&edition=e-old",
            score=_score(db),
            enrich=_enrich,
        )
    ).json()

    assert body["cache"]["status"] == "unavailable"
    assert body["items"] == []


async def test_a_session_leader_with_an_empty_context_is_served_the_copy(
    monkeypatch, rig
):
    """The leader asks the base's own question (an empty personalization
    context), so a session that has interacted with nothing is the anonymous
    build and gets the copy."""
    _, _, redis, _ = await _durable_copy_after_a_complete_build(
        monkeypatch, [_upcoming(1), _upcoming(2)]
    )
    _reset_spies(rig)
    monkeypatch.setattr("app.routes.feed._session_id_from_request", lambda r: "s-1")
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _StageSession([_upcoming(1)], stall=SCORE)

    body = (
        await _get(
            monkeypatch, db, redis, path=DISCOVER, score=_score(db), enrich=_enrich
        )
    ).json()

    assert body["cache"]["status"] == "last_good"
    assert _ids(body) == [1, 2]


async def test_a_seated_discover_page_is_the_page_the_base_tier_would_serve(
    monkeypatch, rig
):
    """Web Discover is SEATED (#5105), and it is the page that went empty in
    production. The durable copy is the base's own body, so the page it serves
    must be the one the page-base read tier serves for that same body:
    composed at this request's clock, same cards, same edition envelope."""
    complete, published, redis, key = await _durable_copy_after_a_complete_build(
        monkeypatch, [_upcoming(1), _upcoming(2)]
    )
    base_key = key[: -len(FEED_PAGE_BASE_LAST_GOOD_SUFFIX)]
    _reset_spies(rig)
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _StageSession([_upcoming(1)], stall=SCORE)
    durable = (
        await _get(
            monkeypatch, db, redis, path=DISCOVER, score=_score(db), enrich=_enrich
        )
    ).json()

    rc._reset_last_good_for_tests()
    base_tier = (
        await _get(
            monkeypatch,
            _StageSession([_upcoming(9)]),
            _StoreRedis({base_key: published.store[base_key]}),
            path=DISCOVER,
        )
    ).json()

    assert durable["cache"]["status"] == "last_good"
    assert base_tier["cache"]["status"] == "page_base_hit"
    strip = lambda body: {k: v for k, v in body.items() if k != "cache"}  # noqa: E731
    assert strip(durable) == strip(base_tier)
    assert durable.get("edition"), "the seated envelope is applied"
    assert _ids(durable) == _ids(complete) == [1, 2]


# --- the route: a coalesced waiter -------------------------------------------


async def _leader_and_waiter(monkeypatch, rig, redis, *, path=DISCOVER):
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _StageSession([_upcoming(1)], stall=SCORE)
    rig.db = db

    async def _after_leader_stalls():
        await asyncio.wait_for(db.stage_entered.wait(), timeout=10)

    leader, waiter = await _get(
        monkeypatch,
        db,
        redis,
        path=path,
        n=2,
        stagger=_after_leader_stalls,
        score=_score(db),
        enrich=_enrich,
    )
    assert db.log.count(f"{SCORE}_sql") == 1, "the waiter never built"
    return leader, waiter


async def test_an_anonymous_waiter_is_served_the_copy_its_leader_would_serve(
    monkeypatch, rig
):
    complete, _, redis, _ = await _durable_copy_after_a_complete_build(
        monkeypatch, [_upcoming(1), _upcoming(2)]
    )
    _reset_spies(rig)

    leader, waiter = await _leader_and_waiter(monkeypatch, rig, redis)

    assert leader.json()["cache"]["status"] == "last_good"
    assert waiter.headers["x-feed-singleflight"] == "waiter_last_good"
    assert waiter.json()["cache"]["status"] == "last_good"
    assert waiter.json()["cache"]["reason"] == "leader_unavailable"
    # The waiter derives the base key without a context; it must be the key
    # the leader published under, or it would read nothing (or another list).
    assert _ids(waiter.json()) == _ids(leader.json()) == _ids(complete)
    assert rig.remembered == [] and rig.published == [] and redis.setex_keys == []
    assert rc._inflight == {}


async def test_a_waiter_not_anonymous_by_identity_keeps_waiter_unavailable(
    monkeypatch, rig
):
    _, _, redis, _ = await _durable_copy_after_a_complete_build(
        monkeypatch, [_upcoming(1), _upcoming(2)]
    )
    _reset_spies(rig)
    monkeypatch.setattr("app.routes.feed._session_id_from_request", lambda r: "s-1")

    _, waiter = await _leader_and_waiter(monkeypatch, rig, redis)

    assert waiter.headers["x-feed-singleflight"] == "waiter_unavailable"
    assert waiter.json()["items"] == []


# --- the two callers that must keep their existing terminal -------------------


async def test_the_warm_rail_never_takes_the_durable_copy(monkeypatch, rig):
    """LAT-P001: the warmer must genuinely build. A warmer handed a cached page
    reports success and refreshes nothing. The rig cannot set the ASGI-scope
    marker, so the marker's name is pointed at a scope key every request has."""
    import app.routes.feed as feed

    _, _, redis, _ = await _durable_copy_after_a_complete_build(
        monkeypatch, [_upcoming(1), _upcoming(2)], path=SPORTS
    )
    _reset_spies(rig)
    monkeypatch.setattr(feed, "FEED_PREWARM_SCOPE_KEY", "type")
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _StageSession([_upcoming(1)], stall=SCORE)

    body = (
        await _get(monkeypatch, db, redis, path=SPORTS, score=_score(db), enrich=_enrich)
    ).json()

    assert body["cache"]["status"] == "unavailable"
    assert body["cache"]["reason"] == "events_timeout"


async def test_a_finished_build_whose_deck_cannot_be_seated_keeps_its_refusal(
    monkeypatch, rig
):
    """`opening_unsupported` is a content outcome of a build that FINISHED, not
    a missed budget; an older deck is not substituted for it. The composer is
    refused for the build only, so the durable copy WOULD compose — the test
    can tell the opt-out from a copy that merely failed to seat."""
    import types

    import app.routes.feed as feed

    _, _, redis, _ = await _durable_copy_after_a_complete_build(
        monkeypatch, [_upcoming(1), _upcoming(2)]
    )
    _reset_spies(rig)
    real_compose = feed.compose_opening_edition
    calls = []

    def compose(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            return types.SimpleNamespace(usable=False)
        return real_compose(*a, **k)

    monkeypatch.setattr(feed, "compose_opening_edition", compose)
    db = _StageSession([_upcoming(3)])

    body = (
        await _get(
            monkeypatch, db, redis, path=DISCOVER, score=_score(db), enrich=_enrich
        )
    ).json()

    assert calls, "the build reached the composer"
    assert body["cache"]["status"] == "unavailable"
    assert body["cache"]["reason"] == "opening_unsupported"
    assert body["items"] == []

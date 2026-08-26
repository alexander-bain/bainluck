"""#2216 — a feed page holding a LIVE card may not be served past the live ceiling.

## The defect these tests pin

2026-08-25, ~15:55 PT. The push alert for the live Boston @ Miami game carried
the true **1-0**. My Stuff, open at the same moment, drew **0-0** on its cards.
The DB held 0-1 and ``GET /api/events/{id}`` served 0-1. So the write side was
correct and *the card's read path served an older payload as current*.

The cause is not ingestion and not linkage. It is that the feed's response cache
had no relationship to what it was caching:

* the cache KEY (``feed_response_cache_key``) contains nothing about any event's
  state, so a score changing cannot invalidate it, and
* the TTL was chosen from the PRINCIPAL alone — 60s anon / 30s my-teams / 5s
  identified — plus a flat 300s ``:stale`` mirror and an UNBOUNDED process-local
  last-good behind that.

``GET /api/events/{id}`` never had this bug: it stores ``event.status`` beside
the cached response and picks its TTL from it (``routes/events.py:1841``,
``:5771-5773``). **The endpoint Alex tapped into was live-aware and the one that
drew the card he was looking at was not.** That asymmetry is the whole finding,
and closing it is the whole fix.

## What "fixed" means, as a number

**60 seconds is the live ceiling** — the oldest a payload containing a live card
may be and still be served — with the fresh window at 30s, mirroring
``_EVENT_DETAIL_LIVE_TTL`` exactly. Past the ceiling the page is REBUILT, not
served older.

## Why these tests are shaped the way they are

The ceiling has to hold at *every* point a TTL is chosen, and there are four
writers, not one: the request path's publish, the LAT-P089 inert-principal
private backfill, the pre-warm beat, and the process-local last-good store. A
test that only covered the obvious publish would pass while the surface that
reported the bug stayed broken — My Stuff is an identified request with a
default personalization context, so it goes through the *backfill*, and the
anonymous Discover key is republished on a beat by the *warmer*. So each writer
gets its own test, and ``test_no_writer_publishes_an_unconditional_stale_ttl``
fails if a fifth one appears.
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import app.utils.request_cache as rc
from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils.feed_cache import (
    FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS,
    FEED_RESPONSE_STALE_TTL_LIVE_SECONDS,
    FEED_RESPONSE_STALE_TTL_SECONDS,
    FEED_RESPONSE_TTL_ANON_SECONDS,
    FEED_RESPONSE_TTL_IDENTIFIED_SECONDS,
    FEED_RESPONSE_TTL_LIVE_SECONDS,
    FEED_RESPONSE_TTL_MY_TEAMS_SECONDS,
    build_feed_cache_metadata,
    feed_response_cache_key,
    feed_response_cache_ttl,
    feed_response_cache_ttls,
    payload_contains_live_event,
)

# ---------------------------------------------------------------------------
# Payloads. `_page` builds the real response shape: a list of {type, data}
# cards, where an event card carries `data.status`.
# ---------------------------------------------------------------------------


def _card(kind: str, oid: int, status: str | None = None) -> dict:
    data: dict = {"id": oid, "name": f"card-{oid}"}
    if status is not None:
        data["status"] = status
    return {"type": kind, "data": data}


def _page(*cards: dict) -> dict:
    return {
        "items": list(cards),
        "total": len(cards),
        "limit": 200,
        "offset": 0,
        "has_more": False,
    }


LIVE_PAGE = _page(
    _card("futures", 1),
    _card("event", 2, "live"),
    _card("event", 3, "upcoming"),
)
SETTLED_PAGE = _page(
    _card("futures", 1),
    _card("event", 2, "completed"),
    _card("event", 3, "upcoming"),
)


# ---------------------------------------------------------------------------
# The predicate
# ---------------------------------------------------------------------------


def test_one_live_card_makes_the_whole_page_live():
    """A page is only as fresh as its fastest-moving card."""
    assert payload_contains_live_event(LIVE_PAGE) is True
    assert payload_contains_live_event(SETTLED_PAGE) is False
    assert payload_contains_live_event(_page()) is False


def test_liveness_is_not_gated_on_the_card_type():
    """No allowlist. Any card declaring itself live counts.

    A new card type that carries a live score must shorten the page's life on
    the day it ships, not on the day somebody remembers to add it here.
    """
    assert payload_contains_live_event(_page(_card("concept", 9, "live"))) is True
    assert payload_contains_live_event(_page(_card("tournament", 9, "live"))) is True


def test_an_unparseable_payload_is_not_live():
    """Fails toward the ORDINARY ttl, which is the safe direction.

    This function only ever SHORTENS a TTL. Failing closed would hand a
    malformed payload the long TTL silently; failing open would expire every
    page it cannot parse in 30s. Neither is free, and the second is worse.
    """
    for junk in (None, [], "items", 7, {"items": "not-a-list"}, {}):
        assert payload_contains_live_event(junk) is False
    # Individual junk ITEMS are skipped, not fatal, and do not mask a real one.
    assert payload_contains_live_event({"items": [None, "x", 3]}) is False
    assert (
        payload_contains_live_event({"items": [None, _card("event", 1, "live")]})
        is True
    )


# ---------------------------------------------------------------------------
# The ceiling arithmetic
# ---------------------------------------------------------------------------


def test_the_live_ceiling_is_the_detail_routes_live_ttl():
    """30s fresh is not a new number — it is the one the detail route uses.

    The two routes read the SAME ORM fields. Two different answers about one
    score is the defect, so they get one staleness rule; pin the equality so a
    future edit to either constant has to face the other.
    """
    from app.routes.events import _EVENT_DETAIL_LIVE_TTL

    assert FEED_RESPONSE_TTL_LIVE_SECONDS == _EVENT_DETAIL_LIVE_TTL == 30
    assert FEED_RESPONSE_STALE_TTL_LIVE_SECONDS == 60
    assert FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS == 60


def test_a_live_page_is_bounded_at_sixty_seconds_for_every_principal():
    for kwargs in (
        dict(),
        dict(identified=True),
        dict(my_teams_only=True),
        dict(my_teams_only=True, identified=True),
    ):
        fresh, stale = feed_response_cache_ttls(live=True, **kwargs)
        assert fresh <= FEED_RESPONSE_TTL_LIVE_SECONDS
        assert stale <= FEED_RESPONSE_STALE_TTL_LIVE_SECONDS
        assert fresh + stale <= 90, (
            "the worst-case age of a served live page must stay inside the "
            f"declared ceiling; got fresh={fresh} stale={stale} for {kwargs}"
        )


def test_the_ceiling_is_a_min_and_never_lengthens_a_ttl():
    """A correctness fix that made somebody's cache LIVE LONGER is a latency
    fix wearing the wrong clothes. The 5s identified TTL must survive at 5s."""
    for kwargs in (
        dict(),
        dict(identified=True),
        dict(my_teams_only=True),
        dict(my_teams_only=True, identified=True),
    ):
        baseline = feed_response_cache_ttl(**kwargs)
        live_fresh, live_stale = feed_response_cache_ttls(live=True, **kwargs)
        assert live_fresh <= baseline
        assert live_stale <= FEED_RESPONSE_STALE_TTL_SECONDS
    assert feed_response_cache_ttls(identified=True, live=True)[0] == (
        FEED_RESPONSE_TTL_IDENTIFIED_SECONDS
    )


def test_a_page_with_no_live_card_is_completely_unchanged():
    """The blast radius is exactly 'pages holding a live game' and nothing else."""
    assert feed_response_cache_ttls() == (
        FEED_RESPONSE_TTL_ANON_SECONDS,
        FEED_RESPONSE_STALE_TTL_SECONDS,
    )
    assert feed_response_cache_ttls(identified=True) == (
        FEED_RESPONSE_TTL_IDENTIFIED_SECONDS,
        FEED_RESPONSE_STALE_TTL_SECONDS,
    )
    assert feed_response_cache_ttls(my_teams_only=True) == (
        FEED_RESPONSE_TTL_MY_TEAMS_SECONDS,
        FEED_RESPONSE_STALE_TTL_SECONDS,
    )


def test_the_cache_block_stays_byte_identical_when_liveness_is_unknown():
    """`live` is emitted only when known, so untouched callers keep their shape."""
    assert build_feed_cache_metadata("miss", ttl_seconds=60) == {
        "status": "miss",
        "ttl_seconds": 60,
        "stale_ttl_seconds": FEED_RESPONSE_STALE_TTL_SECONDS,
    }
    assert build_feed_cache_metadata("hit", ttl_seconds=30, live=True)["live"] is True
    assert build_feed_cache_metadata("hit", ttl_seconds=60, live=False)["live"] is False


# ---------------------------------------------------------------------------
# Writer 1 + 2 — the request path (publish, and the LAT-P089 private backfill)
# ---------------------------------------------------------------------------

_SESSION_ID = "live-ceiling-install-uuid-2216"

_BARE_FEED_SHAPE = dict(
    sport=None,
    limit=200,
    offset=0,
    include_events=True,
    include_futures=True,
    tags=None,
    event_pct=0.15,
    my_teams_only=False,
    mode="discover",
)

SHARED_KEY = feed_response_cache_key(user_id=None, session_id=None, **_BARE_FEED_SHAPE)
PRIVATE_KEY = feed_response_cache_key(
    user_id=None, session_id=_SESSION_ID, **_BARE_FEED_SHAPE
)


def _event_row(oid: int):
    row = MagicMock()
    row.id = oid
    row.home_team = "Celtics"
    row.away_team = "76ers"
    row.status = "live"
    row.sport_key = "basketball_nba"
    row.sport_id = 1
    row.sport_name = "Basketball"
    row.commence_time = datetime.now(timezone.utc) - timedelta(hours=1)
    row.completed_at = None
    row.home_score = 55
    row.away_score = 52
    row.external_id = f"ext-{oid}"
    row.win_probability_sources = {"betting": {"home_probability": 0.55}}
    row.current_home_probability = 0.55
    row.current_away_probability = 0.45
    row.espn_game_id = None
    row.espn_data = None
    row.event_tags = []
    row.pulse_score = None
    row.pulse_label = None
    row.excite_index = None
    row.home_team_id = None
    row.away_team_id = None
    return row


def _seeded_session(events):
    session = AsyncMock()

    def make_result(data):
        result = MagicMock()
        result.scalars.return_value.all.return_value = data or []
        result.scalars.return_value.first.return_value = (
            (data or [None])[0] if data else None
        )
        result.scalar_one_or_none.return_value = None
        result.scalar.return_value = len(data) if data else 0
        result.fetchall.return_value = data or []
        result.all.return_value = [(r,) for r in (data or [])]
        result.first.return_value = None
        return result

    empty = MagicMock()
    empty.scalars.return_value.all.return_value = []
    empty.scalars.return_value.first.return_value = None
    empty.scalar_one_or_none.return_value = None
    empty.scalar.return_value = 0
    empty.fetchall.return_value = []
    empty.all.return_value = []
    empty.first.return_value = None

    async def mock_execute(stmt, *args, **kwargs):
        s = str(stmt).lower()
        if "events" in s and events:
            return make_result(events)
        return empty

    session.execute = AsyncMock(side_effect=mock_execute)
    session.rollback = AsyncMock()
    return session


class _SeededRedis:
    """Shared-redis stand-in holding key -> raw JSON body, recording setex."""

    def __init__(self, contents: dict[str, str] | None = None, *, fail: bool = False):
        self.contents = dict(contents or {})
        self.setex_calls: list[tuple[str, int, str]] = []
        self.fail = fail

    async def get(self, key):
        if self.fail:
            raise ConnectionError("redis is down")
        return self.contents.get(key)

    async def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self.contents[key] = value
        return True


async def _drive_feed(*, redis, monkeypatch, headers=None):
    from app.main import app

    session = _seeded_session([_event_row(1)])

    async def _mock_get_db():
        yield session

    async def _mock_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_user

    async def _no_futures(*a, **k):
        return []

    monkeypatch.setattr(rc, "schedule_background", lambda coro: asyncio.ensure_future(coro))

    async def _get_redis():
        return redis

    monkeypatch.setattr(rc, "get_shared_async_redis", _get_redis)

    try:
        with patch("app.main.init_db", new_callable=AsyncMock), patch(
            "app.routes.feed._score_futures", new=AsyncMock(side_effect=_no_futures)
        ), patch(
            "app.routes.feed._score_sports_mode_futures",
            new=AsyncMock(side_effect=_no_futures),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/api/feed", headers=headers or {})
    finally:
        app.dependency_overrides.clear()
    # Let the detached publish coroutines run.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    return resp


@pytest.mark.asyncio
async def test_the_private_backfill_applies_the_live_ceiling(monkeypatch):
    """THE regression test for the surface that reported the bug.

    My Stuff is an IDENTIFIED request whose personalization context is inert,
    so it takes the LAT-P089 share and republishes the payload under its own
    private key. A fix that landed only on the main publish would leave this
    writer on 60s/300s and Alex would still see the old score.
    """
    rc._reset_last_good_for_tests()
    redis = _SeededRedis({f"{SHARED_KEY}:stale": json.dumps(LIVE_PAGE)})

    resp = await _drive_feed(
        redis=redis, monkeypatch=monkeypatch, headers={"x-session-id": _SESSION_ID}
    )
    assert resp.status_code == 200

    written = {key: ttl for key, ttl, _ in redis.setex_calls}
    assert PRIVATE_KEY in written, "private mirror not backfilled at all"
    assert written[PRIVATE_KEY] <= FEED_RESPONSE_TTL_LIVE_SECONDS
    assert written[f"{PRIVATE_KEY}:stale"] == FEED_RESPONSE_STALE_TTL_LIVE_SECONDS, (
        "a page holding a live game was mirrored at the futures staleness "
        "ceiling — this is the 1-0-vs-0-0 defect exactly"
    )
    assert resp.json()["cache"]["live"] is True


@pytest.mark.asyncio
async def test_a_settled_page_keeps_the_long_mirror(monkeypatch):
    """The control. Without it, 'bounded' could just mean 'broke the cache'."""
    rc._reset_last_good_for_tests()
    redis = _SeededRedis({f"{SHARED_KEY}:stale": json.dumps(SETTLED_PAGE)})

    resp = await _drive_feed(
        redis=redis, monkeypatch=monkeypatch, headers={"x-session-id": _SESSION_ID}
    )
    assert resp.status_code == 200

    written = {key: ttl for key, ttl, _ in redis.setex_calls}
    assert written[f"{PRIVATE_KEY}:stale"] == FEED_RESPONSE_STALE_TTL_SECONDS
    assert resp.json()["cache"]["live"] is False


# ---------------------------------------------------------------------------
# Writer 3 — the process-local last-good store
# ---------------------------------------------------------------------------


def test_last_good_is_unbounded_for_futures_and_bounded_for_live(monkeypatch):
    """Unbounded last-good is defensible for a page of futures. It is not
    defensible for an in-progress score, and 'Redis blipped' is not a licence
    to print a stale one as current."""
    import time as _time

    rc._reset_last_good_for_tests()
    rc.remember_last_good("k:settled", SETTLED_PAGE)
    rc.remember_last_good("k:live", LIVE_PAGE)

    # Age both far past the live ceiling without sleeping.
    old = _time.time() - (FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS + 120)
    for key in ("k:settled", "k:live"):
        _, payload = rc._last_good[key]
        rc._last_good[key] = (old, payload)

    assert rc.recall_last_good("k:settled") is not None
    assert (
        rc.recall_last_good("k:live", max_age_s=FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS)
        is None
    ), "an hour-old live page must be refused, not served"
    # Fresh again -> served. The bound is on AGE, not on liveness itself.
    rc.remember_last_good("k:live", LIVE_PAGE)
    assert (
        rc.recall_last_good("k:live", max_age_s=FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS)
        is not None
    )


@pytest.mark.asyncio
async def test_redis_down_rebuilds_rather_than_serving_a_stale_live_page(monkeypatch):
    """End-to-end: Redis errors, the only last-good is an aged LIVE page.

    Before #2216 this returned that page with ``cache.status == "last_good"``
    and no upper bound on its age. It must now fall through to a real build.
    """
    import time as _time

    rc._reset_last_good_for_tests()
    rc.remember_last_good(SHARED_KEY, LIVE_PAGE)
    _, payload = rc._last_good[SHARED_KEY]
    rc._last_good[SHARED_KEY] = (
        _time.time() - (FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS + 120),
        payload,
    )

    resp = await _drive_feed(redis=_SeededRedis(fail=True), monkeypatch=monkeypatch)

    assert resp.status_code == 200
    assert resp.headers.get("x-feed-cache") != "last_good", (
        "a live page well past the ceiling was served from last-good; the "
        "unbounded-staleness half of #2216 is still open"
    )


# ---------------------------------------------------------------------------
# Writer 4 — the pre-warm beat, and the guard against a fifth writer
# ---------------------------------------------------------------------------


def test_the_prewarm_beat_publishes_under_the_live_ceiling():
    """The warmer REPUBLISHES on a beat, so a warmer left on the principal TTLs
    would keep the anonymous Discover key — and a live score inside it — alive
    at up to 360s indefinitely. Same two-writers-drifting shape LAT-P001 closed
    on the key builder."""
    import inspect

    import app.tasks.precompute_category_pages as pcp

    body = inspect.getsource(pcp._prewarm_feed_shape)
    assert "feed_response_cache_ttls(" in body, (
        "the pre-warm beat no longer derives its TTLs from the shared "
        "live-aware helper — it has drifted from the request path"
    )
    assert "payload_contains_live_event(payload)" in body
    assert "FEED_RESPONSE_STALE_TTL_SECONDS" not in body, (
        "the warmer still writes the flat 300s mirror somewhere"
    )


# ---------------------------------------------------------------------------
# CERT-409 [P1] — a cache-tier copy must not restart the payload's age clock
# ---------------------------------------------------------------------------


def test_a_redis_hit_does_not_launder_an_aged_payload_into_a_fresh_window():
    """The cert's executable falsifier, kept as the regression test.

    Read at t=59, remembered, recalled at t=118 under a declared 60s ceiling.
    Pre-fix this returned the payload — `remember_last_good` stamped its own
    read time, so a 59-second-old score got a brand-new 60-second window and
    was served at 118 seconds under a branch that says 60 is the maximum.
    """
    import app.utils.request_cache as rc
    from app.utils.feed_cache import (
        FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS as CEILING,
    )

    rc._reset_last_good_for_tests()

    fake_now = {"t": 0.0}
    real_time = rc.time.time
    rc.time.time = lambda: fake_now["t"]
    try:
        built_at = 0.0  # the payload's CONTENT was computed at t=0
        payload = {"items": [], "cache": {"status": "hit", "built_at": built_at}}

        fake_now["t"] = 59.0  # ...and this process reads it out of Redis at t=59
        rc.remember_last_good("k", payload, built_at=built_at)

        fake_now["t"] = 118.0
        recalled = rc.recall_last_good("k", max_age_s=CEILING)
    finally:
        rc.time.time = real_time
        rc._reset_last_good_for_tests()

    assert recalled is None, (
        f"a payload built at t=0 was served at t=118 under a {CEILING}s "
        "ceiling — the Redis hit reset its age (CERT-409 [P1])"
    )


def test_a_genuinely_fresh_build_still_uses_the_full_window():
    """The other direction: provenance must not make the ceiling stricter.

    Without this, "always refuse" would pass the test above and silently
    disable last-good entirely — the fallback that exists so a Redis blip is
    not a stampede of cold builds.
    """
    import app.utils.request_cache as rc
    from app.utils.feed_cache import (
        FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS as CEILING,
    )

    rc._reset_last_good_for_tests()

    fake_now = {"t": 0.0}
    real_time = rc.time.time
    rc.time.time = lambda: fake_now["t"]
    try:
        rc.remember_last_good("k", {"items": []}, built_at=0.0)
        fake_now["t"] = CEILING - 1
        recalled = rc.recall_last_good("k", max_age_s=CEILING)
    finally:
        rc.time.time = real_time
        rc._reset_last_good_for_tests()

    assert recalled is not None, (
        "a payload built 59s ago was refused under a 60s ceiling — the live "
        "fallback is now stricter than the rule it enforces"
    )


def test_a_payload_with_no_provenance_falls_back_to_read_time():
    """The rollout window, pinned. Entries published before `built_at` existed
    carry no provenance; they must behave exactly as they did pre-fix rather
    than being refused (which would empty last-good on deploy) or trusted
    forever (which would be the bug with extra steps)."""
    import app.utils.request_cache as rc

    rc._reset_last_good_for_tests()

    fake_now = {"t": 1000.0}
    real_time = rc.time.time
    rc.time.time = lambda: fake_now["t"]
    try:
        rc.remember_last_good("k", {"items": []}, built_at=None)
        fake_now["t"] = 1030.0
        within = rc.recall_last_good("k", max_age_s=60)
        fake_now["t"] = 1100.0
        beyond = rc.recall_last_good("k", max_age_s=60)
    finally:
        rc.time.time = real_time
        rc._reset_last_good_for_tests()

    assert within is not None
    assert beyond is None


def test_the_route_stamps_build_provenance_and_carries_it_across_tiers():
    """The wiring, asserted at the route rather than the helper.

    A correct `remember_last_good` is worthless if the route never passes
    `built_at`. Every cache-tier copy site must forward provenance; only the
    build site may mint it.
    """
    import ast
    import inspect
    import textwrap

    import app.routes.feed as feed_module

    tree = ast.parse(textwrap.dedent(inspect.getsource(feed_module.get_feed)))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "remember_last_good"
    ]
    assert calls, "no `remember_last_good` calls found — test premise is stale"

    missing = [
        ast.unparse(call)
        for call in calls
        if not any(kw.arg == "built_at" for kw in call.keywords)
    ]
    assert missing == [], (
        f"{len(missing)} `remember_last_good` call(s) in `get_feed` do not pass "
        f"`built_at`, so they re-stamp the payload's age: {missing}"
    )


def _setex_ttls_not_derived_from_live_helper(source: str) -> list[str]:
    """Every ``setex`` TTL in ``source`` that is NOT bound to ``_live_ttls``.

    CERT-409 [P2]. The previous version of this guard asserted
    ``src.count("_live_ttls(") >= 5`` and that a constant name was absent.
    Neither statement is about the ``setex`` calls, so appending a fifth writer
    with an unconditional TTL left both true and the guard green — the guard
    was self-oracular: it measured its own vocabulary, not the property.

    So enumerate the writers instead of counting the helper. Names bound by
    ``a, b = _live_ttls(...)`` are live-derived; a nested ``def``'s parameter
    whose DEFAULT is a live-derived name inherits that (the closure-capture
    idiom every publisher here uses). Any ``setex`` whose TTL argument is not
    such a name is returned.
    """
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(source))

    live_derived: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        call = node.value
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)):
            continue
        if call.func.id != "_live_ttls":
            continue
        for target in node.targets:
            if isinstance(target, ast.Tuple):
                live_derived.update(
                    el.id for el in target.elts if isinstance(el, ast.Name)
                )

    # Propagate through closure-captured defaults: `def _pub(_fresh_ttl=_fresh)`.
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        positional = args.posonlyargs + args.args
        for arg, default in zip(positional[len(positional) - len(args.defaults):],
                                args.defaults):
            if isinstance(default, ast.Name) and default.id in live_derived:
                live_derived.add(arg.arg)
        for arg, default in zip(args.kwonlyargs, args.kw_defaults):
            if isinstance(default, ast.Name) and default.id in live_derived:
                live_derived.add(arg.arg)

    offenders: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != "setex" or len(node.args) < 2:
            continue
        ttl = node.args[1]
        if isinstance(ttl, ast.Name) and ttl.id in live_derived:
            continue
        offenders.append(ast.unparse(ttl))
    return offenders


def test_every_setex_writer_derives_its_ttl_from_the_live_helper():
    """The ceiling has to hold at EVERY writer — asserted over the writers."""
    import inspect

    import app.routes.feed as feed_module

    src = inspect.getsource(feed_module.get_feed)
    assert "FEED_RESPONSE_STALE_TTL_SECONDS" not in src, (
        "`get_feed` publishes or reports a flat stale TTL again; route TTLs "
        "must come from `_live_ttls`/`feed_response_cache_ttls`"
    )
    offenders = _setex_ttls_not_derived_from_live_helper(src)
    assert offenders == [], (
        f"{len(offenders)} `setex` call(s) in `get_feed` publish a TTL that is "
        f"not derived from `_live_ttls`: {offenders}. A live page cached under "
        "an unconditional TTL is the #2216 bug returning."
    )


def test_the_fifth_writer_guard_actually_fails_on_a_fifth_writer():
    """The retained mutant. CERT-409 [P2] exists because this was never proved.

    A guard is only worth its runtime if something demonstrates it can go red.
    This appends exactly the regression the guard claims to catch — a new
    publisher on the principal's baseline TTL — and requires it be caught.
    """
    import inspect

    import app.routes.feed as feed_module

    clean = inspect.getsource(feed_module.get_feed)
    assert _setex_ttls_not_derived_from_live_helper(clean) == [], "premise"

    mutant = clean + (
        "\n"
        "    async def _publish_fifth_writer(_client=None, _key='k', _json='{}'):\n"
        "        await _client.setex(_key, _cache_ttl, _json)\n"
    )
    assert _setex_ttls_not_derived_from_live_helper(mutant) == ["_cache_ttl"], (
        "the fifth-writer guard did not catch a fifth unconditional writer — "
        "it is self-oracular again"
    )

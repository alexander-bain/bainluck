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
import time as time_module
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import app.utils.principal_independent_cache as pic
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


async def _drive_feed(*, redis, monkeypatch, headers=None, during_build=None, events=None):
    """Drive one real `GET /api/feed` through the ASGI app.

    ``during_build`` (CERT-1864) is called from inside the patched futures
    scorer — a real seam that runs AFTER the shared-artifact sink is bound and
    BEFORE the publish seam. It is how a test spends measurable build time
    between consumption and publication without sleeping.
    """
    from app.main import app

    session = _seeded_session(events if events is not None else [_event_row(1)])

    async def _mock_get_db():
        yield session

    async def _mock_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_user

    async def _no_futures(*a, **k):
        if during_build is not None:
            during_build()
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


_SETEX = "setex"


def _setex_reference_kind(node) -> str | None:
    """Classify an expression that *names* a ``setex`` writer.

    ``"static"``  — ``client.setex`` / ``getattr(client, "setex")``: readable.
    ``"dynamic"`` — ``getattr(client, <computed>)``: the writer's name is not
    knowable from the source, so nothing downstream may be assumed about it.
    ``None``      — not a writer reference at all.
    """
    import ast

    if isinstance(node, ast.Attribute):
        return "static" if node.attr == _SETEX else None
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
    ):
        name_arg = node.args[1]
        if isinstance(name_arg, ast.Constant) and isinstance(name_arg.value, str):
            return "static" if name_arg.value == _SETEX else None
        return "dynamic"
    return None


def _setex_ttl_expr(node):
    """The AST node for a ``setex`` call's ``time`` argument, or ``None``.

    ``redis.Redis.setex(name, time, value)`` binds by keyword as readily as by
    position, so ``time=`` is checked FIRST and the positional index second.
    ``None`` means the TTL is not readable from the source — a ``*args`` or
    ``**kwargs`` splat — which the caller must treat as a refusal, never as a
    pass.
    """
    import ast

    for kw in node.keywords:
        if kw.arg == "time":
            return kw.value
        if kw.arg is None:  # `**kwargs` — the TTL may be inside it
            return None
    if any(isinstance(arg, ast.Starred) for arg in node.args):
        return None  # `*args` — position 1 is not pinnable
    if len(node.args) >= 2:
        return node.args[1]
    return None


def _setex_ttls_not_derived_from_live_helper(source: str) -> list[str]:
    """Every ``setex`` TTL in ``source`` that is NOT bound to ``_live_ttls``.

    CERT-409 [P2]. The first version of this guard asserted
    ``src.count("_live_ttls(") >= 5`` and that a constant name was absent.
    Neither statement is about the ``setex`` calls, so appending a fifth writer
    with an unconditional TTL left both true and the guard green — the guard
    was self-oracular: it measured its own vocabulary, not the property.

    So enumerate the writers instead of counting the helper. Names bound by
    ``a, b = _live_ttls(...)`` are live-derived; a nested ``def``'s parameter
    whose DEFAULT is a live-derived name inherits that (the closure-capture
    idiom every publisher here uses). Any ``setex`` whose TTL argument is not
    such a name is returned.

    CERT-412 [P2]. The second version enumerated writers, but only writers
    spelled ``client.setex(key, ttl, body)`` — it required an ``Attribute``
    func and two POSITIONAL args. So the keyword form ``setex(name=…, time=…,
    value=…)``, which the Redis client explicitly supports, and
    ``getattr(client, "setex")(…)``, whose func is a ``Call``, both published
    an unconditional TTL and both read back clean. Same self-oracular failure,
    two more ordinary call shapes. A guard that claims *every* ``setex`` may
    not be a guard over the subset it happens to recognize, so:

    * the ``time`` KEYWORD is read as well as positional argument 2;
    * ``getattr(client, "setex")`` is recognized as the writer it is; and
    * anything whose writer name or TTL is **unreadable** — computed
      ``getattr``, ``*args``, ``**kwargs`` — is REFUSED rather than skipped.
      This source may not dispatch its Redis writers dynamically; unreadable
      is not the same as derived (gotcha #53).
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

    # A writer bound to a name before it is called: `_w = getattr(c, "setex")`.
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        kind = _setex_reference_kind(node.value)
        if kind is None:
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                aliases[target.id] = kind

    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            kind = aliases.get(func.id)
        else:
            kind = _setex_reference_kind(func)
        if kind is None:
            continue
        if kind == "dynamic":
            offenders.append(f"<dynamic writer dispatch: {ast.unparse(func)}>")
            continue
        ttl = _setex_ttl_expr(node)
        if ttl is None:
            offenders.append(f"<unreadable TTL: {ast.unparse(node)}>")
            continue
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


def _clean_get_feed_source() -> str:
    """`get_feed`'s source, asserted clean, as the base for a mutant."""
    import inspect

    import app.routes.feed as feed_module

    clean = inspect.getsource(feed_module.get_feed)
    assert _setex_ttls_not_derived_from_live_helper(clean) == [], "premise"
    return clean


def test_the_fifth_writer_guard_catches_the_keyword_time_form():
    """Retained mutant, CERT-412 [P2] finding 1.

    `redis.Redis.setex(name, time, value)` binds by keyword just as happily as
    by position, so a writer spelled `setex(name=…, time=…, value=…)` is an
    ordinary call shape, not a contrivance. The first version of this guard
    required two POSITIONAL arguments and therefore skipped it silently — the
    same self-oracular failure as CERT-409 [P2], in a second call shape.
    """
    mutant = _clean_get_feed_source() + (
        "\n"
        "    async def _publish_fifth_writer(_client=None, _key='k', _json='{}'):\n"
        "        await _client.setex(name=_key, time=_cache_ttl, value=_json)\n"
    )
    assert _setex_ttls_not_derived_from_live_helper(mutant) == ["_cache_ttl"], (
        "a keyword-form `setex(time=…)` writer escaped the guard — the ceiling "
        "is asserted only over writers that happen to be spelled positionally"
    )


def test_the_fifth_writer_guard_catches_getattr_dispatch():
    """Retained mutant, CERT-412 [P2] finding 2.

    `getattr(client, "setex")(…)` is the same write through a literal dynamic
    lookup. The call's `func` is a `Call`, not an `Attribute`, so an
    attribute-only visitor never sees a `setex` at all.
    """
    mutant = _clean_get_feed_source() + (
        "\n"
        "    async def _publish_fifth_writer(_client=None, _key='k', _json='{}'):\n"
        "        await getattr(_client, 'setex')(_key, _cache_ttl, _json)\n"
    )
    assert _setex_ttls_not_derived_from_live_helper(mutant) == ["_cache_ttl"], (
        "a `getattr(client, 'setex')` writer escaped the guard — dynamic "
        "dispatch is an unguarded door into the same unconditional TTL"
    )


def test_the_fifth_writer_guard_refuses_unanalyzable_dispatch_and_splats():
    """The escape hatches the two repairs above would otherwise leave open.

    Recognizing `getattr(client, "setex")` only helps while the attribute name
    is a literal; a computed name, a `*args` splat or a `**kwargs` splat all
    publish a TTL this visitor cannot read. Per the CERT-412 fix paragraph the
    source may not dispatch its Redis writers dynamically — unreadable is
    refused, never assumed clean.
    """
    clean = _clean_get_feed_source()

    dynamic = clean + (
        "\n"
        "    async def _publish_fifth_writer(_client=None, _w='setex'):\n"
        "        await getattr(_client, _w)('k', _cache_ttl, '{}')\n"
    )
    assert _setex_ttls_not_derived_from_live_helper(dynamic), (
        "a computed-name `getattr(client, name)(…)` writer read as clean"
    )

    kwargs_splat = clean + (
        "\n"
        "    async def _publish_fifth_writer(_client=None, _kw=None):\n"
        "        await _client.setex(**_kw)\n"
    )
    assert _setex_ttls_not_derived_from_live_helper(kwargs_splat), (
        "a `setex(**kwargs)` writer read as clean — its TTL is unreadable, "
        "which is not the same as derived"
    )

    args_splat = clean + (
        "\n"
        "    async def _publish_fifth_writer(_client=None, _a=()):\n"
        "        await _client.setex(*_a)\n"
    )
    assert _setex_ttls_not_derived_from_live_helper(args_splat), (
        "a `setex(*args)` writer read as clean — its TTL is unreadable"
    )


# ---------------------------------------------------------------------------
# CERT-1856 — a payload is only as young as its OLDEST INPUT
# ---------------------------------------------------------------------------
#
# The fifth writer that was missed, and it is not a writer at all — it is the
# BUILD. Every test above bounds a payload that was COPIED between tiers, and
# `remember_last_good`'s `built_at` closes those. But a payload can arrive at
# the publish seam already old without ever having been copied: LAT-P230 lets a
# request reuse a shared artifact, and `_score_event_concepts` copies a
# concept's `status` — including `live` — straight onto the card. So a page
# freshly built HERE out of a 59-second-old shared `concepts` artifact carries a
# 59-second-old score, and stamping it with the response-build time handed it a
# brand-new 60-second window: 118 seconds of total input age under a branch
# that declares 60 as the maximum.
#
# The branch got the Redis half right — `_live_ttls` already subtracts the
# artifact age from both TTLs — which is exactly what made this hard to see:
# the visible, externally-checkable half was correct while the process-local
# fallback behind it silently restarted the clock.
#
# LAT-P230's own reasoning missed it by asking the wrong question. It asked
# "can `market_load` carry a live price?" (no — futures markets are never
# live) and concluded the residual was unreachable. The question that finds
# this is "can ANY shared artifact whose age we subtract carry a live price?",
# and `concepts` can.


def _seed_consumed_artifact(monkeypatch, feed_mod, *, age_s: float) -> None:
    """Make the route consume one shared artifact that is `age_s` old.

    Seeds a real ORIGIN into the route's own sink at the real binding seam, so
    the route then runs the REAL `oldest_consumed_artifact_age_s` against it.

    CERT-1862 blocked the first shape of these tests for patching that function
    with a constant. The criticism was exact: a constant cannot age, so the test
    could not see the consumption-to-publication gap — and that gap WAS the
    residual defect (an artifact consumed at 50s with a 20s build still read
    50s). Seeding an origin instead leaves the arithmetic under test in the
    hands of the code under test.
    """
    real_bind = feed_mod._bind_shared_reuse_sink

    def _bind_and_seed(reuse, tiers, origins):
        origins.append(time_module.monotonic() - age_s)
        return real_bind(reuse, tiers, origins)

    monkeypatch.setattr(feed_mod, "_bind_shared_reuse_sink", _bind_and_seed)


@pytest.mark.asyncio
async def test_a_live_page_built_from_an_aged_artifact_gets_no_fresh_window(
    monkeypatch,
):
    """CERT-1856's falsifier, kept as the regression test.

    A fresh BUILD that consumed a 59-second-old shared artifact, recalled 59
    seconds later under the 60-second live ceiling. Pre-fix the route passed
    `time.time()` as the age origin, so last-good served it at 118 seconds.
    """
    import app.routes.feed as feed_mod

    rc._reset_last_good_for_tests()

    # The request consumed a shared artifact that was already 59s old.
    _seed_consumed_artifact(monkeypatch, feed_mod, age_s=59.0)

    # Empty Redis, so the route MISSES and takes the build path (the seam under
    # test). A seeded mirror would exercise a copy hop instead.
    redis = _SeededRedis()
    resp = await _drive_feed(redis=redis, monkeypatch=monkeypatch)
    assert resp.status_code == 200

    stored = rc._last_good.get(SHARED_KEY)
    assert stored is not None, (
        "the build published no process-local last-good, so this test is not "
        "exercising the path CERT-1856 is about"
    )
    origin, _payload = stored

    # The origin must be backdated to the oldest input, not stamped at response
    # build time. Generous slack: the assertion is "roughly a minute ago", not
    # a clock comparison that a slow CI box could flake on.
    backdate = time_module.time() - origin
    assert backdate >= 55.0, (
        f"the age origin was backdated by only {backdate:.1f}s for a payload "
        "built from a 59s-old shared artifact — the response-build time was "
        "stamped instead, which restarts the very clock the ceiling measures "
        "(CERT-1856)"
    )

    # …and the consequence that matters: 59s later, the ceiling refuses it.
    # This is the exact call `_live_bounded_last_good` makes for a live page.
    real_time = rc.time.time
    rc.time.time = lambda: real_time() + 59.0
    try:
        recalled = rc.recall_last_good(
            SHARED_KEY, max_age_s=FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS
        )
    finally:
        rc.time.time = real_time
        rc._reset_last_good_for_tests()

    assert recalled is None, (
        "a page built from a 59s-old shared artifact was served 59s later — "
        f"118s of total input age against a {FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS}s "
        "ceiling (CERT-1856)"
    )


@pytest.mark.asyncio
async def test_a_build_from_fresh_artifacts_keeps_the_full_window(monkeypatch):
    """THE FRESH CONTROL — the fix must not just disable last-good.

    Without this, backdating by a constant (or refusing everything) would pass
    the test above while removing the fallback that keeps a Redis blip from
    becoming a stampede of cold builds.
    """
    import app.routes.feed as feed_mod

    rc._reset_last_good_for_tests()
    _seed_consumed_artifact(monkeypatch, feed_mod, age_s=0.0)

    redis = _SeededRedis()
    resp = await _drive_feed(redis=redis, monkeypatch=monkeypatch)
    assert resp.status_code == 200

    stored = rc._last_good.get(SHARED_KEY)
    assert stored is not None
    origin, _payload = stored
    assert time_module.time() - origin < 5.0, (
        "a build that consumed nothing shared was backdated anyway — the "
        "ceiling is now stricter than the rule it enforces"
    )

    real_time = rc.time.time
    rc.time.time = lambda: real_time() + 59.0
    try:
        recalled = rc.recall_last_good(
            SHARED_KEY, max_age_s=FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS
        )
    finally:
        rc.time.time = real_time
        rc._reset_last_good_for_tests()

    assert recalled is not None, (
        "a genuinely fresh build was refused 59s later under a 60s ceiling — "
        "the live fallback no longer works at all"
    )


@pytest.mark.asyncio
async def test_a_non_live_page_is_still_unbounded_after_the_backdate(monkeypatch):
    """THE NON-LIVE CONTROL — the ceiling is a LIVE rule and stays one.

    Backdating happens unconditionally (it is the honest origin either way),
    so this pins that it did not quietly import the live ceiling into the
    futures path, where unbounded last-good is deliberate and correct.
    """
    rc._reset_last_good_for_tests()

    # A settled page: aged origin, but nothing live on it.
    rc.remember_last_good(
        SHARED_KEY, SETTLED_PAGE, built_at=time_module.time() - 59.0
    )
    assert payload_contains_live_event(SETTLED_PAGE) is False

    real_time = rc.time.time
    rc.time.time = lambda: real_time() + 59.0
    try:
        # No `max_age_s` — the branch `_live_bounded_last_good` takes for a
        # page with no live card.
        recalled = rc.recall_last_good(SHARED_KEY)
    finally:
        rc.time.time = real_time
        rc._reset_last_good_for_tests()

    assert recalled is not None, (
        "a settled page was refused at 118s — the live ceiling leaked into "
        "the futures path, where last-good is unbounded on purpose"
    )


# ---------------------------------------------------------------------------
# CERT-1864 — a payload past the ceiling is not served ONCE
# ---------------------------------------------------------------------------
#
# CERT-1856 gave the payload an honest age origin and CERT-1862 made that origin
# keep aging while the build ran. Both were right, and both stopped one step
# short of the reader. At 50s of artifact age plus a 20s build the arithmetic
# now says 70s and hands back `(0, 0)` TTLs — "nobody may cache this" — and the
# route then returned the page to the caller anyway. The one reader guaranteed
# to see the over-ceiling score was the person who asked for it.
#
# #2216's own sentence is the bar: past the ceiling the page is REBUILT, not
# served older. These tests hold the three outcomes that satisfy it — drop the
# artifacts so the next build is a rebuild, serve a still-valid prior payload,
# or say `unavailable` — and, just as importantly, the control that a build
# INSIDE the ceiling still serves its live page.


class _ShimmedTime:
    """`principal_independent_cache`'s view of `time`, with a movable monotonic.

    Patched on the MODULE's own reference (`pic.time`) and never on the `time`
    module itself. The event loop reads `time.monotonic()` for every timer it
    owns, so a test that moves the real one moves the deadlines of the very
    request it is driving — including the bounded Redis calls this route makes,
    which would divert it onto a fallback path and prove nothing about the seam
    under test. Everything except `monotonic` is the real module.
    """

    def __init__(self, real, offset: dict):
        self._real = real
        self._offset = offset

    def __getattr__(self, name):
        return getattr(self._real, name)

    def monotonic(self) -> float:
        return self._real.monotonic() + self._offset["s"]


def _seed_artifact_and_build_time(
    monkeypatch, feed_mod, *, artifact_age_s: float, build_s: float
):
    """One request that consumed an `artifact_age_s`-old artifact and then spent
    `build_s` building. Returns the hook to hand `_drive_feed(during_build=…)`.

    Both halves are seeded at REAL seams. The origin goes into the route's own
    sink at the real binding site, and the build time is spent by advancing the
    clock the route's arithmetic reads, from inside the build. Nothing patches
    the age, the headroom or the TTL: every number in the assertions is one the
    code under test computed (CERT-1862's criticism of the first shape of these
    tests, applied here from the start).
    """
    offset = {"s": 0.0}
    shim = _ShimmedTime(time_module, offset)
    monkeypatch.setattr(pic, "time", shim)

    real_bind = feed_mod._bind_shared_reuse_sink

    def _bind_and_seed(reuse, tiers, origins):
        origins.append(shim.monotonic() - artifact_age_s)
        return real_bind(reuse, tiers, origins)

    monkeypatch.setattr(feed_mod, "_bind_shared_reuse_sink", _bind_and_seed)

    fired = {"n": 0}

    def _spend_the_build():
        fired["n"] += 1
        offset["s"] = build_s

    return _spend_the_build, fired, shim


class _Row:
    """A DB row whose UNSET attributes are `None`, not a `MagicMock`.

    The rig above seeds a `MagicMock` event, and the real scorer throws it out
    (`skipping event 1 — scoring error: expected string or bytes-like object`),
    which is why the pages those tests build are not live. Every test below
    turns on the built page BEING live, so it needs a row the real
    `_score_events` accepts — and `None` for anything it does not name is the
    honest default for a nullable column.
    """

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __getattr__(self, name):
        return None


def _live_event_row(oid: int = 1):
    """One in-progress NBA game, in the shape `_score_events` actually reads."""
    now = datetime.now(timezone.utc)
    return _Row(
        id=oid,
        external_id=f"ext-{oid}",
        home_team_name="Celtics",
        away_team_name="76ers",
        sport=_Row(key="basketball_nba", name="Basketball"),
        status="live",
        commence_time=now - timedelta(hours=1),
        completed_at=None,
        home_score=55,
        away_score=52,
        period="Q3 5:12",
        win_probability_sources={"betting": {"home_probability": 0.55}},
        opening_home_probability=0.52,
        opening_away_probability=0.48,
        opening_home_spread=-3.5,
        opening_over_under=214.5,
        opening_favorite="Celtics",
        raw_ei=80.0,
        llm_importance=8,
        ei_metadata={},
        event_tags=[],
    )


async def _drive_live_feed(monkeypatch, *, redis, during_build=None):
    """`_drive_feed`, guaranteed to build a page that IS live.

    Two things stand between a live row and a live page, and both are DB work
    the rig mocks out. `enrich_event_team_data` attaches the logos, and
    `_filter_discover_event_noise` DROPS a live game that has none — so without
    the stub the page comes back empty and every assertion about the ceiling
    passes vacuously. Stubbing the enrichment is the smallest thing that makes
    the route's own liveness predicate answer honestly; the scoring, the display
    chain, the publish seam and the ceiling arithmetic are all the real ones.
    """
    import app.routes.feed as feed_mod

    async def _enrich(db, items):
        for item in items:
            if item.get("type") == "event":
                item["data"]["home_team_data"] = {"id": 1, "logo_url": "h.png"}
                item["data"]["away_team_data"] = {"id": 2, "logo_url": "a.png"}

    monkeypatch.setattr(feed_mod, "enrich_event_team_data", _enrich)
    return await _drive_feed(
        redis=redis,
        monkeypatch=monkeypatch,
        during_build=during_build,
        events=[_live_event_row()],
    )


@pytest.mark.asyncio
async def test_a_live_page_over_the_ceiling_is_not_served_even_once(monkeypatch):
    """CERT-1864's falsifier. 50s of artifact + 20s of build = 70s, served zero
    times.

    Pre-fix this request returned 200 with the live page and a `(0, 0)` TTL
    block: the ceiling refused to let anyone CACHE the payload and then served
    it to the caller anyway.
    """
    import app.routes.feed as feed_mod

    rc._reset_last_good_for_tests()
    during_build, fired, _shim = _seed_artifact_and_build_time(
        monkeypatch, feed_mod, artifact_age_s=50.0, build_s=20.0
    )

    redis = _SeededRedis()
    resp = await _drive_live_feed(
        monkeypatch, redis=redis, during_build=during_build
    )

    assert fired["n"] >= 1, (
        "the build-time seam never ran, so this request did not spend the 20 "
        "seconds the test is about — the assertions below would be measuring "
        "a 50s build, not a 70s one"
    )
    assert resp.status_code == 200
    body = resp.json()

    # The page that was built is NOT the page that came back.
    assert body["cache"]["status"] == "unavailable", (
        "a live page built from inputs that had already spent the whole "
        f"{FEED_RESPONSE_STALE_TTL_LIVE_SECONDS}s ceiling was served to the "
        "caller — the TTLs were zero and the payload went out anyway (CERT-1864)"
    )
    assert body["cache"]["reason"] == "input_age_ceiling"
    assert body["items"] == []
    assert resp.headers["X-Feed-Cache"] == "unavailable"

    # …and it did not become anybody else's truth either.
    assert rc._last_good.get(SHARED_KEY) is None, (
        "the over-ceiling payload was recorded as process-local last-good, so "
        "the next request would be served it as a fallback"
    )
    assert redis.setex_calls == [], (
        "the over-ceiling payload was published to Redis"
    )
    rc._reset_last_good_for_tests()


@pytest.mark.asyncio
async def test_a_build_inside_the_ceiling_still_serves_its_live_page(monkeypatch):
    """THE CONTROL, and the reason the test above is a ceiling and not a mute.

    Same rig, same live page, same shared artifact — 50s + 5s of build is 55s,
    inside the ceiling, so the live body IS served, with a real (shortened) TTL.
    A repair that refused everything would pass the falsifier and take Discover
    down.
    """
    import app.routes.feed as feed_mod

    rc._reset_last_good_for_tests()
    during_build, fired, _shim = _seed_artifact_and_build_time(
        monkeypatch, feed_mod, artifact_age_s=50.0, build_s=5.0
    )

    redis = _SeededRedis()
    resp = await _drive_live_feed(
        monkeypatch, redis=redis, during_build=during_build
    )

    assert fired["n"] >= 1
    assert resp.status_code == 200
    body = resp.json()

    assert body["cache"]["status"] == "miss"
    assert body["cache"]["live"] is True, (
        "the rig stopped producing a live page, so neither this control nor "
        "the falsifier above is exercising the live ceiling any more"
    )
    assert body["items"], "an in-ceiling live build served an empty page"
    # Shortened by the inputs' age, not by the principal: the anon window is
    # 60s and the live cap 30s, so anything this small came from the headroom.
    assert 0 < body["cache"]["ttl_seconds"] <= 10, body["cache"]
    assert rc._last_good.get(SHARED_KEY) is not None
    rc._reset_last_good_for_tests()


@pytest.mark.asyncio
async def test_a_still_valid_prior_payload_is_served_instead(monkeypatch):
    """Outcome (b): the fallback is bounded by the same ceiling it replaces.

    A prior payload five seconds old is younger than the 70s build that was
    refused, so serving it is strictly better than both alternatives — and its
    TTLs are computed from ITS age, not from this request's artifacts.
    """
    import app.routes.feed as feed_mod

    rc._reset_last_good_for_tests()
    rc.remember_last_good(
        SHARED_KEY, LIVE_PAGE, built_at=time_module.time() - 5.0
    )

    during_build, fired, _shim = _seed_artifact_and_build_time(
        monkeypatch, feed_mod, artifact_age_s=50.0, build_s=20.0
    )
    resp = await _drive_live_feed(
        monkeypatch, redis=_SeededRedis(), during_build=during_build
    )

    assert fired["n"] >= 1
    assert resp.status_code == 200
    body = resp.json()

    assert body["cache"]["status"] == "last_good"
    assert body["cache"]["reason"] == "input_age_ceiling"
    assert [item["data"]["id"] for item in body["items"]] == [1, 2, 3], (
        "the refused build's own items came back wearing a last_good label"
    )
    # 30s = the live fresh cap, still the binding constraint at 5s of age. The
    # stale window is what the prior payload's own age has left of the ceiling.
    assert body["cache"]["ttl_seconds"] == FEED_RESPONSE_TTL_LIVE_SECONDS
    assert 50 <= body["cache"]["stale_ttl_seconds"] <= 56, body["cache"]

    stored = rc._last_good.get(SHARED_KEY)
    assert stored is not None
    assert [item["data"]["id"] for item in stored[1]["items"]] == [1, 2, 3], (
        "the over-ceiling build overwrote the still-valid prior payload"
    )
    rc._reset_last_good_for_tests()


@pytest.mark.asyncio
async def test_the_over_ceiling_artifacts_are_dropped_by_the_refusal(monkeypatch):
    """Outcome (a): the NEXT build rebuilds instead of repeating the refusal.

    A shared artifact may outlive a live payload's ceiling — `market_load`'s TTL
    is 120s against 60s — so an artifact can be a valid cache entry and an
    invalid input at the same time. Left in place, it refuses every request that
    consumes it until its TTL expires: one refused response is the ceiling
    working, a minute of them is an outage.
    """
    import app.routes.feed as feed_mod

    rc._reset_last_good_for_tests()
    during_build, fired, shim = _seed_artifact_and_build_time(
        monkeypatch, feed_mod, artifact_age_s=50.0, build_s=20.0
    )

    ns = "market_load"
    pic.clear_shared_builds(ns)
    entries = pic._store.setdefault(ns, {})
    entries[("cert1864-too-old",)] = (shim.monotonic() - 70.0, {"v": 1})
    entries[("cert1864-still-usable",)] = (shim.monotonic() - 10.0, {"v": 2})

    try:
        resp = await _drive_live_feed(
            monkeypatch, redis=_SeededRedis(), during_build=during_build
        )
        assert fired["n"] >= 1
        assert resp.status_code == 200

        remaining = pic._store.get(ns, {})
        assert ("cert1864-too-old",) not in remaining, (
            "the artifact that put this build over the ceiling is still in the "
            "store, so the next request consumes it and is refused in turn"
        )
        assert ("cert1864-still-usable",) in remaining, (
            "the refusal evicted an artifact that is still young enough to "
            "build a live page from — a ceiling, not a flush"
        )
    finally:
        pic.clear_shared_builds(ns)
        rc._reset_last_good_for_tests()


class _CountingClock:
    """A monotonic clock a test can advance. `drop_entries_older_than` takes one
    for the reason `get_or_build` does: a test that sleeps is a test that flakes."""

    def __init__(self, t: float = 10_000.0) -> None:
        self._t = t

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


@pytest.mark.asyncio
async def test_dropping_an_over_age_entry_makes_the_next_read_rebuild():
    """The unit under outcome (a): dropped means REBUILT, not "returns stale"."""
    ns = "cert1864_probe"
    pic.clear_shared_builds(ns)
    clock = _CountingClock()

    async def _build_v(v):
        return {"v": v}

    first = await pic.get_or_build(
        ns, ("k",), lambda: _build_v(1), ttl_s=120.0, clock=clock
    )
    assert first == {"v": 1}

    clock.advance(70.0)
    # Still a live cache entry under its own 120s TTL...
    assert await pic.get_or_build(
        ns, ("k",), lambda: _build_v(2), ttl_s=120.0, clock=clock
    ) == {"v": 1}

    # ...and no longer a valid input to a live page.
    dropped = pic.drop_entries_older_than(
        FEED_RESPONSE_STALE_TTL_LIVE_SECONDS, clock=clock
    )
    assert dropped == 1
    assert await pic.get_or_build(
        ns, ("k",), lambda: _build_v(3), ttl_s=120.0, clock=clock
    ) == {"v": 3}, "the dropped entry was still served — the eviction is a no-op"

    pic.clear_shared_builds(ns)


def test_the_ceiling_the_route_refuses_on_is_the_ceiling_last_good_is_bounded_by():
    """The two numbers the refusal path uses have to be the same number.

    The route decides "over the ceiling" with `live_total_age_headroom_s`
    (`FEED_RESPONSE_STALE_TTL_LIVE_SECONDS`) and then bounds its fallback with
    `FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS`. If those ever drift apart the
    fallback can be older than the payload it replaced, which is the defect
    wearing the repair's clothes.
    """
    assert FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS == FEED_RESPONSE_STALE_TTL_LIVE_SECONDS

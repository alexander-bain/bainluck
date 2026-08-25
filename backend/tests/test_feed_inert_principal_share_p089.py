"""LAT-P089 (Q407 Item 1) — an INERT principal must not pay a private cold build.

## The defect these tests pin

``feed_response_cache_key`` gives every identified principal its own key. The
native Discover surface always sends ``x-session-id`` (a persistent per-install
UUID), so it resolves ``s:<uuid>`` and can NEVER hit the key the pre-warm beat
keeps warm — the beat can only warm ``anon``. Measured against production on
2026-08-25 at the client's exact first-paint shape, with a distinct session id
per request:

    limit=50&event_pct=0.15  session A   miss  3.47s (server 2962.67ms)
    limit=50&event_pct=0.15  session B   miss  3.32s (server 2815.70ms)
    limit=20&event_pct=0.15  anon        hit   0.41s (server   14.88ms)

Every distinct install pays a full cold build against a hard, non-retryable 6s
client budget (``DiscoverViewModel.retryBudget``). Q407 measured 2 of 3 such
builds over budget, worst 67% over. That is what surfaces to Alex as
``DeadlineExceededError`` and a two-card feed replayed from disk last-good.

## Why the fix is provably safe

The principal enters the build through exactly ONE value: the
``PersonalizationContext`` loaded at the top of the leader block. Nothing else
downstream reads ``feed_user``/``feed_session_id`` outside ``my_teams_only``,
which is already part of the cache key. So when the loaded context is EQUAL to
a default-constructed ``PersonalizationContext()``, the build is byte-identical
to the anonymous build of the same shape — not "probably similar", equal by
construction. Such a request may read the anonymous entry.

The test is structural equality, deliberately, rather than a bespoke "does this
session have interactions" query: a new personalization field added later is
covered without anyone remembering to update a predicate, and any field that
cannot be compared makes the check fail CLOSED (build as before).

``test_the_empty_principal_context_equals_the_default_context`` pins that
premise directly, so the fix cannot outlive its own justification.
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
    FEED_RESPONSE_STALE_TTL_SECONDS,
    feed_response_cache_key,
)
from app.utils.personalization import PersonalizationContext

# The bare `GET /api/feed` shape after the route's own Discover defaulting
# (event_pct -> 0.15, mode -> "discover"). Built from the SAME function the
# route uses, so this fixture cannot drift from the key under test.
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

_SESSION_ID = "inert-install-uuid-p089"

SHARED_KEY = feed_response_cache_key(user_id=None, session_id=None, **_BARE_FEED_SHAPE)
PRIVATE_KEY = feed_response_cache_key(
    user_id=None, session_id=_SESSION_ID, **_BARE_FEED_SHAPE
)

WARMED_PAYLOAD = {
    "items": [
        {"type": "futures", "data": {"id": 1, "name": "Warmed card A"}},
        {"type": "futures", "data": {"id": 2, "name": "Warmed card B"}},
        {"type": "futures", "data": {"id": 3, "name": "Warmed card C"}},
    ],
    "total": 3,
    "limit": 200,
    "offset": 0,
    "has_more": False,
}


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
    """A DB stand-in that returns rows for the events query and nothing else.

    Nothing else is the point: no ``discover_interactions``, no favorites, no
    pins — i.e. exactly the state of a fresh install, which is what makes the
    loaded personalization context inert.
    """
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
    """A shared-redis stand-in holding a fixed map of key -> raw JSON body."""

    def __init__(self, contents: dict[str, str] | None = None):
        self.contents = dict(contents or {})
        self.gets: list[str] = []
        self.setex_calls: list[tuple[str, int, str]] = []

    async def get(self, key):
        self.gets.append(key)
        return self.contents.get(key)

    async def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self.contents[key] = value
        return True


async def _drive_feed(*, redis, monkeypatch, headers=None, user=None):
    """One real `/api/feed` request, recording whether the build stage ran."""
    from app.main import app

    session = _seeded_session([_event_row(1)])

    async def _mock_get_db():
        yield session

    async def _mock_user():
        return user

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_user

    built: list[str] = []

    async def spy_futures(*a, **k):
        built.append("futures")
        return []

    def spy_schedule(coro):
        return asyncio.ensure_future(coro)

    monkeypatch.setattr(rc, "schedule_background", spy_schedule)

    async def _get_redis():
        return redis

    monkeypatch.setattr(rc, "get_shared_async_redis", _get_redis)

    with patch("app.main.init_db", new_callable=AsyncMock), patch(
        "app.routes.feed._score_futures", new=AsyncMock(side_effect=spy_futures)
    ), patch(
        "app.routes.feed._score_sports_mode_futures",
        new=AsyncMock(side_effect=spy_futures),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            resp = await ac.get("/api/feed", headers=headers or {})

    app.dependency_overrides.clear()
    # Let the detached private-key backfill run.
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    return resp, built


# --- The premise ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_empty_principal_context_equals_the_default_context():
    """The whole fix rests on this equality. Pin it, don't assume it.

    A session id with no rows anywhere must load a context that is EQUAL to the
    default one an anonymous request gets for free. If a future field breaks
    that (a timestamp, a nondeterministic set order, `eq=False`), the sharing
    below silently stops firing — and this test says so out loud instead.
    """
    from app.routes.feed import _load_personalization_context

    session = _seeded_session([])
    loaded = await _load_personalization_context(
        session, None, session_id=_SESSION_ID, config=None
    )
    assert loaded == PersonalizationContext(), (
        "a principal with no personalization state must be indistinguishable "
        "from anonymous — otherwise the shared-key read below is unsound"
    )


def test_the_shared_key_is_the_key_the_warmer_publishes():
    """The 'shared' key is not a new key space — it is literally the anon key."""
    assert SHARED_KEY == feed_response_cache_key(
        user_id=None, session_id=None, **_BARE_FEED_SHAPE
    )
    assert SHARED_KEY != PRIVATE_KEY, "a session must still have its own key"


# --- The behaviour --------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_inert_session_serves_the_shared_entry_instead_of_building(
    monkeypatch,
):
    """The failing production case, at the route.

    Private key cold, anonymous key warm, request carries a session id and no
    user. Today this pays the full build (the 3.5s that blows the client's 6s
    budget). It must serve the warmed anonymous payload instead.
    """
    redis = _SeededRedis({f"{SHARED_KEY}:stale": json.dumps(WARMED_PAYLOAD)})

    resp, built = await _drive_feed(
        redis=redis, monkeypatch=monkeypatch, headers={"x-session-id": _SESSION_ID}
    )

    assert resp.status_code == 200
    assert built == [], (
        "an inert principal must not pay a cold build when the anonymous entry "
        f"for its own shape is already warm (build stages ran: {built})"
    )
    body = resp.json()
    assert [i["data"]["id"] for i in body["items"]] == [1, 2, 3]
    assert body["total"] == 3
    assert resp.headers["x-feed-cache"] in ("shared_hit", "shared_stale_hit")
    assert body["cache"]["reason"] == "inert_principal"


@pytest.mark.asyncio
async def test_the_shared_serve_backfills_the_private_key(monkeypatch):
    """The next open from the same install must not even reach the DB.

    Serving from the anonymous entry is the SECOND-best outcome; short-circuiting
    at the top-of-route private read is the best one. Publishing the payload
    under the private key is what converts one into the other.
    """
    redis = _SeededRedis({f"{SHARED_KEY}:stale": json.dumps(WARMED_PAYLOAD)})

    await _drive_feed(
        redis=redis, monkeypatch=monkeypatch, headers={"x-session-id": _SESSION_ID}
    )

    written = {key: (ttl, body) for key, ttl, body in redis.setex_calls}
    assert PRIVATE_KEY in written, "fresh private mirror not backfilled"
    assert f"{PRIVATE_KEY}:stale" in written, "private stale mirror not backfilled"
    assert written[f"{PRIVATE_KEY}:stale"][0] == FEED_RESPONSE_STALE_TTL_SECONDS
    assert json.loads(written[PRIVATE_KEY][1])["total"] == 3
    # It must NOT scribble on the shared/anon entry — that one belongs to the
    # warmer, and a request republishing it would extend its life indefinitely.
    assert SHARED_KEY not in written
    assert f"{SHARED_KEY}:stale" not in written


@pytest.mark.asyncio
async def test_a_cold_shared_entry_still_builds(monkeypatch):
    """No warmed anonymous entry → behave exactly as before this change."""
    redis = _SeededRedis({})

    resp, built = await _drive_feed(
        redis=redis, monkeypatch=monkeypatch, headers={"x-session-id": _SESSION_ID}
    )

    assert resp.status_code == 200
    assert built, "with nothing to share, the request must still build"
    assert resp.headers["x-feed-cache"] == "miss"


@pytest.mark.asyncio
async def test_an_anonymous_request_does_not_read_a_second_key(monkeypatch):
    """An anon request's private key IS the shared key — no double read."""
    redis = _SeededRedis({f"{SHARED_KEY}:stale": json.dumps(WARMED_PAYLOAD)})

    resp, built = await _drive_feed(redis=redis, monkeypatch=monkeypatch)

    assert resp.status_code == 200
    assert built == []
    assert (
        resp.headers["x-feed-cache"] == "stale_hit"
    ), "anonymous must take the ordinary stale path, not the shared path"
    # Exactly the two ordinary reads (fresh, then :stale). No third.
    assert redis.gets == [SHARED_KEY, f"{SHARED_KEY}:stale"]


@pytest.mark.asyncio
async def test_a_personalized_session_never_reads_the_shared_entry(monkeypatch):
    """The other direction, and the one that would be a product bug.

    A principal with real personalization state must keep its own build. If this
    ever goes green by serving the anon payload, a user's dismissals and
    already-seen suppression have silently stopped applying.
    """
    redis = _SeededRedis({f"{SHARED_KEY}:stale": json.dumps(WARMED_PAYLOAD)})

    personalized = PersonalizationContext(
        recent_dismissed_event_ids={4242},
    )

    with patch(
        "app.routes.feed._load_personalization_context",
        new=AsyncMock(return_value=personalized),
    ):
        resp, built = await _drive_feed(
            redis=redis, monkeypatch=monkeypatch, headers={"x-session-id": _SESSION_ID}
        )

    assert resp.status_code == 200
    assert built, "a personalized principal must still build its own feed"
    assert resp.headers["x-feed-cache"] == "miss"
    assert (
        f"{SHARED_KEY}:stale" not in redis.gets[1:]
    ), "a personalized principal must never read the anonymous entry"


@pytest.mark.asyncio
async def test_a_redis_failure_on_the_shared_read_degrades_to_a_build(monkeypatch):
    """Fail-open on the response. A cache that can 500 the endpoint is a loss."""

    class _AngryRedis(_SeededRedis):
        async def get(self, key):
            self.gets.append(key)
            if key.startswith(SHARED_KEY) and len(self.gets) > 2:
                raise RuntimeError("redis exploded on the shared read")
            return None

    redis = _AngryRedis({})

    resp, built = await _drive_feed(
        redis=redis, monkeypatch=monkeypatch, headers={"x-session-id": _SESSION_ID}
    )

    assert resp.status_code == 200, "a shared-read failure must never surface as a 500"
    assert built, "a shared-read failure must degrade to the ordinary build"

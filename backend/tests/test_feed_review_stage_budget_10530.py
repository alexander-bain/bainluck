"""#10530 (#1459): the mandatory review stage lives inside the one request budget.

`_apply_manual_review_decisions` is not optional steering — `needs_design_fix`
and `needs_data_fix` decisions DROP cards. It used to be awaited with no deadline
after the futures stage had already spent the budget, so a stalled decisions
query held the whole /api/feed response (root reproduction:
artifacts/1459-post-budget-review-20261005). The contract pinned here, at the
real route, with the REAL review helper and only the DB/Redis edges faked:

* zero budget left  -> the stage is never started: no decisions SQL, no Redis;
* budget runs out   -> the query is cancelled, the session gets a FINITE
  rollback (or invalidate when the rollback hangs), and no further DB work runs;
* either way the unreviewed build is never served, handed to waiters, kept as
  process last-good or published to Redis. The caller gets the prior COMPLETE
  payload with its stored origin and the live ceiling, or a truthful
  `unavailable`;
* a request cancellation propagates as cancellation and releases the slot;
* with time to spare, human decisions (suppress / promote / kill switch OFF)
  apply exactly as before.
"""

import asyncio
import time
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import app.utils.request_cache as rc
from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from app.utils.feed_cache import FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS
from tests.test_feed_degraded_publication import _seeded_session

# Large enough that the futures stub and the event build finish well inside it
# on a slow runner, small enough that a stalled query times out quickly.
_SHORT_BUDGET_MS = 1500

# Sports is the surface the root reproduced on. Discover's default
# `event_pct=0.15` empties a deck that holds only games, so the Discover arm
# asks for an all-games page to keep the build non-empty at the review stage.
SPORTS = "/api/feed?mode=sports"
DISCOVER = "/api/feed?event_pct=1.0"


class _Redis:
    """Misses every feed-cache read (so the route builds); answers the eval
    kill-switch key with ``kill_value``; records every key read and written."""

    def __init__(self, kill_value=None):
        from app.routes.feed import _EVAL_PROMOTE_ENABLED_KEY

        self._kill_key = _EVAL_PROMOTE_ENABLED_KEY
        self._kill_value = kill_value
        self.reads: list[str] = []
        self.setex_keys: list[str] = []

    async def get(self, key, *a, **k):
        self.reads.append(key)
        return self._kill_value if key == self._kill_key else None

    async def setex(self, key, ttl, val):
        self.setex_keys.append(key)
        return True

    @property
    def kill_switch_reads(self) -> int:
        return self.reads.count(self._kill_key)


class _Session:
    """The fixture session, with the review-decisions query under test control.

    ``log`` is the ordered DB history: ``sql`` (any other statement),
    ``review_sql``, ``review_cancelled``, ``rollback``, ``invalidate``; the
    singleflight spy appends ``finish_build:<result>`` so ordering across the
    two is checkable.
    """

    def __init__(self, cards, *, rows=(), block=False, rollback_hangs=False):
        # The cards the build's events stage returns. The rest of the build
        # runs for real against an empty fixture database.
        self.cards = cards
        self.session = _seeded_session([])
        self.log: list[str] = []
        self.review_entered = asyncio.Event()
        base_execute = self.session.execute.side_effect

        async def execute(stmt, *a, **k):
            if "discover_review_decisions" in str(stmt).lower():
                self.log.append("review_sql")
                self.review_entered.set()
                if block:
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError:
                        self.log.append("review_cancelled")
                        raise
                result = MagicMock()
                result.all.return_value = list(rows)
                return result
            self.log.append("sql")
            return await base_execute(stmt, *a, **k)

        async def rollback():
            self.log.append("rollback")
            if rollback_hangs:
                await asyncio.Event().wait()

        async def invalidate():
            self.log.append("invalidate")

        self.session.execute = AsyncMock(side_effect=execute)
        self.session.rollback = AsyncMock(side_effect=rollback)
        self.session.invalidate = AsyncMock(side_effect=invalidate)

    def after_review(self) -> list[str]:
        return self.log[self.log.index("review_sql") + 1 :]


def _card(oid: int) -> dict:
    """A live game card as `_score_events` emits it."""
    return {
        "type": "event",
        "score": 70 - oid,
        "reason": "Close game",
        "headline": "Live",
        "data": {
            "id": oid,
            "status": "live",
            "home_team": f"Home {oid}",
            "away_team": f"Away {oid}",
            "sport_key": "basketball_nba",
            "home_probability": 0.55,
            "away_probability": 0.45,
        },
    }


def _decision(item_id, decision, item_type="event"):
    return types.SimpleNamespace(
        item_type=item_type, item_id=str(item_id), decision=decision, family_key=None
    )


@pytest.fixture
def rig(monkeypatch):
    """Spies on every publication edge; resets process-local cache state."""
    rc._reset_last_good_for_tests()
    rc._reset_inflight_for_tests()
    state = types.SimpleNamespace(remembered=[], published=[], finished=[], db=None)

    orig_remember = rc.remember_last_good
    orig_finish = rc.finish_build

    def spy_remember(key, payload, **kwargs):
        state.remembered.append(key)
        return orig_remember(key, payload, **kwargs)

    def spy_schedule(coro):
        state.published.append(coro)
        return asyncio.ensure_future(coro)

    def spy_finish(key, future, **kwargs):
        result = kwargs.get("result")
        tag = "None" if result is None else "payload"
        state.finished.append(tag)
        if state.db is not None:
            state.db.log.append(f"finish_build:{tag}")
        return orig_finish(key, future, **kwargs)

    monkeypatch.setattr(rc, "remember_last_good", spy_remember)
    monkeypatch.setattr(rc, "schedule_background", spy_schedule)
    monkeypatch.setattr(rc, "finish_build", spy_finish)
    yield state
    rc._reset_last_good_for_tests()
    rc._reset_inflight_for_tests()


async def _get(
    monkeypatch,
    db: _Session,
    redis: _Redis,
    *,
    path=SPORTS,
    n: int = 1,
    stagger=None,
    score=None,
    enrich=None,
):
    """Drive ``n`` concurrent real /api/feed requests.

    The candidate stages are stubbed (events -> ``db.cards``; futures, golf and
    concepts empty); everything from the review stage on is the real route.
    ``score`` / ``enrich`` replace the events-half stubs (#10534 drives them).
    """
    from app.main import app

    async def _mock_get_db():
        yield db.session

    async def _mock_user():
        return None

    async def _get_redis():
        return redis

    monkeypatch.setattr(rc, "get_shared_async_redis", _get_redis)
    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock), patch(
            "app.routes.feed._score_futures", new=AsyncMock(return_value=[])
        ), patch(
            "app.routes.feed._score_sports_mode_futures",
            new=AsyncMock(return_value=[]),
        ), patch(
            "app.routes.feed._score_events",
            new=AsyncMock(
                side_effect=score or (lambda *a, **k: [dict(c) for c in db.cards])
            ),
        ), patch(
            "app.routes.feed._score_golf_tournaments", new=AsyncMock(return_value=[])
        ), patch(
            "app.routes.feed._score_event_concepts", new=AsyncMock(return_value=[])
        ), patch(
            "app.routes.feed.enrich_event_team_data", new=AsyncMock(side_effect=enrich)
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                first = asyncio.create_task(ac.get(path))
                tasks = [first]
                if n > 1:
                    await stagger()
                    tasks += [asyncio.create_task(ac.get(path)) for _ in range(n - 1)]
                responses = await asyncio.gather(*tasks)
    finally:
        app.dependency_overrides.clear()
    await asyncio.sleep(0)
    return responses if n > 1 else responses[0]


def _spend_budget_in_enrichment(monkeypatch):
    """#10534: event scoring and team enrichment refuse at zero budget too, so a
    budget that is zero from admission now stops the build at scoring. The tests
    below pin the REVIEW stage's zero admission, so the budget runs out at the
    end of the events half instead — the same zero the review stage met before."""

    async def _enrich(db, items):
        monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", 0)

    return _enrich


def _ids(body):
    return sorted(item["data"]["id"] for item in body["items"])


# --- with time to spare: human decisions apply exactly as before -------------


@pytest.mark.parametrize("path", [SPORTS, DISCOVER])
async def test_normal_budget_applies_suppression_and_publishes_complete_build(
    monkeypatch, rig, path
):
    db = _Session(
        [_card(1), _card(2)],
        rows=[_decision(1, "needs_data_fix"), _decision(2, "accepted_promote")],
    )
    redis = _Redis()

    resp = await _get(monkeypatch, db, redis, path=path)
    body = resp.json()

    assert resp.status_code == 200
    assert "review_sql" in db.log
    assert _ids(body) == [2], "needs_data_fix must still suppress event 1"
    assert "build_quality" not in body
    assert rig.remembered and rig.published, "a complete build is still shared truth"
    assert "rollback" not in db.log and "invalidate" not in db.log


async def test_kill_switch_off_still_short_circuits_before_any_review_sql(
    monkeypatch, rig
):
    db = _Session([_card(1), _card(2)], rows=[_decision(1, "needs_data_fix")])
    redis = _Redis(kill_value=b"0")

    resp = await _get(monkeypatch, db, redis)

    assert resp.status_code == 200
    assert redis.kill_switch_reads == 1
    assert "review_sql" not in db.log
    assert _ids(resp.json()) == [1, 2], "switch OFF applies no steer, as before"


# --- zero budget: the stage is never started ---------------------------------


@pytest.mark.parametrize("path", [SPORTS, DISCOVER])
async def test_zero_budget_admits_no_review_and_serves_truthful_unavailable(
    monkeypatch, rig, path
):
    db = _Session([_card(1)], rows=[_decision(1, "needs_data_fix")])
    redis = _Redis()

    resp = await _get(
        monkeypatch,
        db,
        redis,
        path=path,
        enrich=_spend_budget_in_enrichment(monkeypatch),
    )
    body = resp.json()

    assert resp.status_code == 200
    assert "review_sql" not in db.log, "no decisions SQL at zero budget"
    assert redis.kill_switch_reads == 0, "the stage is not entered at all"
    assert body["items"] == [] and body["total"] == 0
    assert body["cache"]["status"] == "unavailable"
    assert body["cache"]["reason"] == "review_budget"
    assert body["cache"]["ttl_seconds"] == 0
    assert resp.headers["x-feed-cache"] == "unavailable"
    assert resp.headers["x-feed-singleflight"] == "none"
    assert rig.remembered == [] and rig.published == [] and redis.setex_keys == []
    assert rig.finished == ["None"], "the slot is released with no payload"
    assert rc.inflight_count() == 0 and rc._inflight == {}


async def test_zero_budget_serves_prior_complete_payload_with_its_stored_origin(
    monkeypatch, rig
):
    # A real complete build first: that is what makes it an eligible prior.
    db = _Session([_card(1), _card(2)])
    complete = (await _get(monkeypatch, db, _Redis())).json()
    [key] = list(rc._last_good)
    stored_origin = rc._last_good[key][0]
    # Ten seconds into the live window, so the served TTL must shrink by ten.
    rc._last_good[key] = (stored_origin - 10, rc._last_good[key][1])
    rig.remembered.clear()
    rig.published.clear()
    rig.finished.clear()

    db2 = _Session([_card(1), _card(2), _card(3)])
    redis = _Redis()
    resp = await _get(
        monkeypatch, db2, redis, enrich=_spend_budget_in_enrichment(monkeypatch)
    )
    body = resp.json()

    assert "review_sql" not in db2.log
    assert resp.headers["x-feed-cache"] == "last_good"
    assert body["cache"]["status"] == "last_good"
    assert body["cache"]["reason"] == "review_budget"
    assert body["cache"]["live"] is True
    assert body["cache"]["built_at"] == pytest.approx(stored_origin - 10)
    assert body["cache"]["ttl_seconds"] <= FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS - 10
    assert _ids(body) == _ids(complete), "the prior payload, not the new build"
    assert rig.remembered == [] and rig.published == [] and redis.setex_keys == []
    assert rig.finished == ["None"]


async def test_zero_budget_refuses_a_live_prior_past_the_live_ceiling(monkeypatch, rig):
    db = _Session([_card(1)])
    await _get(monkeypatch, db, _Redis())
    [key] = list(rc._last_good)
    origin, payload = rc._last_good[key]
    rc._last_good[key] = (origin - FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS - 1, payload)

    resp = await _get(
        monkeypatch,
        _Session([_card(1)]),
        _Redis(),
        enrich=_spend_budget_in_enrichment(monkeypatch),
    )
    body = resp.json()

    assert body["cache"]["status"] == "unavailable"
    assert body["cache"]["reason"] == "review_budget"
    assert body["items"] == []


# --- budget runs out mid-query: cancel, finite cleanup, no leak --------------


async def test_slow_review_sql_is_cancelled_rolled_back_and_never_leaks(
    monkeypatch, rig
):
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    # Event 1 is a card a human ruled bad; the query that would say so stalls.
    db = _Session([_card(1)], rows=[_decision(1, "needs_data_fix")], block=True)
    rig.db = db
    redis = _Redis()
    captures = []

    class _Capture:
        def abandon(self, reason):
            captures.append(reason)

        def __getattr__(self, name):  # any record_* call would be a leak
            raise AssertionError(f"capture.{name} called on an abandoned build")

    monkeypatch.setattr(
        "app.routes.feed.display_capture_from_request", lambda request: _Capture()
    )

    started = time.monotonic()
    resp = await _get(monkeypatch, db, redis)
    elapsed = time.monotonic() - started
    body = resp.json()

    assert resp.status_code == 200
    assert elapsed < _SHORT_BUDGET_MS / 1000 + 2.0 + 1.0, elapsed
    # The concrete SQL lifecycle: cancelled, released, rolled back — and the
    # waiters were released BEFORE the cleanup spent any time.
    assert db.after_review() == ["review_cancelled", "finish_build:None", "rollback"]
    assert "sql" not in db.after_review(), "no DB work on the cancelled session"
    assert body["items"] == [], "the unreviewed card must not be served"
    assert body["cache"]["status"] == "unavailable"
    assert body["cache"]["reason"] == "review_timeout"
    assert captures == ["review_timeout"]
    assert rig.remembered == [] and rig.published == [] and redis.setex_keys == []
    assert rc._inflight == {}


async def test_a_hung_rollback_is_bounded_and_the_connection_invalidated(
    monkeypatch, rig
):
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _Session([_card(1)], block=True, rollback_hangs=True)
    rig.db = db

    started = time.monotonic()
    resp = await _get(monkeypatch, db, _Redis())
    elapsed = time.monotonic() - started

    assert resp.status_code == 200
    assert resp.json()["cache"]["reason"] == "review_timeout"
    assert db.after_review() == [
        "review_cancelled",
        "finish_build:None",
        "rollback",
        "invalidate",
    ]
    assert elapsed < _SHORT_BUDGET_MS / 1000 + 2.0 + 1.0, elapsed


async def test_a_coalesced_waiter_is_released_with_nothing_to_serve(monkeypatch, rig):
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _Session([_card(1)], rows=[_decision(1, "needs_data_fix")], block=True)
    rig.db = db
    redis = _Redis()

    async def _after_leader_enters_review():
        await asyncio.wait_for(db.review_entered.wait(), timeout=10)

    leader, waiter = await _get(
        monkeypatch, db, redis, n=2, stagger=_after_leader_enters_review
    )

    assert leader.headers["x-feed-singleflight"] == "none"
    assert leader.json()["cache"]["reason"] == "review_timeout"
    assert waiter.headers["x-feed-singleflight"] == "waiter_unavailable"
    assert waiter.json()["items"] == []
    assert db.log.count("review_sql") == 1, "the waiter never started a second build"
    assert rig.finished[0] == "None", "the waiters got no payload"
    assert rig.remembered == [] and rig.published == [] and redis.setex_keys == []
    assert rc._inflight == {}


async def test_request_cancellation_propagates_and_releases_the_slot(monkeypatch, rig):
    db = _Session([_card(1)], block=True)
    rig.db = db
    redis = _Redis()

    task = asyncio.create_task(_get(monkeypatch, db, redis))
    await asyncio.wait_for(db.review_entered.wait(), timeout=10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert db.after_review() == ["review_cancelled", "finish_build:None"], (
        "a cancelled request is not a timeout: no fallback, no cleanup SQL"
    )
    assert rc._inflight == {}
    assert rig.remembered == [] and rig.published == [] and redis.setex_keys == []

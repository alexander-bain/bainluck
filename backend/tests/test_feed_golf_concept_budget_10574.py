"""#10574 (#1459): the golf and event-concept tiers live inside the one request
budget.

Both tiers ran after the events half with no deadline, so once event
enrichment had spent the budget they were still entered, and a stalled tier
held the whole /api/feed response past it (root proof:
artifacts/discovery-containers-release-plan/alive-feature-delivery-20261003/
1459-GOLF-CONCEPT-BOUNDARY). They now end the way the events half does
(#10534), and this file reuses that suite's and #10530's rig, session, Redis
and spies rather than rebuilding them. Pinned at the real route:

* zero budget left  -> the tier is never started;
* budget runs out   -> the tier is cancelled, the waiters are released, and
  nothing after it runs. Concepts build on THIS request's session, so they
  get the finite rollback (after the waiters are released); golf never
  touches it, so it gets none — its own cold fill closes its isolated session;
* a swallowed cancellation still ends the build; the incomplete build is never
  served, handed to waiters, kept as last-good, captured or published; the
  caller gets the prior COMPLETE payload with its stored origin, or a truthful
  `unavailable`;
* another request's shared work is left alone: a concept build or golf fill
  this request was only WAITING on keeps running and keeps its slot, and a
  finished concept artifact whose best-effort publish outlived the budget stays
  shared with its own age;
* a golf waiter handed the cancellation of ANOTHER request's fill leader is not
  itself cancelled: it carries on without golf;
* a request cancellation propagates, a disabled tier creates no budget
  condition, ordinary tier errors keep the catch-and-log, and with time to
  spare both tiers still feed mandatory human review.
"""

import asyncio
import time
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

import app.utils.golf_base as gb
import app.utils.principal_independent_cache as shared
import app.utils.request_cache as rc
from app.utils.feed_cache import FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS
from tests.test_feed_event_stage_budget_10534 import (
    _assert_nothing_published,
    captures,  # noqa: F401 — fixture
    stages,  # noqa: F401 — fixture
)
from tests.test_feed_review_stage_budget_10530 import (
    DISCOVER,
    SPORTS,
    _card,
    _decision,
    _get,
    _ids,
    _Redis,
    _Session,
    _SHORT_BUDGET_MS,
)
from tests.test_feed_review_stage_budget_10530 import rig as _rig_10530
from tests.test_golf_base_cache import _FakeFillSession, _tournament

rig = _rig_10530

GOLF = "golf"
CONCEPTS = "concepts"
TIERS = [GOLF, CONCEPTS]
OUR_REASONS = {
    "golf_budget",
    "golf_timeout",
    "concepts_budget",
    "concepts_timeout",
}
# What may never follow each tier once it did not finish.
DOWNSTREAM = {
    GOLF: {CONCEPTS, "futures", "review_decisions"},
    CONCEPTS: {"futures", "review_decisions"},
}
# Nothing after a tier is a second DB statement on the request session.
CLEANUP = {GOLF: [], CONCEPTS: ["rollback"]}


@pytest.fixture(autouse=True)
def _clean_shared_tiers(monkeypatch):
    """The concept artifact and the golf base outlive a request by design;
    every test here starts and ends without one."""
    monkeypatch.setenv("FEED_SHARED_BUILD_CROSS_WORKER", "0")
    shared.clear_shared_builds()
    gb._reset_l0_for_tests()
    yield
    shared.clear_shared_builds()
    gb._reset_l0_for_tests()


class _TierSession(_Session):
    """#10530's session; the log also records the two tiers.

    ``stall`` names the tier that never returns until cancelled; ``swallow``
    makes it eat the cancellation and return normally. The concept tier runs a
    marked query on this session (``concepts_sql``), as the real builder does;
    the golf tier never touches it (``golf_entered``), as the golf base never
    does. Either logs ``<tier>_cancelled``.
    """

    def __init__(self, cards, *, stall=None, swallow=False, **kw):
        super().__init__(cards, **kw)
        self.stall = stall
        self.swallow = swallow
        self.tier_entered = asyncio.Event()
        inner = self.session.execute.side_effect

        async def execute(stmt, *a, **k):
            if f"/* stage:{CONCEPTS} */" in str(stmt):
                self.log.append(f"{CONCEPTS}_sql")
                if stall == CONCEPTS:
                    await self._stall(CONCEPTS)
                return None
            return await inner(stmt, *a, **k)

        self.session.execute.side_effect = execute

    async def _stall(self, tier):
        self.tier_entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.log.append(f"{tier}_cancelled")
            if not self.swallow:
                raise

    def entry(self, tier) -> str:
        return f"{tier}_sql" if tier == CONCEPTS else f"{tier}_entered"

    def after(self, entry: str) -> list[str]:
        return self.log[self.log.index(entry) + 1 :]


def _golf(db: _TierSession, *, then=None, error=None):
    async def golf(*a, **k):
        db.log.append(f"{GOLF}_entered")
        if db.stall == GOLF:
            await db._stall(GOLF)
        if error is not None:
            raise error
        if then is not None:
            then()
        return []

    return golf


def _concepts(db: _TierSession, *, then=None, error=None):
    async def concepts(session, *a, **k):
        await session.execute(text(f"SELECT 1 /* stage:{CONCEPTS} */"))
        if error is not None:
            raise error
        if then is not None:
            then()
        return []

    return concepts


def _tiers(db, **kw):
    return {
        "golf": _golf(db, **kw.get(GOLF, {})),
        "concepts": _concepts(db, **kw.get(CONCEPTS, {})),
    }


def _spend(monkeypatch):
    return lambda: monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", 0)


def _spend_in_enrichment(monkeypatch):
    async def enrich(session, items):
        monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", 0)

    return enrich


# --- with time to spare: both tiers feed mandatory human review --------------


@pytest.mark.parametrize("path", [SPORTS, DISCOVER])
async def test_normal_budget_runs_both_tiers_then_reviews_and_publishes(
    monkeypatch, rig, stages, path
):
    db = _TierSession(
        [_card(1), _card(2)],
        rows=[_decision(1, "needs_data_fix"), _decision(2, "accepted_promote")],
    )

    resp = await _get(monkeypatch, db, _Redis(), path=path, **_tiers(db))
    body = resp.json()

    assert resp.status_code == 200
    assert db.log.index(f"{GOLF}_entered") < db.log.index(f"{CONCEPTS}_sql")
    assert db.log.index(f"{CONCEPTS}_sql") < db.log.index("review_sql")
    assert _ids(body) == [2], "needs_data_fix must still suppress event 1"
    assert body["cache"].get("reason") not in OUR_REASONS
    assert {GOLF, CONCEPTS, "futures", "review_decisions"} <= set(stages)
    assert rig.remembered and rig.published, "a complete build is still shared truth"
    assert "rollback" not in db.log and "invalidate" not in db.log


# --- zero budget: the tier is never started -----------------------------------


@pytest.mark.parametrize("tier", TIERS)
async def test_zero_budget_admits_no_tier(monkeypatch, rig, stages, captures, tier):
    db = _TierSession([_card(1)], rows=[_decision(1, "needs_data_fix")])
    redis = _Redis()
    # Golf is the first tier, so the budget runs out in enrichment for it; for
    # concepts it runs out inside golf, which is the stage before.
    kw = {GOLF: {"then": _spend(monkeypatch)}} if tier == CONCEPTS else {}
    enrich = _spend_in_enrichment(monkeypatch) if tier == GOLF else None

    resp = await _get(monkeypatch, db, redis, enrich=enrich, **_tiers(db, **kw))
    body = resp.json()

    assert db.entry(tier) not in db.log, "the tier is not started at zero budget"
    assert "review_sql" not in db.log
    assert (
        "rollback" not in db.log and "invalidate" not in db.log
    ), "a tier never started cancelled nothing: no cleanup"
    assert body["items"] == [] and body["total"] == 0
    assert body["cache"]["status"] == "unavailable"
    assert body["cache"]["reason"] == f"{tier}_budget"
    assert body["cache"]["ttl_seconds"] == 0
    assert resp.headers["x-feed-singleflight"] == "none"
    assert not DOWNSTREAM[tier] & set(stages)
    assert captures == [f"{tier}_budget"]
    assert rig.finished == ["None"], "the slot is released with no payload"
    _assert_nothing_published(rig, redis)


@pytest.mark.parametrize(
    "path, disabled",
    [
        (SPORTS + "&include_events=false", {GOLF, CONCEPTS}),
        (SPORTS + '&tags=["sport:mma"]', {GOLF}),
        (SPORTS + '&tags=["sport:golf"]', {CONCEPTS}),
    ],
)
async def test_a_disabled_tier_creates_no_budget_condition(
    monkeypatch, rig, path, disabled
):
    db = _TierSession([_card(1)])
    # The budget runs out in whichever tier is still enabled (or is zero from
    # admission when neither is): a disabled tier must never be the one that
    # reports it.
    if disabled == {GOLF, CONCEPTS}:
        monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", 0)
    kw = {
        GOLF: {"then": _spend(monkeypatch)},
        CONCEPTS: {"then": _spend(monkeypatch)},
    }

    resp = await _get(monkeypatch, db, _Redis(), path=path, **_tiers(db, **kw))
    reason = resp.json()["cache"].get("reason")

    assert resp.status_code == 200
    for tier in disabled:
        assert db.entry(tier) not in db.log
        assert reason not in {f"{tier}_budget", f"{tier}_timeout"}, reason


# --- budget runs out mid-tier: cancel, release, finite cleanup, no leak -------


@pytest.mark.parametrize("path", [SPORTS, DISCOVER])
@pytest.mark.parametrize("tier", TIERS)
async def test_a_stalled_tier_is_cancelled_released_and_never_leaks(
    monkeypatch, rig, stages, captures, tier, path
):
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _TierSession([_card(1)], rows=[_decision(1, "needs_data_fix")], stall=tier)
    rig.db = db
    redis = _Redis()

    started = time.monotonic()
    resp = await _get(monkeypatch, db, redis, path=path, **_tiers(db))
    elapsed = time.monotonic() - started
    body = resp.json()

    assert resp.status_code == 200
    assert elapsed < _SHORT_BUDGET_MS / 1000 + 2.0 + 1.0, elapsed
    # Cancelled, the waiters released, THEN (concepts only) rolled back — and
    # nothing after it: no further statement on the request session.
    assert db.after(db.entry(tier)) == [
        f"{tier}_cancelled",
        "finish_build:None",
        *CLEANUP[tier],
    ]
    assert not DOWNSTREAM[tier] & set(stages), "no stage follows the deadline"
    assert body["items"] == [], "the incomplete build must not be served"
    assert body["cache"]["status"] == "unavailable"
    assert body["cache"]["reason"] == f"{tier}_timeout"
    assert body["cache"]["ttl_seconds"] == 0
    assert resp.headers["x-feed-singleflight"] == "none"
    assert captures == [f"{tier}_timeout"]
    _assert_nothing_published(rig, redis)


@pytest.mark.parametrize("tier", TIERS)
async def test_a_swallowed_cancellation_still_ends_the_build(
    monkeypatch, rig, stages, tier
):
    # Something inside the tier ate the deadline's cancellation and returned
    # normally. The tier returned; it did not finish inside the budget.
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _TierSession([_card(1)], stall=tier, swallow=True)
    rig.db = db
    redis = _Redis()

    resp = await _get(monkeypatch, db, redis, **_tiers(db))
    body = resp.json()

    assert db.after(db.entry(tier)) == [
        f"{tier}_cancelled",
        "finish_build:None",
        *CLEANUP[tier],
    ]
    assert body["cache"]["reason"] == f"{tier}_timeout"
    assert body["items"] == []
    assert not DOWNSTREAM[tier] & set(stages)
    _assert_nothing_published(rig, redis)


async def test_a_hung_rollback_after_a_concept_stall_is_bounded_and_invalidated(
    monkeypatch, rig
):
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _TierSession([_card(1)], stall=CONCEPTS, rollback_hangs=True)
    rig.db = db

    started = time.monotonic()
    resp = await _get(monkeypatch, db, _Redis(), **_tiers(db))
    elapsed = time.monotonic() - started

    assert resp.json()["cache"]["reason"] == "concepts_timeout"
    assert db.after(f"{CONCEPTS}_sql") == [
        f"{CONCEPTS}_cancelled",
        "finish_build:None",
        "rollback",
        "invalidate",
    ]
    assert elapsed < _SHORT_BUDGET_MS / 1000 + 2.0 + 1.0, elapsed


@pytest.mark.parametrize("tier", TIERS)
async def test_a_tier_stall_serves_the_prior_complete_payload_with_its_origin(
    monkeypatch, rig, tier
):
    db = _TierSession([_card(1), _card(2)])
    complete = (await _get(monkeypatch, db, _Redis(), **_tiers(db))).json()
    [key] = list(rc._last_good)
    stored_origin = rc._last_good[key][0]
    # Ten seconds into the live window, so the served TTL must shrink by ten.
    rc._last_good[key] = (stored_origin - 10, rc._last_good[key][1])
    rig.remembered.clear()
    rig.published.clear()
    rig.finished.clear()
    shared.clear_shared_builds()

    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db2 = _TierSession([_card(1), _card(2), _card(3)], stall=tier)
    redis = _Redis()
    resp = await _get(monkeypatch, db2, redis, **_tiers(db2))
    body = resp.json()

    assert resp.headers["x-feed-cache"] == "last_good"
    assert body["cache"]["status"] == "last_good"
    assert body["cache"]["reason"] == f"{tier}_timeout"
    assert body["cache"]["live"] is True
    assert body["cache"]["built_at"] == pytest.approx(stored_origin - 10)
    assert body["cache"]["ttl_seconds"] <= FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS - 10
    assert _ids(body) == _ids(complete), "the prior payload, not the new build"
    assert rig.finished == ["None"]
    _assert_nothing_published(rig, redis)


@pytest.mark.parametrize("tier", TIERS)
async def test_a_tier_stall_refuses_a_live_prior_past_the_live_ceiling(
    monkeypatch, rig, tier
):
    db = _TierSession([_card(1)])
    await _get(monkeypatch, db, _Redis(), **_tiers(db))
    [key] = list(rc._last_good)
    origin, payload = rc._last_good[key]
    rc._last_good[key] = (origin - FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS - 1, payload)
    shared.clear_shared_builds()

    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db2 = _TierSession([_card(1)], stall=tier)
    resp = await _get(monkeypatch, db2, _Redis(), **_tiers(db2))
    body = resp.json()

    assert body["cache"]["status"] == "unavailable"
    assert body["cache"]["reason"] == f"{tier}_timeout"
    assert body["items"] == []


@pytest.mark.parametrize("tier", TIERS)
async def test_a_coalesced_page_waiter_is_released_before_cleanup(
    monkeypatch, rig, tier
):
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _TierSession([_card(1)], stall=tier)
    rig.db = db
    redis = _Redis()

    async def _after_leader_enters_the_tier():
        await asyncio.wait_for(db.tier_entered.wait(), timeout=10)

    leader, waiter = await _get(
        monkeypatch,
        db,
        redis,
        n=2,
        stagger=_after_leader_enters_the_tier,
        **_tiers(db),
    )

    assert leader.json()["cache"]["reason"] == f"{tier}_timeout"
    assert waiter.headers["x-feed-singleflight"] == "waiter_unavailable"
    assert waiter.json()["items"] == []
    assert db.log.count(db.entry(tier)) == 1, "the waiter never started a second build"
    assert db.after(db.entry(tier))[:2] == [f"{tier}_cancelled", "finish_build:None"]
    _assert_nothing_published(rig, redis)


@pytest.mark.parametrize("tier", TIERS)
async def test_request_cancellation_propagates_with_no_fallback(monkeypatch, rig, tier):
    db = _TierSession([_card(1)], stall=tier)
    rig.db = db
    redis = _Redis()

    task = asyncio.create_task(_get(monkeypatch, db, redis, **_tiers(db)))
    await asyncio.wait_for(db.tier_entered.wait(), timeout=10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert db.after(db.entry(tier)) == [
        f"{tier}_cancelled",
        "finish_build:None",
    ], "a cancelled request is not a timeout: no fallback, no cleanup SQL"
    _assert_nothing_published(rig, redis)


@pytest.mark.parametrize("tier", TIERS)
@pytest.mark.parametrize(
    "error", [RuntimeError("tier bug"), TimeoutError("a provider's own timeout")]
)
async def test_an_ordinary_tier_error_is_still_logged_and_the_build_goes_on(
    monkeypatch, rig, stages, tier, error
):
    # A TimeoutError raised INSIDE the tier is not the request deadline: it
    # keeps the catch-and-log policy, as it always had.
    db = _TierSession([_card(1)])

    resp = await _get(
        monkeypatch, db, _Redis(), **_tiers(db, **{tier: {"error": error}})
    )

    assert resp.status_code == 200
    assert resp.json()["cache"].get("reason") not in OUR_REASONS
    assert {"futures", "review_decisions"} <= set(stages)
    assert "review_sql" in db.log
    assert "rollback" not in db.log and "invalidate" not in db.log


# --- the shared concept build: another request's work is left alone ----------


@pytest.fixture
def one_concept_key(monkeypatch):
    """Pin the concept key's clock bucket, so a build started outside the route
    and the route's own lookup name the same artifact on any clock."""
    monkeypatch.setattr(shared, "time_bucket", lambda now, seconds: 0)
    return (("all",), 0)


async def test_a_concept_waiter_deadline_leaves_the_other_leader_building(
    monkeypatch, rig, one_concept_key
):
    entered, release = asyncio.Event(), asyncio.Event()

    async def other_requests_build():
        entered.set()
        await release.wait()
        return [{"id": "other"}]

    leader = asyncio.create_task(
        shared.get_or_build(CONCEPTS, one_concept_key, other_requests_build)
    )
    await entered.wait()
    try:
        monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
        db = _TierSession([_card(1)])
        rig.db = db
        redis = _Redis()
        resp = await _get(monkeypatch, db, redis, **_tiers(db))

        assert resp.json()["cache"]["reason"] == "concepts_timeout"
        assert f"{CONCEPTS}_sql" not in db.log, "the waiter never built its own"
        assert not leader.done(), "the other request's build is not cancelled"
        assert shared._locks[CONCEPTS][
            one_concept_key
        ].locked(), "and it still holds its own lock"
        # Expiry while waiting is still conservatively cleaned up.
        assert db.log[-2:] == ["finish_build:None", "rollback"]
        _assert_nothing_published(rig, redis)
    finally:
        release.set()
    assert await leader == [{"id": "other"}]


async def test_a_cancelled_concept_build_publishes_nothing_and_frees_its_lock(
    monkeypatch, rig, one_concept_key
):
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _TierSession([_card(1)], stall=CONCEPTS)
    resp = await _get(monkeypatch, db, _Redis(), **_tiers(db))

    assert resp.json()["cache"]["reason"] == "concepts_timeout"
    assert not shared._locks[CONCEPTS][one_concept_key].locked()
    assert one_concept_key not in shared._store.get(CONCEPTS, {})

    async def next_build():
        return [{"id": "next"}]

    assert await shared.get_or_build(CONCEPTS, one_concept_key, next_build) == [
        {"id": "next"}
    ], "the next caller rebuilds cleanly"


async def test_a_publish_that_outlives_the_budget_keeps_the_finished_artifact(
    monkeypatch, rig, one_concept_key
):
    async def stalled_publish(*a, **k):
        await asyncio.Event().wait()

    monkeypatch.setattr(shared, "_publish_cross_worker", stalled_publish)
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _TierSession([_card(1)])
    rig.db = db
    redis = _Redis()
    built = [{"id": "complete"}]

    resp = await _get(
        monkeypatch, db, redis, golf=_golf(db), concepts=lambda *a, **k: built
    )
    body = resp.json()

    # This PAGE did not finish inside the budget: it is not served or shared.
    assert body["cache"]["reason"] == "concepts_timeout"
    assert body["items"] == []
    assert db.log[-2:] == ["finish_build:None", "rollback"]
    _assert_nothing_published(rig, redis)
    # The concept artifact DID finish before the expiry: it stays shared, with
    # the age it was stored at — the timeout neither clears nor refreshes it.
    stored_at, value = shared._store[CONCEPTS][one_concept_key]
    assert value == built
    assert not shared._locks[CONCEPTS][one_concept_key].locked()

    async def must_not_build():
        raise AssertionError("the finished artifact should have been reused")

    assert await shared.get_or_build(CONCEPTS, one_concept_key, must_not_build) == built
    assert shared._store[CONCEPTS][one_concept_key][0] == stored_at


# --- the real golf base: its own session, its own slot -----------------------


@pytest.fixture
def golf_fill(monkeypatch):
    """The real golf tier over an empty Redis, so it reaches the cold fill;
    the fill's isolated sessions and its `get_golf` calls are recorded and
    `get_golf` hangs until ``release`` is set."""
    import app.routes.feed as feed

    state = type("GolfFill", (), {})()
    state.real = feed._score_golf_tournaments
    state.sessions = []
    state.calls = 0
    state.entered = asyncio.Event()
    state.release = asyncio.Event()
    state.cancelled = 0

    def factory():
        s = _FakeFillSession()
        state.sessions.append(s)
        return s

    async def get_golf(fill_db):
        state.calls += 1
        state.entered.set()
        try:
            await state.release.wait()
        except asyncio.CancelledError:
            state.cancelled += 1
            raise
        return {"tournaments": [_tournament(key="masters")]}

    monkeypatch.setattr(gb, "_fill_session_factory", factory)
    monkeypatch.setattr("app.routes.golf.get_golf", get_golf)
    return state


async def test_a_golf_fill_leader_cancelled_by_the_deadline_closes_its_own_session(
    monkeypatch, rig, stages, golf_fill
):
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _TierSession([_card(1)])
    rig.db = db
    redis = _Redis()
    statements_before_golf = []

    async def mark(*a, **k):
        statements_before_golf.extend(db.log)
        return await golf_fill.real(*a, **k)

    resp = await _get(monkeypatch, db, redis, golf=mark, concepts=_concepts(db))
    body = resp.json()

    assert body["cache"]["reason"] == "golf_timeout"
    assert golf_fill.calls == 1 and golf_fill.cancelled == 1
    [fill_session] = golf_fill.sessions
    assert fill_session.entered and fill_session.exited, "the fill closed its own"
    # The request session saw nothing from golf and gets no rollback for it.
    # The rig's spy logs every slot release: the fill resolving its own golf
    # slot as it unwinds, then this page's slot.
    assert db.log == statements_before_golf + ["finish_build:None"] * 2
    assert not DOWNSTREAM[GOLF] & set(stages)
    _assert_nothing_published(rig, redis)  # incl. the golf slot: rc._inflight == {}


async def test_a_golf_waiter_deadline_leaves_the_fill_leader_and_its_slot(
    monkeypatch, rig, golf_fill
):
    leader = asyncio.create_task(gb.get_golf_base(None, datetime.now(timezone.utc)))
    await golf_fill.entered.wait()
    slot = rc._inflight[gb.GOLF_BASE_BUILD_KEY]
    try:
        monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
        db = _TierSession([_card(1)])
        rig.db = db
        resp = await _get(
            monkeypatch, db, _Redis(), golf=golf_fill.real, concepts=_concepts(db)
        )

        assert resp.json()["cache"]["reason"] == "golf_timeout"
        assert not leader.done(), "the other caller's fill is not cancelled"
        assert rc._inflight.get(gb.GOLF_BASE_BUILD_KEY) is slot, "nor displaced"
        assert golf_fill.calls == 1, "and the waiter started no second fill"
        assert "rollback" not in db.log
    finally:
        golf_fill.release.set()
    tours, prov = await leader
    assert prov == gb.PROV_INLINE and tours[0]["key"] == "masters"


async def test_a_golf_waiter_handed_another_leaders_cancellation_carries_on(
    monkeypatch, rig, stages, golf_fill
):
    # The fill is shared across feed keys, so a waiter here is handed the
    # cancellation of a leader some OTHER request owns (its deadline, or its
    # client leaving). Nobody cancelled this request.
    leader = asyncio.create_task(gb.get_golf_base(None, datetime.now(timezone.utc)))
    await golf_fill.entered.wait()
    db = _TierSession([_card(1)])

    async def golf_then_leader_cancelled(*a, **k):
        # This request joins the fill as a waiter, in its own task; the leader
        # is cancelled while it waits.
        asyncio.get_running_loop().call_later(0.05, leader.cancel)
        return await golf_fill.real(*a, **k)

    resp = await _get(
        monkeypatch,
        db,
        _Redis(),
        golf=golf_then_leader_cancelled,
        concepts=_concepts(db),
    )
    body = resp.json()

    assert leader.cancelled()
    assert resp.status_code == 200
    assert body["cache"].get("reason") not in OUR_REASONS
    assert {CONCEPTS, "futures", "review_decisions"} <= set(stages)
    assert resp.headers["x-feed-golf-provenance"] == gb.PROV_UNAVAILABLE
    assert "rollback" not in db.log

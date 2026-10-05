"""#10534 (#1459): event scoring and its team enrichment live inside the one
request budget.

`_score_events` and the `enrich_event_team_data` call right after it were
awaited with no deadline, so a stalled query in either held the whole /api/feed
response past the budget (root reproduction of the scoring gap:
artifacts/1459-post-budget-review-20261005). They now end the way the review
stage does (#10530), and this file reuses that suite's rig, session, Redis and
cleanup controls rather than rebuilding them. Pinned at the real route, with
only the DB/Redis edges and the candidate stages faked:

* zero budget left  -> the stage is never started;
* budget runs out   -> the stage's query is cancelled, the waiters are released
  BEFORE a finite rollback (or invalidate), and nothing after it runs: no golf,
  concepts, futures, review or further DB work;
* the deadline is not an ordinary scoring failure: the catch-and-log never
  turns it into a published partial build, while ordinary errors keep it;
* the caller gets the prior COMPLETE payload with its stored origin under the
  live ceiling, or a truthful `unavailable`; nothing is published;
* a request cancellation propagates as cancellation, with no fallback;
* a stage with nothing to do creates no budget condition, and with time to
  spare both stages still feed mandatory human review.
"""

import asyncio
import time

import pytest
from sqlalchemy import text

import app.utils.request_cache as rc
from app.utils.feed_cache import FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS
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

# #10530's publication spies, reused as they are: every edge an incomplete
# build must never reach (last-good, Redis publish, the singleflight slot).
rig = _rig_10530

SCORE = "score_events"
ENRICH = "team_enrichment"
OUR_REASONS = {
    "events_budget",
    "events_timeout",
    "enrichment_budget",
    "enrichment_timeout",
}
# Stages that only run AFTER the events half; none may follow a cancelled one.
DOWNSTREAM = {"golf", "concepts", "futures", "review_decisions"}


class _StageSession(_Session):
    """#10530's session, plus one marked query per events-half stage.

    ``stall`` names the stage whose query never returns until cancelled;
    ``swallow`` makes that query eat the cancellation and return normally.
    The log gains ``<stage>_sql`` / ``<stage>_cancelled``.
    """

    def __init__(self, cards, *, stall=None, swallow=False, **kw):
        super().__init__(cards, **kw)
        self.stage_entered = asyncio.Event()
        inner = self.session.execute.side_effect

        async def execute(stmt, *a, **k):
            for stage in (SCORE, ENRICH):
                if f"/* stage:{stage} */" in str(stmt):
                    self.log.append(f"{stage}_sql")
                    if stall == stage:
                        self.stage_entered.set()
                        try:
                            await asyncio.Event().wait()
                        except asyncio.CancelledError:
                            self.log.append(f"{stage}_cancelled")
                            if not swallow:
                                raise
                    return None
            return await inner(stmt, *a, **k)

        self.session.execute.side_effect = execute

    def after(self, entry: str) -> list[str]:
        return self.log[self.log.index(entry) + 1 :]


def _score(db: _StageSession, *, then=None):
    """`_score_events` as a stage that queries the request's session."""

    async def score(session, *a, **k):
        await session.execute(text(f"SELECT 1 /* stage:{SCORE} */"))
        if then is not None:
            then()
        return [dict(c) for c in db.cards]

    return score


async def _enrich(session, feed_items):
    """`enrich_event_team_data` as a stage that queries the request's session —
    and, like it, returns before any query when there is no event card."""
    if not any(item["type"] == "event" for item in feed_items):
        return
    await session.execute(text(f"SELECT 1 /* stage:{ENRICH} */"))
    for item in feed_items:
        item["data"]["home_team_data"] = {"name": item["data"]["home_team"]}


@pytest.fixture
def stages(monkeypatch):
    """Every stage `get_feed` records, in order — the downstream-stage witness."""
    import app.routes.feed as feed

    seen: list[str] = []
    orig = feed._record_feed_timing

    def spy(timings, started_at, previous_at, stage, *a, **k):
        seen.append(stage)
        return orig(timings, started_at, previous_at, stage, *a, **k)

    monkeypatch.setattr(feed, "_record_feed_timing", spy)
    return seen


@pytest.fixture
def captures(monkeypatch):
    abandoned: list[str] = []

    class _Capture:
        def abandon(self, reason):
            abandoned.append(reason)

        def __getattr__(self, name):  # any record_* call would be a leak
            raise AssertionError(f"capture.{name} called on an abandoned build")

    monkeypatch.setattr(
        "app.routes.feed.display_capture_from_request", lambda request: _Capture()
    )
    return abandoned


def _stall_db(stage, **kw) -> _StageSession:
    # Event 1 is a card a human ruled bad; the stage before review stalls.
    return _StageSession(
        [_card(1)], rows=[_decision(1, "needs_data_fix")], stall=stage, **kw
    )


def _assert_nothing_published(rig, redis):
    assert rig.remembered == [] and rig.published == [] and redis.setex_keys == []
    assert rc._inflight == {}


# --- with time to spare: both stages feed mandatory human review --------------


@pytest.mark.parametrize("path", [SPORTS, DISCOVER])
async def test_normal_budget_scores_enriches_then_reviews_and_publishes(
    monkeypatch, rig, stages, path
):
    db = _StageSession(
        [_card(1), _card(2)],
        rows=[_decision(1, "needs_data_fix"), _decision(2, "accepted_promote")],
    )
    redis = _Redis()

    resp = await _get(
        monkeypatch, db, redis, path=path, score=_score(db), enrich=_enrich
    )
    body = resp.json()

    assert resp.status_code == 200
    assert db.log.index(f"{SCORE}_sql") < db.log.index(f"{ENRICH}_sql")
    assert db.log.index(f"{ENRICH}_sql") < db.log.index("review_sql")
    assert _ids(body) == [2], "needs_data_fix must still suppress event 1"
    assert body["items"][0]["data"]["home_team_data"] == {"name": "Home 2"}
    assert body["cache"].get("reason") not in OUR_REASONS
    assert DOWNSTREAM <= set(stages)
    assert rig.remembered and rig.published, "a complete build is still shared truth"
    assert "rollback" not in db.log and "invalidate" not in db.log


# --- zero budget: the stage is never started ---------------------------------


async def test_zero_budget_admits_no_event_scoring(monkeypatch, rig, stages):
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", 0)
    db = _StageSession([_card(1)])
    redis = _Redis()
    entered = []

    async def score(*a, **k):
        entered.append(SCORE)
        return [dict(c) for c in db.cards]

    resp = await _get(monkeypatch, db, redis, score=score, enrich=_enrich)
    body = resp.json()

    assert entered == [], "scoring is not started at zero budget"
    assert f"{ENRICH}_sql" not in db.log and "review_sql" not in db.log
    assert body["items"] == [] and body["total"] == 0
    assert body["cache"]["status"] == "unavailable"
    assert body["cache"]["reason"] == "events_budget"
    assert body["cache"]["ttl_seconds"] == 0
    assert resp.headers["x-feed-singleflight"] == "none"
    assert not DOWNSTREAM & set(stages)
    assert rig.finished == ["None"], "the slot is released with no payload"
    _assert_nothing_published(rig, redis)


async def test_zero_budget_admits_no_team_enrichment(monkeypatch, rig, stages):
    db = _StageSession([_card(1)])
    redis = _Redis()
    spend = lambda: monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", 0)  # noqa: E731

    resp = await _get(
        monkeypatch, db, redis, score=_score(db, then=spend), enrich=_enrich
    )
    body = resp.json()

    assert f"{SCORE}_sql" in db.log
    assert f"{ENRICH}_sql" not in db.log, "enrichment is not started at zero budget"
    assert "review_sql" not in db.log
    assert body["cache"]["status"] == "unavailable"
    assert body["cache"]["reason"] == "enrichment_budget"
    assert body["items"] == [], "the unenriched card must not be served"
    assert not DOWNSTREAM & set(stages)
    assert rig.finished == ["None"]
    _assert_nothing_published(rig, redis)


async def test_excluded_events_create_no_budget_condition(monkeypatch, rig):
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", 0)
    db = _StageSession([_card(1)])
    entered = []

    async def score(*a, **k):
        entered.append(SCORE)
        return []

    resp = await _get(
        monkeypatch,
        db,
        _Redis(),
        path=SPORTS + "&include_events=false",
        score=score,
        enrich=_enrich,
    )

    assert entered == []
    assert resp.status_code == 200
    assert resp.json()["cache"].get("reason") not in OUR_REASONS


async def test_no_event_cards_to_enrich_creates_no_budget_condition(
    monkeypatch, rig, stages
):
    db = _StageSession([])
    spend = lambda: monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", 0)  # noqa: E731

    resp = await _get(
        monkeypatch, db, _Redis(), score=_score(db, then=spend), enrich=_enrich
    )

    assert f"{ENRICH}_sql" not in db.log
    assert resp.json()["cache"].get("reason") not in OUR_REASONS
    assert "golf" in stages, "the build goes on exactly as before"


# --- budget runs out mid-stage: cancel, release, finite cleanup, no leak -----


@pytest.mark.parametrize(
    "stage, reason, path",
    [
        (SCORE, "events_timeout", SPORTS),
        (SCORE, "events_timeout", DISCOVER),
        (ENRICH, "enrichment_timeout", SPORTS),
        (ENRICH, "enrichment_timeout", DISCOVER),
    ],
)
async def test_a_stalled_stage_is_cancelled_released_rolled_back_and_never_leaks(
    monkeypatch, rig, stages, captures, stage, reason, path
):
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _stall_db(stage)
    rig.db = db
    redis = _Redis()

    started = time.monotonic()
    resp = await _get(
        monkeypatch, db, redis, path=path, score=_score(db), enrich=_enrich
    )
    elapsed = time.monotonic() - started
    body = resp.json()

    assert resp.status_code == 200
    assert elapsed < _SHORT_BUDGET_MS / 1000 + 2.0 + 1.0, elapsed
    # Cancelled, the waiters released, THEN rolled back — and nothing after.
    assert db.after(f"{stage}_sql") == [
        f"{stage}_cancelled",
        "finish_build:None",
        "rollback",
    ]
    assert not DOWNSTREAM & set(stages), "no stage follows a cancelled session"
    assert body["items"] == [], "the incomplete build must not be served"
    assert body["cache"]["status"] == "unavailable"
    assert body["cache"]["reason"] == reason
    assert body["cache"]["ttl_seconds"] == 0
    assert resp.headers["x-feed-singleflight"] == "none"
    assert captures == [reason]
    _assert_nothing_published(rig, redis)


async def test_a_hung_rollback_after_a_stage_stall_is_bounded_and_invalidated(
    monkeypatch, rig
):
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _stall_db(ENRICH, rollback_hangs=True)
    rig.db = db

    started = time.monotonic()
    resp = await _get(monkeypatch, db, _Redis(), score=_score(db), enrich=_enrich)
    elapsed = time.monotonic() - started

    assert resp.json()["cache"]["reason"] == "enrichment_timeout"
    assert db.after(f"{ENRICH}_sql") == [
        f"{ENRICH}_cancelled",
        "finish_build:None",
        "rollback",
        "invalidate",
    ]
    assert elapsed < _SHORT_BUDGET_MS / 1000 + 2.0 + 1.0, elapsed


async def test_a_swallowed_cancellation_still_ends_the_build(monkeypatch, rig, stages):
    # Something inside scoring ate the deadline's cancellation and returned its
    # cards anyway. The stage returned; it did not finish inside the budget.
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _stall_db(SCORE, swallow=True)
    rig.db = db
    redis = _Redis()

    resp = await _get(monkeypatch, db, redis, score=_score(db), enrich=_enrich)
    body = resp.json()

    assert db.after(f"{SCORE}_sql") == [
        f"{SCORE}_cancelled",
        "finish_build:None",
        "rollback",
    ]
    assert body["cache"]["reason"] == "events_timeout"
    assert body["items"] == []
    assert not DOWNSTREAM & set(stages)
    _assert_nothing_published(rig, redis)


@pytest.mark.parametrize(
    "stage, reason", [(SCORE, "events_timeout"), (ENRICH, "enrichment_timeout")]
)
async def test_a_stage_stall_serves_the_prior_complete_payload_with_its_origin(
    monkeypatch, rig, stage, reason
):
    db = _StageSession([_card(1), _card(2)])
    complete = (
        await _get(monkeypatch, db, _Redis(), score=_score(db), enrich=_enrich)
    ).json()
    [key] = list(rc._last_good)
    stored_origin = rc._last_good[key][0]
    # Ten seconds into the live window, so the served TTL must shrink by ten.
    rc._last_good[key] = (stored_origin - 10, rc._last_good[key][1])
    rig.remembered.clear()
    rig.published.clear()
    rig.finished.clear()

    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db2 = _StageSession([_card(1), _card(2), _card(3)], stall=stage)
    redis = _Redis()
    resp = await _get(monkeypatch, db2, redis, score=_score(db2), enrich=_enrich)
    body = resp.json()

    assert resp.headers["x-feed-cache"] == "last_good"
    assert body["cache"]["status"] == "last_good"
    assert body["cache"]["reason"] == reason
    assert body["cache"]["live"] is True
    assert body["cache"]["built_at"] == pytest.approx(stored_origin - 10)
    assert body["cache"]["ttl_seconds"] <= FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS - 10
    assert _ids(body) == _ids(complete), "the prior payload, not the new build"
    assert rig.finished == ["None"]
    _assert_nothing_published(rig, redis)


async def test_a_stage_stall_refuses_a_live_prior_past_the_live_ceiling(
    monkeypatch, rig
):
    db = _StageSession([_card(1)])
    await _get(monkeypatch, db, _Redis(), score=_score(db), enrich=_enrich)
    [key] = list(rc._last_good)
    origin, payload = rc._last_good[key]
    rc._last_good[key] = (origin - FEED_LAST_GOOD_MAX_AGE_LIVE_SECONDS - 1, payload)

    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db2 = _StageSession([_card(1)], stall=SCORE)
    resp = await _get(monkeypatch, db2, _Redis(), score=_score(db2), enrich=_enrich)
    body = resp.json()

    assert body["cache"]["status"] == "unavailable"
    assert body["cache"]["reason"] == "events_timeout"
    assert body["items"] == []


async def test_a_coalesced_waiter_is_released_with_nothing_to_serve(monkeypatch, rig):
    monkeypatch.setattr(rc, "FEED_TOTAL_BUDGET_MS", _SHORT_BUDGET_MS)
    db = _stall_db(SCORE)
    rig.db = db
    redis = _Redis()

    async def _after_leader_enters_scoring():
        await asyncio.wait_for(db.stage_entered.wait(), timeout=10)

    leader, waiter = await _get(
        monkeypatch,
        db,
        redis,
        n=2,
        stagger=_after_leader_enters_scoring,
        score=_score(db),
        enrich=_enrich,
    )

    assert leader.json()["cache"]["reason"] == "events_timeout"
    assert waiter.headers["x-feed-singleflight"] == "waiter_unavailable"
    assert waiter.json()["items"] == []
    assert db.log.count(f"{SCORE}_sql") == 1, "the waiter never started a second build"
    assert rig.finished[0] == "None", "the waiters got no payload"
    _assert_nothing_published(rig, redis)


@pytest.mark.parametrize("stage", [SCORE, ENRICH])
async def test_request_cancellation_propagates_and_releases_the_slot(
    monkeypatch, rig, stage
):
    db = _stall_db(stage)
    rig.db = db
    redis = _Redis()

    task = asyncio.create_task(
        _get(monkeypatch, db, redis, score=_score(db), enrich=_enrich)
    )
    await asyncio.wait_for(db.stage_entered.wait(), timeout=10)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert db.after(f"{stage}_sql") == [
        f"{stage}_cancelled",
        "finish_build:None",
    ], "a cancelled request is not a timeout: no fallback, no cleanup SQL"
    _assert_nothing_published(rig, redis)


# --- ordinary scoring errors keep their existing policy ----------------------


@pytest.mark.parametrize(
    "error", [RuntimeError("scoring bug"), TimeoutError("a provider's own timeout")]
)
async def test_an_ordinary_scoring_error_is_still_logged_and_the_build_goes_on(
    monkeypatch, rig, stages, error
):
    # A TimeoutError raised INSIDE scoring is not the request deadline: it keeps
    # the catch-and-log policy, as it always had.
    db = _StageSession([_card(1)])

    async def score(*a, **k):
        raise error

    resp = await _get(monkeypatch, db, _Redis(), score=score, enrich=_enrich)

    assert resp.status_code == 200
    assert resp.json()["cache"].get("reason") not in OUR_REASONS
    assert "golf" in stages and "futures" in stages
    assert "rollback" not in db.log and "invalidate" not in db.log

"""live/046 — CERT-764: retry #3 must not settle on the count it started with.

CERT-753 blocked the drain for reporting `drained` while match pages stayed
thin. live/042 repaired both of its findings. CERT-764 then found the same
disease one layer down, and its repro is exact:

    a third failed fetch increments the Redis give-up counter while settlement
    still receives the PRE-trigger `state.gave_up`, so with an exhausted page
    and an empty retry hash it writes a permanent clean `drained`
    (`owed={}`, `gaveup += 1`, `done:us_open = drained`).

WHY THE THIRD FAILURE SPECIFICALLY. On failures one and two the event stays in
the retry hash, so `owed` is non-empty and `_settle_tier` returns
`awaiting_retries` before the give-up count is ever consulted — the stale count
is there the whole time and cannot be seen. The third failure is the one that
empties the hash AND increments the counter in the same pass. That is the only
pass where the settlement reads the counter, and it is exactly the pass where
the value it was handed is a trigger out of date. A defect that is invisible on
every input except one.

WHAT THE REPAIR HAD TO BE, verbatim from the cert: "settle with the
post-attempt give-up count and guard retry #3 through the returned and
persisted terminal verdict." So `_record_attempts` returns an `AttemptOutcome`
carrying the post-attempt total (the value `INCRBY` stored), the runner threads
it into `_settle_tier`, and `_settle_tier` returns the marker it persisted so
the report, Redis, and the next trigger's read-back all come from one decision.

Every test resolves the module lazily, for the reason the sibling file gives:
a module-level import of `AttemptOutcome` would collapse the file into one
collection error against the pre-fix tree, which is red for the wrong reason.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

BASE = datetime(2026, 9, 1, tzinfo=timezone.utc)


def _drain():
    import app.tasks.chart_backfill_thirty_day as module

    return module


#: 🔴 ONE FAKE, SHARED (live/047). It models MULTI/EXEC, bytes-on-the-wire hash
#: fields, `SET NX` refusing with `None`, and `INCRBY` answering with the value
#: it stored — all four of which some guard in this family turns on. It used to
#: be a per-file class; CERT-773's repair is about what a CONCURRENT READER can
#: see, and a per-file fake that publishes a transaction's commands one at a
#: time would make every interleaving guard green against a tree with no
#: transaction in it.
from tests.lib_tier_redis import FakeTierRedis as _FakeRedis  # noqa: E402


def _install(monkeypatch, drain, redis):
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: redis
    )
    monkeypatch.setattr(drain, "INTER_EVENT_SLEEP_SECONDS", 0)


# ---------------------------------------------------------------------------
# 1. The seam — `_record_attempts` hands back what it just persisted
# ---------------------------------------------------------------------------


def _record(drain, redis, attempted, failed, prior, prior_gave_up):
    original = drain._with_redis
    drain._with_redis = lambda tier, apply: apply(redis)
    try:
        return drain._record_attempts(
            "us_open", attempted, failed, prior, prior_gave_up,
        )
    finally:
        drain._with_redis = original


def test_the_third_failure_returns_the_post_attempt_give_up_total():
    """🔴 RED-FIRST. The count leaves the function, instead of only leaving for
    Redis where nothing in this trigger will read it again."""
    drain = _drain()
    redis = _FakeRedis()
    outcome = _record(
        drain, redis,
        attempted=[5], failed=[5],
        prior={5: drain.MAX_EVENT_RETRIES - 1}, prior_gave_up=0,
    )

    assert outcome.owed == {}, "the event leaves the hash on its last attempt"
    assert outcome.gave_up_total == 1, (
        "the give-up happened in THIS pass and the caller was not told"
    )
    assert redis.store["chart_backfill_30d:gaveup:us_open"] == 1, (
        "the returned total and the persisted total must be the same number"
    )


def test_the_returned_total_accumulates_on_top_of_what_redis_remembered():
    drain = _drain()
    redis = _FakeRedis({"chart_backfill_30d:gaveup:us_open": 4})
    outcome = _record(
        drain, redis,
        attempted=[5], failed=[5],
        prior={5: drain.MAX_EVENT_RETRIES - 1}, prior_gave_up=4,
    )

    assert outcome.gave_up_total == 5
    assert redis.store["chart_backfill_30d:gaveup:us_open"] == 5


def test_a_pass_that_gives_up_on_nobody_carries_the_prior_total_forward():
    """CONTROL. The total must not reset to zero on a clean pass — a tier that
    gave up earlier and finishes cleanly later still ends
    `drained_with_failures`."""
    drain = _drain()
    redis = _FakeRedis({"chart_backfill_30d:gaveup:us_open": 2})
    outcome = _record(
        drain, redis, attempted=[7], failed=[], prior={7: 1}, prior_gave_up=2,
    )

    assert outcome.owed == {}
    assert outcome.gave_up_total == 2


def test_an_unreachable_redis_still_reports_the_give_up_it_just_made():
    """FAIL TOWARD THE LOUDER VERDICT. If the counter cannot be persisted, the
    arithmetic answer stands — under-reporting here is the defect itself, and a
    tier wrongly ending `drained_with_failures` costs a re-trigger, while one
    wrongly ending `drained` is permanent."""
    drain = _drain()
    original = drain._with_redis
    drain._with_redis = lambda tier, apply: None  # every write swallowed
    try:
        outcome = drain._record_attempts(
            "us_open", [5], [5], {5: drain.MAX_EVENT_RETRIES - 1}, 0,
        )
    finally:
        drain._with_redis = original

    assert outcome.gave_up_total == 1


def test_a_concurrent_trigger_is_read_from_what_redis_actually_stored():
    """PERSISTED beats COMPUTED, which is why the INCRBY answer is read at all.

    `prior_gave_up` is a snapshot taken when this trigger read its checkpoint.
    A sibling trigger that abandoned an event in between makes the arithmetic
    `prior + len(gave_up)` an UNDERCOUNT, and undercounting is the whole CERT-764
    failure mode: the settlement two lines later turns `drained_with_failures`
    into a permanent clean `drained`. Redis's INCRBY returns the value it just
    stored, so that answer is the one that wins.

    Found by mutation: replacing `max(computed_total, persisted)` with
    `computed_total` left every other test in this file green.
    """
    drain = _drain()
    redis = _FakeRedis()
    # A sibling trigger got here first and banked four give-ups this tier's
    # checkpoint never saw.
    redis.store[drain.GAVE_UP_KEY.format(tier="us_open")] = 4

    outcome = _record(
        drain, redis, [5], [5], {5: drain.MAX_EVENT_RETRIES - 1}, prior_gave_up=0,
    )

    assert outcome.gave_up_total == 5, (
        "the settlement is using its own stale arithmetic instead of the count "
        "Redis actually holds — a concurrent trigger's give-ups vanish"
    )


# ---------------------------------------------------------------------------
# 2. The settlement — and it returns the verdict it persisted
# ---------------------------------------------------------------------------


def _finished_page(drain):
    return drain.DrainPage([], (BASE, 9), True, 0)


def test_settling_with_a_give_up_names_the_tier_by_its_failure(monkeypatch):
    drain = _drain()
    redis = _FakeRedis()
    _install(monkeypatch, drain, redis)
    report: dict = {}

    marker = drain._settle_tier(
        "us_open", _finished_page(drain), report,
        owed={}, gave_up=1, dry_run=False,
    )

    assert marker == drain.DONE_WITH_FAILURES, "the persisted verdict is returned"
    assert report["status"] == drain.DONE_WITH_FAILURES
    assert redis.store["chart_backfill_30d:done:us_open"] == drain.DONE_WITH_FAILURES


def test_a_genuinely_clean_finish_is_still_drained(monkeypatch):
    """CONTROL, green in BOTH arms. The repair must not turn every ending into
    `drained_with_failures` — that would be the same lie in the other
    direction, and the drain would never be able to say it finished."""
    drain = _drain()
    redis = _FakeRedis()
    _install(monkeypatch, drain, redis)
    report: dict = {}

    marker = drain._settle_tier(
        "us_open", _finished_page(drain), report,
        owed={}, gave_up=0, dry_run=False,
    )

    assert marker == drain.DONE_CLEAN
    assert redis.store["chart_backfill_30d:done:us_open"] == drain.DONE_CLEAN


def test_a_non_terminal_settlement_returns_no_marker(monkeypatch):
    """CONTROL. `awaiting_retries` and `in_progress` persist nothing terminal,
    so the caller must get `None` rather than a marker it could record."""
    drain = _drain()
    redis = _FakeRedis()
    _install(monkeypatch, drain, redis)

    assert drain._settle_tier(
        "us_open", _finished_page(drain), {},
        owed={9: 1}, gave_up=0, dry_run=False,
    ) is None
    assert drain._settle_tier(
        "us_open", drain.DrainPage([1], (BASE, 1), False, 1), {},
        owed={}, gave_up=0, dry_run=False,
    ) is None
    assert "chart_backfill_30d:done:us_open" not in redis.store


def test_the_give_up_count_is_reported_even_when_it_is_zero(monkeypatch):
    """A stale zero and an absent key read the same to whoever reads the
    verdict. Stamping it unconditionally is what makes them different."""
    drain = _drain()
    _install(monkeypatch, drain, _FakeRedis())
    report: dict = {}

    drain._settle_tier(
        "us_open", _finished_page(drain), report,
        owed={}, gave_up=0, dry_run=False,
    )

    assert report["gave_up"] == 0


# ---------------------------------------------------------------------------
# 3. The grader's scenario, through the whole runner
# ---------------------------------------------------------------------------


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _Row:
    def __init__(self, event_id):
        self.id = event_id


class _Session:
    def __init__(self, present):
        self._present = set(present)

    async def execute(self, statement):
        for param in statement.compile().params.values():
            if param in self._present:
                return _ScalarResult(_Row(param))
        return _ScalarResult(None)

    async def commit(self):
        return None


class _NullSessionCtx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def _wire_runner(monkeypatch, drain, redis, *, event_id, present=True):
    """The grader's exact head: ONE event, owed its final retry, and the venue
    refuses it again. No new ground behind it, so the page is exhausted."""
    import app.tasks.event_chart_backfill as engine

    _install(monkeypatch, drain, redis)

    session = _Session([event_id] if present else [])
    monkeypatch.setattr(
        "app.tasks.base.get_task_session", lambda: _NullSessionCtx(session)
    )

    class _Svc:
        async def close(self):
            return None

    monkeypatch.setattr("app.services.kalshi_api.KalshiAPIService", _Svc)
    monkeypatch.setattr("app.services.polymarket_api.PolymarketAPIService", _Svc)

    async def _tiers(_session):
        return {tier.name: [1] for tier in drain.TIERS}

    monkeypatch.setattr(drain, "tier_sport_ids", _tiers)

    async def _page(_session, **_kw):
        # Exhausted with nothing left to look at — the state in which the
        # settlement actually consults the give-up count.
        return drain.DrainPage([], (BASE, event_id), True, 0)

    monkeypatch.setattr(drain, "select_thirty_day_page", _page)

    async def _refuse(_session, event, **_kw):
        return {
            "status": "no_new_points",
            "sources": {"polymarket": {"status": "fetch_failed"}},
            "points_written": 0,
            "errors": ["the venue refused, again"],
        }

    monkeypatch.setattr(engine, "backfill_event_chart", _refuse)
    return session


async def test_the_certs_exact_head_reproduction_does_not_write_a_clean_drained(
    monkeypatch,
):
    """🔴 THE REPRODUCTION, and it is the reason this branch exists.

    `owed={}` after the pass, `gaveup += 1` during it, page exhausted. Against
    the blocked subject `66562633` this persists `done:us_open = drained` and
    the tier is permanently, cleanly finished over an event it abandoned.
    """
    drain = _drain()
    redis = _FakeRedis({"chart_backfill_30d:gaveup:us_open": 0})
    redis.hashes["chart_backfill_30d:retry:us_open"] = {
        "7007": str(drain.MAX_EVENT_RETRIES - 1)
    }
    _wire_runner(monkeypatch, drain, redis, event_id=7007)

    summary = await drain.run_thirty_day_chart_drain(
        limit=5, only_tier="us_open", dry_run=False,
    )
    tier = summary["tiers"]["us_open"]

    assert redis.hashes["chart_backfill_30d:retry:us_open"] == {}, (
        "precondition: the third attempt empties the retry hash"
    )
    assert redis.store["chart_backfill_30d:gaveup:us_open"] == 1, (
        "precondition: the third attempt increments the give-up counter"
    )
    assert redis.store["chart_backfill_30d:done:us_open"] != drain.DONE_CLEAN, (
        "a tier that just abandoned an event was marked permanently, cleanly "
        "drained — CERT-764's finding"
    )
    assert redis.store["chart_backfill_30d:done:us_open"] == (
        drain.DONE_WITH_FAILURES
    )
    assert tier["status"] == drain.DONE_WITH_FAILURES
    assert tier["gave_up"] == 1
    assert summary["status"] == drain.DONE_WITH_FAILURES


async def test_the_returned_and_the_persisted_verdict_are_the_same_verdict(
    monkeypatch,
):
    """🔴 The cert's second clause: "guard retry #3 through the RETURNED and
    PERSISTED terminal verdict". Two readers, one decision. A summary that says
    `drained_with_failures` over a Redis key that says `drained` would re-open
    the defect for the NEXT trigger, which reads Redis and not the summary."""
    drain = _drain()
    redis = _FakeRedis({"chart_backfill_30d:gaveup:us_open": 0})
    redis.hashes["chart_backfill_30d:retry:us_open"] = {
        "7007": str(drain.MAX_EVENT_RETRIES - 1)
    }
    _wire_runner(monkeypatch, drain, redis, event_id=7007)

    summary = await drain.run_thirty_day_chart_drain(
        limit=5, only_tier="us_open", dry_run=False,
    )
    tier = summary["tiers"]["us_open"]

    assert tier["persisted_done_marker"] == redis.store[
        "chart_backfill_30d:done:us_open"
    ]
    assert tier["persisted_done_marker"] == tier["status"]
    # And the next trigger reads back the same thing.
    assert drain._read_checkpoint("us_open").done == drain.DONE_WITH_FAILURES
    assert drain._read_checkpoint("us_open").gave_up == 1


async def test_a_tier_that_finishes_without_abandoning_anyone_still_drains_clean(
    monkeypatch,
):
    """CONTROL, and the one that stops this repair from becoming a blanket
    `drained_with_failures`. Same wiring, but the retry SUCCEEDS."""
    import app.tasks.event_chart_backfill as engine

    drain = _drain()
    redis = _FakeRedis({"chart_backfill_30d:gaveup:us_open": 0})
    redis.hashes["chart_backfill_30d:retry:us_open"] = {
        "7007": str(drain.MAX_EVENT_RETRIES - 1)
    }
    _wire_runner(monkeypatch, drain, redis, event_id=7007)

    async def _answers(_session, event, **_kw):
        return {
            "status": "filled",
            "sources": {"polymarket": {"status": "ok", "points": 12}},
            "points_written": 12,
            "errors": [],
        }

    monkeypatch.setattr(engine, "backfill_event_chart", _answers)

    summary = await drain.run_thirty_day_chart_drain(
        limit=5, only_tier="us_open", dry_run=False,
    )

    assert redis.store["chart_backfill_30d:gaveup:us_open"] == 0
    assert redis.store["chart_backfill_30d:done:us_open"] == drain.DONE_CLEAN
    assert summary["tiers"]["us_open"]["status"] == drain.DONE_CLEAN


async def test_the_second_failure_is_still_awaiting_retries_not_terminal(
    monkeypatch,
):
    """CONTROL, and it is the reason the defect hid. On attempt two the event
    stays in the hash, so the settlement never reaches the give-up count at
    all. This must keep being true, or the repair would have papered over the
    bound that makes retries finite."""
    drain = _drain()
    redis = _FakeRedis({"chart_backfill_30d:gaveup:us_open": 0})
    redis.hashes["chart_backfill_30d:retry:us_open"] = {"7007": "1"}
    _wire_runner(monkeypatch, drain, redis, event_id=7007)

    summary = await drain.run_thirty_day_chart_drain(
        limit=5, only_tier="us_open", dry_run=False,
    )

    assert summary["tiers"]["us_open"]["status"] == "awaiting_retries"
    assert "chart_backfill_30d:done:us_open" not in redis.store
    assert redis.hashes["chart_backfill_30d:retry:us_open"] == {"7007": "2"}
    assert redis.store["chart_backfill_30d:gaveup:us_open"] == 0


def test_a_dry_run_still_persists_nothing(monkeypatch):
    """CONTROL, green in both arms. The new return value must not become a new
    write path."""
    drain = _drain()
    redis = _FakeRedis()
    _install(monkeypatch, drain, redis)

    marker = drain._settle_tier(
        "us_open", _finished_page(drain), {},
        owed={}, gave_up=3, dry_run=True,
    )

    assert marker == drain.DONE_WITH_FAILURES, "it still says what it decided"
    assert redis.store == {}, "and it still wrote nothing"


def test_the_outcome_is_a_named_pair_not_a_bare_dict():
    """The seam itself. `_record_attempts` returning a bare hash is what made
    the give-up count impossible to hand on without a second Redis read."""
    drain = _drain()
    outcome = _record(drain, _FakeRedis(), [1], [], {}, 0)

    assert isinstance(outcome, drain.AttemptOutcome)
    assert outcome._fields == ("owed", "gave_up_total")
    assert isinstance(MagicMock() and outcome.owed, dict)

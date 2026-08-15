"""The Kalshi cliff drain (#1586, queue 355).

These tests lock down the four properties that separate a drain from a rescan,
each of which has a named prior failure behind it:

* BOTH bounds on an expiring population (gotcha #41, and its inverse).
* A watermark that advances past outcomes that yield NOTHING — otherwise an
  empty leading edge pins the sweep in place forever.
* An empty 200 is disambiguated before any claim is written (gotcha #53).
* A run that could not persist its watermark reports FAILED, not progress.
"""

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import kalshi_cliff as drain
from app.utils.kalshi_retention import (
    AT_RISK_AGE_DAYS,
    PROVABLY_PURGED_AGE_DAYS,
)


class _Row:
    def __init__(self, outcome_id, ticker, resolution_date):
        self.outcome_id = outcome_id
        self.ticker = ticker
        self.resolution_date = resolution_date


def _cohort(pairs):
    """Rows oldest-first, spaced a day apart inside the retention window."""
    base = datetime.now(timezone.utc) - timedelta(days=PROVABLY_PURGED_AGE_DAYS - 2)
    return [
        _Row(oid, ticker, base + timedelta(days=i))
        for i, (oid, ticker) in enumerate(pairs)
    ]


class _FakeResult:
    def __init__(self, rows=None, scalar=0):
        self._rows = rows or []
        self._scalar = scalar

    def fetchall(self):
        return self._rows

    def scalar(self):
        return self._scalar

    def one(self):
        return self._rows[0] if self._rows else None


#: Bound parameters that land on a ``timestamptz`` column, and therefore must
#: arrive as a ``datetime``. asyncpg does not cast at this boundary — psycopg2
#: would have, which is why the habit is easy to keep and the failure is not.
_TIMESTAMPTZ_PARAMS = ("cursor_date",)


class _AsyncpgDataError(TypeError):
    """Stands in for ``asyncpg.exceptions.DataError`` (#1884).

    The real class is not importable from a pure-unit test without a driver
    connection, and the point being tested is the TYPE that crosses the bind,
    not the identity of the exception raised on the other side.
    """


class _FakeSession:
    """In-memory session that is STRICT ABOUT BIND TYPES, deliberately.

    The original double accepted ``params`` and discarded it. Every watermark
    test therefore passed while production threw ``asyncpg.DataError`` on its
    first statement of every run (#1884): the drain bound its cold-start
    watermark as an ISO *string* into a ``timestamptz`` comparison. No test
    could have caught it, because no test could see a bind at all.

    So this double now enforces what the driver enforces. That is what makes
    the pre-existing behavioural tests above and below real evidence rather
    than a description of the fake.
    """

    def __init__(self, rows):
        self._rows = rows
        self.committed = 0
        self.bound_params = []

    def _typecheck(self, params):
        if not params:
            return
        for name in _TIMESTAMPTZ_PARAMS:
            if name not in params:
                continue
            value = params[name]
            if not isinstance(value, datetime):
                raise _AsyncpgDataError(
                    "invalid input for query argument "
                    f"${name}: {value!r} (expected a datetime.datetime "
                    f"instance, got {type(value).__name__!r}). "
                    f"{name} is compared against fm.resolution_date, which is "
                    "DateTime(timezone=True) -> timestamptz."
                )

    async def execute(self, statement, params=None):
        sql = str(statement)
        self._typecheck(params)
        if params:
            self.bound_params.append(dict(params))
        if "ORDER BY fm.resolution_date ASC" in sql:
            return _FakeResult(rows=self._rows)
        if "count(*)" in sql:
            return _FakeResult(scalar=0)
        return _FakeResult()

    async def commit(self):
        self.committed += 1


class _FakeService:
    def __init__(self, candles_by_ticker, markets):
        self._candles = candles_by_ticker
        self._markets = markets
        self.candle_calls = []
        self.market_calls = []

    async def get_market_candlesticks(self, ticker, period_interval=60,
                                      start_ts=None, end_ts=None):
        self.candle_calls.append((ticker, start_ts, end_ts))
        return self._candles.get(ticker, [])

    async def get_market(self, ticker):
        self.market_calls.append(ticker)
        return self._markets.get(ticker)

    async def close(self):
        pass


def _install_fakes(monkeypatch, *, rows, candles_by_ticker, markets):
    """Wire the drain to in-memory doubles and capture what it persists."""
    import contextlib

    session = _FakeSession(rows)
    service = _FakeService(candles_by_ticker, markets)
    captured = {"state": drain._default_state(), "service": service,
                "session": session}

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    monkeypatch.setattr(drain, "get_task_session", _fake_session)
    monkeypatch.setattr(drain, "load_state", lambda: drain._default_state())
    monkeypatch.setattr(
        drain, "save_state", lambda s: (captured.update(state=dict(s)), True)[1]
    )
    monkeypatch.setattr(
        "app.services.kalshi_api.KalshiAPIService", lambda *a, **k: service
    )
    return captured


class TestCohortBounds:
    """An expiring population needs a floor AND an ordering (gotcha #41)."""

    def test_floor_uses_the_measured_constant_not_a_hand_count(self):
        src = inspect.getsource(drain)
        assert "PROVABLY_PURGED_AGE_DAYS" in src
        # A predicate cannot consume a range written in prose (gotcha #35).
        assert "86" not in drain._COHORT_SQL, "the horizon must not be inlined"

    def test_cohort_is_bounded_below_by_the_retention_floor(self):
        assert "make_interval(days => :purge_days)" in drain._COHORT_SQL
        assert ">= now() - make_interval(days => :purge_days)" in drain._COHORT_SQL

    def test_cohort_is_ordered_oldest_first_inside_that_floor(self):
        assert "ORDER BY fm.resolution_date ASC, fo.id ASC" in drain._COHORT_SQL

    def test_the_two_horizons_are_distinct_and_correctly_ordered(self):
        # Warn on the lower bound, skip work on the upper one.
        assert AT_RISK_AGE_DAYS < PROVABLY_PURGED_AGE_DAYS


class TestWatermark:
    """The property the old rail lacked: it can page past barren rows."""

    def test_cohort_query_filters_on_the_cursor(self):
        assert "(fm.resolution_date, fo.id) > (:cursor_date, :cursor_id)" in (
            drain._COHORT_SQL
        )

    def test_the_cursor_tuple_matches_the_sort_key(self):
        """A watermark on a different key than the ORDER BY skips or repeats."""
        assert "ORDER BY fm.resolution_date ASC, fo.id ASC" in drain._COHORT_SQL
        assert "(fm.resolution_date, fo.id) >" in drain._COHORT_SQL

    def test_a_fresh_state_starts_at_the_epoch_not_at_null(self):
        """NULL in a row-value comparison matches nothing — the drain would
        select zero rows forever and report itself caught up."""
        params = drain._cursor_params(drain._default_state())
        assert params["cursor_date"] == drain._EPOCH
        assert params["cursor_id"] == 0

    # ----------------------------------------------------------------
    # #1884 — the cold watermark's TYPE, not just its value.
    #
    # The test directly above shipped green while the rail threw on every
    # run. It compared `_cursor_params()["cursor_date"]` against `_EPOCH`,
    # the same constant the production line binds — so it restated the
    # assignment and could not fail whatever the type was. The type is the
    # entire defect: `fm.resolution_date` is timestamptz, and asyncpg
    # refuses a `str` there instead of casting it.
    # ----------------------------------------------------------------

    def test_the_cold_watermark_binds_as_a_datetime_not_an_iso_string(self):
        """The #1884 defect, pinned at the bind.

        Asserting the TYPE is what the value comparison above could not do.
        """
        params = drain._cursor_params(drain._default_state())
        assert isinstance(params["cursor_date"], datetime), (
            "the cold-start watermark must bind as a datetime: "
            "fm.resolution_date is DateTime(timezone=True), so asyncpg "
            "raises DataError on a str rather than casting it, and the "
            "drain fails before its first fetch — permanently, because the "
            "cold path is the only path a never-advancing watermark takes."
        )
        assert params["cursor_date"].tzinfo is not None, (
            "a naive datetime against timestamptz is a silent timezone guess"
        )

    def test_a_warm_watermark_binds_as_a_datetime_too(self):
        """The warm path stores an ISO string in Redis and must parse it back.

        `state["cursor_date"] = row.resolution_date.isoformat()` is JSON-safe
        by necessity, so EVERY resumed run re-enters through a string. Fixing
        only the epoch would have moved the failure from run 1 to run 2.
        """
        moment = datetime(2026, 6, 1, 12, 30, tzinfo=timezone.utc)
        state = drain._default_state()
        state["cursor_date"] = moment.isoformat()
        state["cursor_id"] = 4242

        params = drain._cursor_params(state)

        assert isinstance(params["cursor_date"], datetime)
        assert params["cursor_date"] == moment
        assert params["cursor_id"] == 4242

    def test_an_unparseable_watermark_degrades_to_the_epoch_and_does_not_throw(
        self,
    ):
        """Ruling 039 — a lookup must never throw.

        A corrupt watermark costs a re-sweep of rows already known barren.
        Raising costs the rail, which is exactly the outage being fixed.
        """
        state = drain._default_state()
        state["cursor_date"] = "not-a-date"
        params = drain._cursor_params(state)
        assert params["cursor_date"] == drain._EPOCH

    @pytest.mark.asyncio
    async def test_a_cold_start_completes_a_first_drain_through_a_strict_bind(
        self, monkeypatch
    ):
        """watermark=None -> a real first drain, with the driver's type rule on.

        This is the end-to-end shape #1884 asked for. It runs the rail from a
        DEFAULT state (cursor_date None, cursor_id 0) against a session that
        rejects a non-datetime bind the way asyncpg does. On the shipped code
        the very first `session.execute` raises, `outcomes_seen` is 0 and the
        terminal is `failed` — which is what production recorded twice.
        """
        rows = _cohort([(31, "KX-A"), (32, "KX-B")])
        saved = _install_fakes(
            monkeypatch, rows=rows, candles_by_ticker={}, markets={}
        )
        session = saved["session"]

        result = await drain.run_cliff_drain(limit=10)

        # It reached the rows at all — the bind was accepted.
        assert result["run"]["outcomes_seen"] == 2
        assert not result.get("errors"), result.get("errors")
        # And the watermark left its cold value, which is the property whose
        # absence made the failure permanent rather than merely repeated.
        assert saved["state"]["cursor_id"] == 32
        assert saved["state"]["cursor_date"] == rows[-1].resolution_date.isoformat()

        cold_binds = [
            p for p in session.bound_params if p.get("cursor_id") == 0
        ]
        assert cold_binds, "the cohort query never ran with the cold watermark"
        assert all(
            isinstance(p["cursor_date"], datetime) for p in cold_binds
        )

    @pytest.mark.asyncio
    async def test_the_strict_session_actually_rejects_a_string_watermark(self):
        """The guard's own control.

        A double that enforces nothing is the thing that let #1884 ship. This
        proves the strictness above is real, so a future change that reverts
        `_cursor_params` to an ISO string fails loudly rather than passing
        against a permissive fake.
        """
        session = _FakeSession(rows=[])
        with pytest.raises(_AsyncpgDataError):
            await session.execute(
                "SELECT 1 WHERE (fm.resolution_date, fo.id) > "
                "(:cursor_date, :cursor_id)",
                {"cursor_date": "1970-01-01T00:00:00+00:00", "cursor_id": 0},
            )

    @pytest.mark.asyncio
    async def test_watermark_advances_over_outcomes_that_yield_nothing(
        self, monkeypatch
    ):
        """The whole difference from a rescan, tested by behaviour not by grep.

        A barren leading edge is the expected state of this cohort — most of
        the oldest rows inside the window are outcomes Kalshi never traded or
        has already purged. If the watermark only moved on a successful fetch,
        the sweep would re-select those same rows every hour and never reach
        the ones that still have history.
        """
        rows = _cohort([(11, "KX-A"), (12, "KX-B"), (13, "KX-C")])
        saved = _install_fakes(
            monkeypatch, rows=rows, candles_by_ticker={}, markets={}
        )

        result = await drain.run_cliff_drain(limit=10)

        assert result["run"]["outcomes_seen"] == 3
        assert result["run"]["snapshots_created"] == 0
        # Every row was barren, and the watermark still sits on the LAST one.
        assert saved["state"]["cursor_id"] == 13
        assert saved["state"]["cursor_date"] == rows[-1].resolution_date.isoformat()

    @pytest.mark.asyncio
    async def test_a_truncated_run_banks_the_rows_it_did_reach(
        self, monkeypatch
    ):
        """A deadline must cost the remainder of the run, never the progress."""
        rows = _cohort([(21, "KX-A"), (22, "KX-B"), (23, "KX-C")])
        saved = _install_fakes(
            monkeypatch, rows=rows, candles_by_ticker={}, markets={}
        )
        # A deadline already in the past stops the loop before the first row.
        import time as _time

        result = await drain.run_cliff_drain(
            limit=10, deadline=_time.monotonic() - 1
        )
        assert result["run"]["outcomes_seen"] == 0
        assert saved["state"]["cursor_id"] == 0


class TestCheckpointArithmetic:
    """Repeated checkpoints inside one run must not inflate the totals."""

    def test_checkpoint_is_idempotent_within_a_run(self, monkeypatch):
        written = {}
        monkeypatch.setattr(
            drain, "save_state", lambda s: (written.update(s), True)[1]
        )
        state = drain._default_state()
        state["outcomes_seen"] = 100
        state["snapshots_created"] = 5000
        base = {"outcomes_seen": 100, "snapshots_created": 5000}
        run = {"outcomes_seen": 25, "snapshots_created": 900}

        drain._checkpoint(state, base, run)
        assert state["outcomes_seen"] == 125
        # Same checkpoint again (a second flush in the same run) must not add
        # the deltas twice.
        drain._checkpoint(state, base, run)
        assert state["outcomes_seen"] == 125
        assert state["snapshots_created"] == 5900

    def test_totals_accumulate_across_runs(self, monkeypatch):
        monkeypatch.setattr(drain, "save_state", lambda s: True)
        state = {**drain._default_state(), "outcomes_seen": 100}
        base = {"outcomes_seen": 100}
        drain._checkpoint(state, base, {"outcomes_seen": 25})
        # Next run's base is the new total.
        base2 = {"outcomes_seen": state["outcomes_seen"]}
        drain._checkpoint(state, base2, {"outcomes_seen": 40})
        assert state["outcomes_seen"] == 165


class TestTerminal:
    """"It returned" is not "it worked" (gotcha #53 / task_verdict)."""

    def test_a_failed_checkpoint_is_failed_even_with_snapshots_written(self):
        """Unresumable progress is progress that will be redone."""
        run = {"outcomes_seen": 50, "snapshots_created": 900}
        assert drain._terminal(run, False, checkpoint_ok=False, errors=[]) == "failed"

    def test_a_run_error_is_failed(self):
        run = {"outcomes_seen": 10}
        assert (
            drain._terminal(run, False, True, ["run_error: boom"]) == "failed"
        )

    def test_progress_is_partial_never_complete(self):
        """A cohort is still expiring; a working sweep must not read GREEN."""
        assert drain._terminal({"outcomes_seen": 400}, False, True, []) == "partial"

    def test_complete_only_when_the_window_is_caught_up(self):
        assert drain._terminal({"outcomes_seen": 0}, True, True, []) == "complete"

    def test_no_rows_without_exhaustion_is_not_complete(self):
        assert drain._terminal({"outcomes_seen": 0}, False, True, []) == "no_work"


class TestEmptyAnswerDisambiguation:
    """gotcha #53: an empty 200 is a response SHAPE, not an absence."""

    def test_empty_buckets_are_kept_separate(self):
        state = drain._default_state()
        for bucket in ("empty_purged", "empty_present", "empty_unprobed"):
            assert bucket in state, f"{bucket} must be counted on its own"

    def test_existence_probe_uses_the_only_404_bearing_call(self):
        """`get_market` returns None for 404 and ONLY for 404; candlesticks and
        trades both answer 200-with-nothing for a purged market."""
        src = inspect.getsource(drain._drain_one)
        assert "service.get_market(" in src
        assert "market is None" in src

    def test_unprobed_empties_are_never_folded_into_an_explanation(self):
        src = inspect.getsource(drain._drain_one)
        probe_off = src.index("if not probe_empties:")
        following = src[probe_off:probe_off + 200]
        assert "empty_unprobed" in following
        assert "empty_purged" not in following

    def test_probe_budget_is_bounded(self):
        assert drain.MAX_EXISTENCE_PROBES > 0
        assert "probes_used < MAX_EXISTENCE_PROBES" in inspect.getsource(
            drain.run_cliff_drain
        )

    @pytest.mark.asyncio
    async def test_purged_and_never_traded_are_counted_apart(self, monkeypatch):
        """The two facts an empty 200 cannot distinguish, distinguished.

        `KX-GONE` 404s on the market lookup: Kalshi deleted it, a fact about
        RETENTION. `KX-QUIET` still exists: it simply never traded, a fact
        about the MARKET. The old rail called both `api_empty` and a run that
        recovered nothing looked identical to a run with nothing to do.
        """
        rows = _cohort([(31, "KX-GONE"), (32, "KX-QUIET")])
        _install_fakes(
            monkeypatch,
            rows=rows,
            candles_by_ticker={},
            markets={"KX-QUIET": {"ticker": "KX-QUIET"}},   # KX-GONE → None/404
        )

        result = await drain.run_cliff_drain(limit=10)

        assert result["run"]["empty_purged"] == 1
        assert result["run"]["empty_present"] == 1
        assert result["run"]["empty_unprobed"] == 0

    @pytest.mark.asyncio
    async def test_a_zero_yield_run_is_never_terminal_complete(self, monkeypatch):
        """500 fetched, 500 empty, 0 created, recorded SUCCESS every 6h for ten
        weeks — the #683 shape this rail must not reproduce."""
        rows = _cohort([(41, "KX-A"), (42, "KX-B")])
        _install_fakes(monkeypatch, rows=rows, candles_by_ticker={}, markets={})

        result = await drain.run_cliff_drain(limit=10)
        assert result["run"]["snapshots_created"] == 0
        assert result["terminal"] == "partial"

        from app.utils.task_verdict import NOT_GREEN, classify_summary

        assert classify_summary(result).verdict in NOT_GREEN


class TestYield:
    """The happy path: history found inside the window actually lands."""

    @pytest.mark.asyncio
    async def test_candles_become_snapshots_and_seed_the_opening(
        self, monkeypatch
    ):
        rows = _cohort([(51, "KX-LIVE")])
        fakes = _install_fakes(
            monkeypatch,
            rows=rows,
            candles_by_ticker={
                "KX-LIVE": [
                    {"t": 1_750_000_000, "yes_price": 0.31},
                    {"t": 1_750_003_600, "yes_price": 0.48},
                    # Degenerate prices are dropped, not stored as 0/1.
                    {"t": 1_750_007_200, "yes_price": 0.0},
                    {"t": 1_750_010_800, "yes_price": 1.0},
                ]
            },
            markets={},
        )

        result = await drain.run_cliff_drain(limit=10)

        assert result["run"]["snapshots_created"] == 2
        assert result["run"]["outcomes_with_history"] == 1
        # No existence probe is spent when the answer was non-empty.
        assert fakes["service"].market_calls == []

    @pytest.mark.asyncio
    async def test_the_fetch_window_brackets_the_markets_own_settlement(
        self, monkeypatch
    ):
        """Not `now-90d..now`, which barely overlaps an 80-day-old market."""
        rows = _cohort([(61, "KX-OLD")])
        fakes = _install_fakes(
            monkeypatch, rows=rows, candles_by_ticker={}, markets={}
        )

        await drain.run_cliff_drain(limit=10)

        ticker, start_ts, end_ts = fakes["service"].candle_calls[0]
        settled = rows[0].resolution_date.timestamp()
        assert ticker == "KX-OLD"
        assert start_ts < settled < end_ts
        assert (settled - start_ts) >= drain.LOOKBACK_DAYS * 86400 - 1


class TestCandlestickWindow:
    """The window is anchored on the market's settlement, not on now."""

    def test_range_is_derived_from_resolution_date(self):
        src = inspect.getsource(drain._drain_one)
        assert "resolution_date - timedelta(days=LOOKBACK_DAYS)" in src
        assert "resolution_date + timedelta(days=1)" in src

    def test_start_and_end_are_passed_explicitly(self):
        """The client default (now-90d..now) barely overlaps an 80-day-old
        market's life — the exact cohort this rail exists for."""
        src = inspect.getsource(drain._drain_one)
        assert "start_ts=start_ts" in src
        assert "end_ts=end_ts" in src


class TestRemainingCount:
    """A capped count reported as a total is the silent-truncation failure."""

    def test_remaining_is_bounded(self):
        assert ":cap" in drain._REMAINING_SQL
        assert "LIMIT :cap" in drain._REMAINING_SQL

    def test_the_cap_is_reported(self):
        src = inspect.getsource(drain._count_remaining)
        assert '"capped"' in src

    def test_an_unmeasurable_count_is_none_not_zero(self):
        src = inspect.getsource(drain._count_remaining)
        assert '"count": None' in src, (
            "a failed count must not report 0 remaining — that reads as done"
        )

    def test_remaining_uses_the_same_predicate_as_the_cohort(self):
        """Otherwise progress is measured against a different population."""
        for clause in (
            "fm.source = 'kalshi'",
            "fm.status = 'resolved'",
            ">= now() - make_interval(days => :purge_days)",
            "(fm.resolution_date, fo.id) > (:cursor_date, :cursor_id)",
        ):
            assert clause in drain._COHORT_SQL
            assert clause in drain._REMAINING_SQL


class TestWiring:
    def test_task_is_registered_and_scheduled(self):
        from app.tasks import celery_app

        assert "app.tasks.kalshi_cliff_drain" in celery_app.tasks
        entry = celery_app.conf.beat_schedule["kalshi-cliff-drain"]
        assert entry["task"] == "app.tasks.kalshi_cliff_drain"

    def test_the_beat_is_at_least_hourly(self):
        """Fetch-now-or-never: ~7,800 markets/week cross the horizon, so the
        drain must outpace expiry rather than merely make progress."""
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["kalshi-cliff-drain"]
        sched = entry["schedule"]
        # crontab(minute=N) → every hour.
        assert sched.hour == set(range(24)), "the drain must run hourly"

    def test_admin_endpoints_exist(self):
        from app.routes import admin_providers

        paths = {r.path for r in admin_providers.router.routes}
        assert "/kalshi/cliff-drain" in paths
        assert "/kalshi/cliff-drain/run" in paths

    def test_soft_limit_leaves_the_drain_room_to_checkpoint(self):
        """A drain SIGKILLed before its watermark write loses the whole run
        (project_celery_sigkill_untracked)."""
        from app.tasks import celery_app

        task = celery_app.tasks["app.tasks.kalshi_cliff_drain"]
        src = inspect.getsource(drain.run_cliff_drain)
        assert "deadline" in src
        assert task.soft_time_limit and task.soft_time_limit >= 780

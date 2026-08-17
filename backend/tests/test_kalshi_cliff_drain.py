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


class _AtRiskCount:
    """The row shape ``_count_at_risk`` reads."""

    def __init__(self, ahead=0, expiring_soon=0):
        self.ahead = ahead
        self.expiring_soon = expiring_soon


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

    def __init__(self, rows, at_risk_rows=None, at_risk_count=None,
                 remaining_count=0):
        self._rows = rows
        self._remaining_count = remaining_count
        # The at-risk pass is a SEPARATE population on a SEPARATE watermark.
        # Feeding it the main cohort's rows would have every test silently
        # process each outcome twice, so it is empty unless a test asks for it.
        self._at_risk_rows = at_risk_rows or []
        self._at_risk_count = at_risk_count or _AtRiskCount()
        self.committed = 0
        self.bound_params = []
        self.at_risk_queries = 0

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
        if "/* at_risk_pass_count */" in sql:
            return _FakeResult(rows=[self._at_risk_count])
        if "/* at_risk_pass */" in sql:
            self.at_risk_queries += 1
            return _FakeResult(rows=self._at_risk_rows)
        if "ORDER BY fm.resolution_date ASC" in sql:
            return _FakeResult(rows=self._rows)
        if "count(*)" in sql:
            return _FakeResult(scalar=self._remaining_count)
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


def _install_fakes(
    monkeypatch, *, rows, candles_by_ticker, markets,
    at_risk_rows=None, at_risk_count=None, state=None, remaining_count=0,
):
    """Wire the drain to in-memory doubles and capture what it persists."""
    import contextlib

    session = _FakeSession(rows, at_risk_rows=at_risk_rows,
                           at_risk_count=at_risk_count,
                           remaining_count=remaining_count)
    service = _FakeService(candles_by_ticker, markets)
    captured = {"state": drain._default_state(), "service": service,
                "session": session}

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    def _load_state():
        base = drain._default_state()
        if state:
            base.update(state)
        return base

    monkeypatch.setattr(drain, "get_task_session", _fake_session)
    monkeypatch.setattr(drain, "load_state", _load_state)
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


# ==========================================================================
# Queue 359 (#1892): the cap is a shape problem, and liveness is what hid it
# ==========================================================================


def _at_risk_cohort(pairs, *, age_days):
    """Rows inside the 74-86d band, oldest-first."""
    base = datetime.now(timezone.utc) - timedelta(days=age_days)
    return [
        _Row(oid, ticker, base + timedelta(hours=i))
        for i, (oid, ticker) in enumerate(pairs)
    ]


class TestAtRiskPass:
    """A one-way watermark cannot serve a population that expires behind it.

    The main cursor walks FORWARD through resolution_date while the retention
    floor walks forward behind it, so a row examined at 20 days old is never
    looked at again and dies at 86 regardless. Measured 2026-08-17: 15,712
    uncovered outcomes sit behind the watermark inside the window, matching the
    rail's own `empty_present + empty_unprobed` (15,792) — i.e. all of them.
    """

    def test_the_band_is_bounded_on_both_sides(self):
        # Gotcha #41 in both directions at once: a floor so the sweep never
        # spends itself on the provably-dead, and a ceiling so it is the band
        # and not the whole window.
        assert ">= now() - make_interval(days => :purge_days)" in drain._AT_RISK_SQL
        assert "<  now() - make_interval(days => :at_risk_days)" in drain._AT_RISK_SQL

    def test_the_band_uses_the_measured_constants_not_hand_counts(self):
        # A predicate cannot consume a range written in prose (gotcha #35).
        for literal in ("74", "86"):
            assert literal not in drain._AT_RISK_SQL
            assert literal not in drain._AT_RISK_COUNT_SQL

    def test_the_band_is_ordered_closest_to_death_first(self):
        assert "ORDER BY fm.resolution_date ASC, fo.id ASC" in drain._AT_RISK_SQL

    def test_the_at_risk_pass_has_its_own_watermark(self):
        """Sharing the main cursor would make the two passes fight over one
        position and each would undo the other's progress."""
        state = drain._default_state()
        assert "at_risk_cursor_date" in state
        assert "at_risk_cursor_id" in state
        # Distinct keys, and the SQL reads the at-risk one.
        src = inspect.getsource(drain.run_cliff_drain)
        assert "_at_risk_cursor_params(state)" in src
        assert 'state["at_risk_cursor_id"] = int(row.outcome_id)' in src

    def test_at_risk_cursor_binds_a_datetime_not_an_iso_string(self):
        """#1884 again: asyncpg does not cast at a timestamptz bind, and a
        second watermark is a second chance to make the bind that self-blocked
        the entire rail for its whole life."""
        params = drain._at_risk_cursor_params({"at_risk_cursor_date": "2026-07-01"})
        assert isinstance(params["cursor_date"], datetime)
        assert params["cursor_date"].tzinfo is not None

    @pytest.mark.asyncio
    async def test_at_risk_rows_are_drained_and_their_watermark_advances(
        self, monkeypatch
    ):
        at_risk = _at_risk_cohort([(91, "KX-DYING")], age_days=80)
        captured = _install_fakes(
            monkeypatch,
            rows=[],
            at_risk_rows=at_risk,
            candles_by_ticker={"KX-DYING": [{"t": 1_750_000_000, "yes_price": 0.4}]},
            markets={},
        )

        result = await drain.run_cliff_drain(limit=40)

        assert result["run"]["at_risk_outcomes_seen"] == 1
        assert result["run"]["at_risk_with_history"] == 1
        assert result["run"]["snapshots_created"] == 1
        assert captured["state"]["at_risk_cursor_id"] == 91

    @pytest.mark.asyncio
    async def test_the_at_risk_pass_runs_before_the_main_pass(self, monkeypatch):
        """The reserve exists because a step promised 'later, bounded' is a
        step that never runs — poll_kalshi's empty-event backfill is sitting on
        exactly that promise and has never executed."""
        order = []

        at_risk = _at_risk_cohort([(101, "KX-BAND")], age_days=80)
        main = _cohort([(102, "KX-MAIN")])
        fakes = _install_fakes(
            monkeypatch, rows=main, at_risk_rows=at_risk,
            candles_by_ticker={}, markets={},
        )
        original = fakes["service"].get_market_candlesticks

        async def _tracking(ticker, **kwargs):
            order.append(ticker)
            return await original(ticker, **kwargs)

        fakes["service"].get_market_candlesticks = _tracking

        await drain.run_cliff_drain(limit=40)

        assert order == ["KX-BAND", "KX-MAIN"]

    @pytest.mark.asyncio
    async def test_the_at_risk_budget_is_a_fraction_of_the_run_not_the_whole(
        self, monkeypatch
    ):
        """It must never be able to starve the main drain."""
        fakes = _install_fakes(
            monkeypatch, rows=[], candles_by_ticker={}, markets={},
        )
        result = await drain.run_cliff_drain(limit=400)
        assert result["saturation"]["at_risk_limit"] == 100
        assert result["saturation"]["at_risk_limit"] < 400
        # And the query was actually issued with that bound.
        band = [
            p for p in fakes["session"].bound_params
            if p.get("at_risk_days") is not None and "limit" in p
        ]
        assert band and band[0]["limit"] == 100

    @pytest.mark.asyncio
    async def test_expiring_rows_left_by_a_capped_pass_are_a_FAILED_run(
        self, monkeypatch
    ):
        """The one condition here that is a LOSS and not a backlog."""
        at_risk = _at_risk_cohort(
            [(200 + i, f"KX-{i}") for i in range(25)], age_days=84
        )
        _install_fakes(
            monkeypatch, rows=[], at_risk_rows=at_risk,
            candles_by_ticker={}, markets={},
            at_risk_count=_AtRiskCount(ahead=900, expiring_soon=120),
        )

        result = await drain.run_cliff_drain(limit=100, at_risk_limit=25)

        assert result["saturation"]["at_risk_cap_bound"] is True
        assert result["at_risk"]["expiring_soon"] == 120
        assert result["terminal"] == "failed"
        assert any("IMMINENT LOSS" in n for n in result["notes"])

    @pytest.mark.asyncio
    async def test_a_backlog_the_pass_worked_through_is_not_a_failure(
        self, monkeypatch
    ):
        """Rows left ahead of a pass that ran out of ROWS is a contradiction;
        only a pass that ran out of BUDGET is the rail failing."""
        at_risk = _at_risk_cohort([(301, "KX-ONE")], age_days=80)
        _install_fakes(
            monkeypatch, rows=_cohort([(302, "KX-MAIN")]), at_risk_rows=at_risk,
            candles_by_ticker={}, markets={},
            at_risk_count=_AtRiskCount(ahead=0, expiring_soon=0),
        )

        result = await drain.run_cliff_drain(limit=100, at_risk_limit=25)

        assert result["saturation"]["at_risk_cap_bound"] is False
        assert result["terminal"] == "partial"

    def test_an_unmeasurable_at_risk_count_never_trips_the_alarm(self):
        """A missing probe is a finding, not a zero — and not a red either."""
        assert drain._terminal(
            {"outcomes_seen": 5}, False, True, [],
            at_risk_expiring=None, at_risk_cap_bound=True,
        ) == "partial"


class TestSaturation:
    """`outcomes_seen == limit` on every run is the signal, and nothing said so.

    Measured across 21 consecutive production runs (#1892): exactly 400 every
    single time. A rail quietly pinned at its cap looks identical to a rail
    comfortably keeping up.
    """

    @pytest.mark.asyncio
    async def test_a_run_that_hits_its_cap_says_so_loudly(self, monkeypatch):
        rows = _cohort([(400 + i, f"KX-S{i}") for i in range(5)])
        _install_fakes(monkeypatch, rows=rows, candles_by_ticker={}, markets={})

        result = await drain.run_cliff_drain(limit=5, at_risk_limit=0)

        assert result["saturation"]["cap_bound"] is True
        assert result["saturation"]["outcomes_seen"] == 5
        assert any("SATURATED" in n for n in result["notes"])

    @pytest.mark.asyncio
    async def test_a_run_under_its_cap_is_not_reported_as_saturated(
        self, monkeypatch
    ):
        rows = _cohort([(500, "KX-U")])
        _install_fakes(monkeypatch, rows=rows, candles_by_ticker={}, markets={})

        result = await drain.run_cliff_drain(limit=50, at_risk_limit=0)

        assert result["saturation"]["cap_bound"] is False
        assert not any("SATURATED" in n for n in result["notes"])

    @pytest.mark.asyncio
    async def test_the_streak_is_what_distinguishes_pinned_from_busy(
        self, monkeypatch
    ):
        """One capped run is a busy hour. Twenty-one is a cap-bound rail."""
        rows = _cohort([(600 + i, f"KX-T{i}") for i in range(3)])
        _install_fakes(
            monkeypatch, rows=rows, candles_by_ticker={}, markets={},
            state={"cap_bound_streak": 20, "runs": 20},
        )

        result = await drain.run_cliff_drain(limit=3, at_risk_limit=0)

        assert result["saturation"]["cap_bound_streak"] == 21


class TestConvergence:
    """Is `remaining` FALLING — the question liveness cannot answer.

    Every instrument on both #1892 and #1586 asked whether the task was
    MOVING: runs incrementing, cursors distinct, fetch_errors zero, wraps
    advancing. All read healthy. Movement is not progress.
    """

    def test_one_point_is_not_a_trend(self):
        """#1892 was itself filed on a two-point 'trend' that reversed sign on
        the third reading. One point must never be read optimistically."""
        out = drain.convergence([{"run": 1, "at": "2026-08-17T00:00:00+00:00",
                                  "remaining": 100}])
        assert out["verdict"] == "insufficient_data"
        assert out["samples"] == 1

    def test_an_empty_ring_is_insufficient_not_converging(self):
        assert drain.convergence([])["verdict"] == "insufficient_data"

    def test_unmeasured_remainings_are_skipped_not_counted_as_zero(self):
        """A failed count reads as `None`; treating it as 0 would fake a
        collapse to an empty backlog."""
        out = drain.convergence([
            {"run": 1, "at": "2026-08-17T00:00:00+00:00", "remaining": None},
            {"run": 2, "at": "2026-08-17T01:00:00+00:00", "remaining": None},
        ])
        assert out["verdict"] == "insufficient_data"
        assert out["samples"] == 0

    def test_a_falling_backlog_is_converging(self):
        out = drain.convergence([
            {"run": 25, "at": "2026-08-15T22:00:00+00:00", "remaining": 121818},
            {"run": 65, "at": "2026-08-17T15:00:00+00:00", "remaining": 109830},
        ])
        assert out["verdict"] == "converging"
        assert out["span_runs"] == 40
        assert out["per_run"] == -299.7
        assert out["runs_to_empty"] == 366

    def test_a_rising_backlog_is_diverging(self):
        out = drain.convergence([
            {"run": 23, "at": "2026-08-15T18:00:00+00:00", "remaining": 121279},
            {"run": 25, "at": "2026-08-15T20:00:00+00:00", "remaining": 121818},
        ])
        assert out["verdict"] == "diverging"
        assert out["delta"] == 539

    def test_a_flat_backlog_is_neither(self):
        out = drain.convergence([
            {"run": 1, "at": "2026-08-17T00:00:00+00:00", "remaining": 1000},
            {"run": 20, "at": "2026-08-17T19:00:00+00:00", "remaining": 1005},
        ])
        assert out["verdict"] == "flat"

    def test_convergence_never_raises_on_a_poisoned_ring(self):
        """A metric that can crash the rail it measures is worse than no
        metric (ruling 039)."""
        assert drain.convergence("not a list")["verdict"] in (
            "insufficient_data", "unmeasured"
        )
        assert drain.convergence([{"remaining": "x"}, None])["verdict"] == (
            "insufficient_data"
        )

    @pytest.mark.asyncio
    async def test_saturated_and_not_converging_is_stated_in_one_note(
        self, monkeypatch
    ):
        """The exact conjunction gotcha #41 describes: a bounded run whose
        bound sits below its inflow. Neither half alone says it."""
        rows = _cohort([(700 + i, f"KX-C{i}") for i in range(2)])
        _install_fakes(
            monkeypatch, rows=rows, candles_by_ticker={}, markets={},
            state={
                "runs": 5,
                "history": [
                    {"run": 1, "at": "2026-08-17T00:00:00+00:00", "remaining": 500},
                    {"run": 5, "at": "2026-08-17T04:00:00+00:00", "remaining": 500},
                ],
            },
            remaining_count=500,
        )

        result = await drain.run_cliff_drain(limit=2, at_risk_limit=0)

        assert result["saturation"]["cap_bound"] is True
        assert result["convergence"]["verdict"] in ("flat", "diverging")
        assert any("NOT CONVERGING" in n for n in result["notes"])

    @pytest.mark.asyncio
    async def test_the_ring_is_bounded(self, monkeypatch):
        captured = _install_fakes(
            monkeypatch, rows=[], candles_by_ticker={}, markets={},
            state={"history": [
                {"run": i, "at": "2026-08-17T00:00:00+00:00", "remaining": i}
                for i in range(200)
            ]},
        )
        await drain.run_cliff_drain(limit=10, at_risk_limit=0)
        assert len(captured["state"]["history"]) == drain.CONVERGENCE_RING


class TestDegenerateCandles:
    """"No candles came back" and "every candle was 0 or 1" are not one fact."""

    @pytest.mark.asyncio
    async def test_all_degenerate_prices_are_not_reported_as_never_traded(
        self, monkeypatch
    ):
        rows = _cohort([(800, "KX-DEGEN")])
        _install_fakes(
            monkeypatch, rows=rows, markets={},
            candles_by_ticker={"KX-DEGEN": [
                {"t": 1_750_000_000, "yes_price": 0.0},
                {"t": 1_750_003_600, "yes_price": 1.0},
            ]},
        )

        result = await drain.run_cliff_drain(limit=10, at_risk_limit=0)

        assert result["run"]["degenerate_candles"] == 1
        assert result["run"]["empty_present"] == 0
        assert result["run"]["snapshots_created"] == 0


class TestProgressEndpointBudget:
    """#1892 §2: this issue's own instrument H12'd for two days.

    `cliff_drain_progress` fired sequential probes at 25s EACH against
    Heroku's 30s hard router cap, so once any two were slow the endpoint could
    not succeed at all.
    """

    def test_the_probe_budgets_sum_to_under_the_router_cap(self):
        probes = 3  # remaining + at_risk + census
        assert drain.PROGRESS_PROBE_TIMEOUT_S * probes < 30

    def test_the_human_path_is_tighter_than_the_task_path(self):
        assert drain.PROGRESS_PROBE_TIMEOUT_S < drain.TASK_PROBE_TIMEOUT_S

    def test_progress_passes_the_tighter_budget_to_every_probe(self):
        src = inspect.getsource(drain.cliff_drain_progress)
        assert src.count("timeout_s=PROGRESS_PROBE_TIMEOUT_S") == 3

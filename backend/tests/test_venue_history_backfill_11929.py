"""#11929 PR-A: Kalshi's hourly candles for recently settled markets are kept before the venue purges them.

PILLAR: TRUTH. SHIP: a settled futures market keeps the price journey the venue
recorded for it, past Kalshi's 47-86 day purge. This PR only PRESERVES the rows
(``venue_history_points``); serving them on charts is PR-B.

THE CASES:

* the switch: off (the default) means no venue call, no database statement, no
  Redis lease, from the task body and from the run function;
* the bounds: every env var read per run, clamped, garbage means the default;
* the cohort: settled in the last 45 days, oldest settlement first, nothing
  older than the floor (never past 86 days), open and non-Kalshi markets
  excluded, done and thrice-failed markets skipped. The SQL itself runs on the
  real-PostgreSQL rig (``SEARCH_TEST_DATABASE_URL``); a skip is not a pass;
* the legs: the chart's top 10 by probability plus every winner;
* the price: ``candle_yes_price`` decides it; an empty book, a lone 0.99 ask, a
  terminal 0/1 price and a candle after settlement are refused, never stored;
* idempotency: a rerun inserts 0 (``ON CONFLICT DO NOTHING``, real PG);
* the rate: the row throttle sleeps to the configured rate on a fake clock, the
  venue is paced at 2 req/s, the wall budget ends the run and the leg it
  interrupted is not marked done;
* a 429 stops the run without being swallowed, and nothing else is caught
  around the request;
* the verdict line carries the counts, and an empty cohort is never GREEN;
* the migration builds exactly the models' tables (offline, and on real PG).
"""

from __future__ import annotations

import importlib.util
import logging
import os
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table
from sqlalchemy.dialects import postgresql

import app.tasks.venue_history_backfill as vhb
from app.models.models import VenueHistoryBackfillProgress, VenueHistoryPoint
from app.tasks.venue_history_backfill import (
    BackfillSettings,
    CohortMarket,
    Leg,
    RunClock,
    backfill_once,
    candle_point,
    cohort_window,
    leg_groups,
    read_settings,
    request_span,
    run_venue_history_backfill,
    select_chart_legs,
)
from app.utils.task_verdict import COMPLETE, PARTIAL, UNKNOWN, verdict_for
from tests.pm_bulk_test_support import cleanup_pg_engines  # noqa: F401 — autouse schema cleanup

UTC = timezone.utc
NOW = datetime(2026, 11, 4, 20, 0, tzinfo=UTC)
BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "venue_history_points_11929.py"


# ---------------------------------------------------------------------------
# Builders and fakes
# ---------------------------------------------------------------------------


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())


def candle(end: datetime, *, bid=None, ask=None, last=None) -> dict:
    def side(v):
        return {"close_dollars": None if v is None else f"{v:.4f}"}

    return {
        "end_period_ts": _ts(end),
        "yes_bid": side(bid),
        "yes_ask": side(ask),
        "price": {"close_dollars": None if last is None else f"{last:.4f}"},
    }


def market(mid=1, *, settled_days_ago=10.0, life_days=20.0, legs_done=(), attempts=0):
    settle = NOW - timedelta(days=settled_days_ago)
    return CohortMarket(
        market_id=mid,
        event_ticker=f"KXEVT-{mid}",
        settle_ts=settle,
        listed_at=settle - timedelta(days=life_days),
        legs_done=frozenset(legs_done),
        attempts=attempts,
    )


def leg(oid, mid=1, *, prob=0.1, winner=False, ticker=None):
    return Leg(
        outcome_id=oid,
        market_id=mid,
        ticker=ticker if ticker is not None else f"KXEVT-{mid}-L{oid}",
        current_probability=prob,
        is_winner=winner,
    )


def settings(**kw) -> BackfillSettings:
    base = dict(enabled=True, rows_per_min=1_000_000, markets_per_run=50, wall_budget_s=600)
    base.update(kw)
    return BackfillSettings(**base)


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


class FakeStore:
    """In-memory store with the PG store's semantics (see the real-PG tests)."""

    def __init__(self, markets=(), legs=None):
        self.markets = list(markets)
        self.legs = legs or {}
        self.rows: dict = {}
        self.progress: dict = {}
        self.cohort_calls: list = []
        self.statements = 0

    async def select_cohort(self, *, floor, ceiling, limit, max_attempts):
        self.statements += 1
        self.cohort_calls.append(dict(floor=floor, ceiling=ceiling, limit=limit, max_attempts=max_attempts))
        out = []
        for m in sorted(self.markets, key=lambda m: (m.settle_ts, m.market_id)):
            p = self.progress.get(m.market_id)
            if p and (p["status"] == "done" or p["attempts"] >= max_attempts):
                continue
            if floor <= m.settle_ts <= ceiling:
                out.append(replace(
                    m,
                    legs_done=frozenset(p["legs_done"]) if p else frozenset(),
                    attempts=p["attempts"] if p else 0,
                ))
        return out[:limit]

    async def load_legs(self, market_ids):
        self.statements += 1
        return {mid: list(self.legs.get(mid, [])) for mid in market_ids}

    async def insert_points(self, points):
        self.statements += 1
        new = 0
        for p in points:
            key = (p.outcome_id, p.observed_at)
            if key not in self.rows:
                self.rows[key] = p
                new += 1
        return new

    async def record_progress(self, market_id, *, status, legs_done, attempts_inc, points_inserted, last_error):
        self.statements += 1
        p = self.progress.setdefault(
            market_id, {"status": None, "legs_done": [], "attempts": 0, "points": 0, "last_error": None}
        )
        p["status"] = status
        p["legs_done"] = sorted(legs_done)
        p["attempts"] += attempts_inc
        p["points"] += points_inserted
        p["last_error"] = last_error


def http_error(code: int) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://api.elections.kalshi.com/trade-api/v2/markets/candlesticks")
    return httpx.HTTPStatusError(f"{code}", request=req, response=httpx.Response(code, request=req))


class FakeService:
    """Answers candles per ticker for the asked window; can raise per call number."""

    def __init__(self, candles_by_ticker=None, *, raises=None, cost_s=0.0, clock=None):
        self.candles_by_ticker = candles_by_ticker or {}
        self.raises = raises or {}
        self.calls: list[dict] = []
        self.cost_s = cost_s
        self.clock = clock

    async def get_markets_candlesticks_raw(self, tickers, period_interval=60, start_ts=None, end_ts=None):
        self.calls.append(dict(tickers=list(tickers), period_interval=period_interval, start_ts=start_ts, end_ts=end_ts))
        if self.clock is not None:
            self.clock.t += self.cost_s
        exc = self.raises.get(len(self.calls))
        if exc is not None:
            raise exc
        out = {}
        for t in tickers:
            if t in self.candles_by_ticker:
                out[t] = [
                    c for c in self.candles_by_ticker[t]
                    if start_ts <= c["end_period_ts"] < end_ts
                ]
        return out

    async def close(self):
        pass


def hourly(m: CohortMarket, *, hours: int, prob=0.4):
    """``hours`` tight-book candles ending just before settlement."""
    start = m.settle_ts - timedelta(hours=hours)
    return [
        candle(start + timedelta(hours=h), bid=prob - 0.01, ask=prob + 0.01)
        for h in range(hours)
    ]


async def _run(store, service, clock=None, **kw):
    clock = clock or FakeClock()
    return await backfill_once(
        store, service, settings(**kw), now=NOW, clock=clock, sleep=clock.sleep
    )


# ---------------------------------------------------------------------------
# The switch
# ---------------------------------------------------------------------------


class TestTheSwitch:
    async def test_off_by_default_no_venue_call_no_db_statement(self, monkeypatch):
        import app.services.kalshi_api as kalshi_api
        import app.tasks.base as base

        def boom(*a, **k):
            raise AssertionError("touched while the switch is off")

        monkeypatch.setattr(kalshi_api, "KalshiAPIService", boom)
        monkeypatch.setattr(base, "get_task_session", boom)
        store = FakeStore([market()], {1: [leg(11)]})
        for env in ({}, {"VENUE_GAP_BACKFILL_ENABLED": "0"}, {"VENUE_GAP_BACKFILL_ENABLED": "off"}):
            result = await run_venue_history_backfill(environ=env, store=store, service=FakeService())
            assert result["status"] == "disabled"
        assert store.statements == 0

    async def test_on_the_run_does_read_the_store(self):
        """Control for the test above: the same call with the switch on does work."""
        store = FakeStore([market()], {1: [leg(11)]})
        result = await run_venue_history_backfill(
            environ={"VENUE_GAP_BACKFILL_ENABLED": "1"}, store=store,
            service=FakeService(), now=NOW, clock=FakeClock(), sleep=FakeClock().sleep,
        )
        assert result["terminal"] == "complete" and store.statements > 0

    def test_task_body_off_returns_before_redis_and_the_run(self, monkeypatch):
        import app.tasks as tasks
        import app.utils.single_flight as sf

        def boom(*a, **k):
            raise AssertionError("lease or run reached with the switch off")

        monkeypatch.delenv("VENUE_GAP_BACKFILL_ENABLED", raising=False)
        monkeypatch.setattr(sf, "single_flight", boom)
        monkeypatch.setattr(vhb, "run_venue_history_backfill", boom)
        result = tasks.backfill_venue_history_gaps()
        assert result["status"] == "disabled"

    def test_settings_are_read_every_run_and_clamped(self):
        s = read_settings({})
        assert (s.enabled, s.rows_per_min, s.markets_per_run, s.wall_budget_s) == (False, 1000, 50, 600)
        s = read_settings({
            "VENUE_GAP_BACKFILL_ENABLED": "Kalshi",
            "VENUE_GAP_BACKFILL_ROWS_PER_MIN": "250",
            "VENUE_GAP_BACKFILL_MARKETS_PER_RUN": "9999",
            "VENUE_GAP_BACKFILL_WALL_S": "5",
        })
        assert (s.enabled, s.rows_per_min, s.markets_per_run, s.wall_budget_s) == (True, 250, 500, 30)
        s = read_settings({"VENUE_GAP_BACKFILL_ROWS_PER_MIN": "lots", "VENUE_GAP_BACKFILL_WALL_S": "9000"})
        assert (s.rows_per_min, s.wall_budget_s) == (1000, 720)


# ---------------------------------------------------------------------------
# Cohort and legs
# ---------------------------------------------------------------------------


class TestCohort:
    def test_the_window_is_45_days_and_never_past_the_purge(self):
        floor, ceiling = cohort_window(NOW)
        assert ceiling == NOW
        assert floor == NOW - timedelta(days=45)
        assert vhb.CAPTURE_PLANNING_AGE_DAYS == 45
        assert NOW - floor < timedelta(days=vhb.PROVABLY_PURGED_AGE_DAYS)

    async def test_the_run_asks_for_the_window_cap_and_attempt_limit(self):
        store = FakeStore()
        summary = await _run(store, FakeService(), markets_per_run=7)
        [call] = store.cohort_calls
        assert call == dict(floor=NOW - timedelta(days=45), ceiling=NOW, limit=7, max_attempts=3)
        assert summary["terminal"] == "no_work"

    async def test_oldest_settled_first_and_the_cap_holds(self):
        ms = [market(i, settled_days_ago=d) for i, d in ((1, 3), (2, 40), (3, 20), (4, 44), (5, 50))]
        legs = {m.market_id: [leg(m.market_id * 10, m.market_id)] for m in ms}
        service = FakeService()
        summary = await _run(FakeStore(ms, legs), service, markets_per_run=2)
        asked = [c["tickers"][0].split("-")[1] for c in service.calls]
        assert asked == ["4", "2"]  # 44 days, then 40; 50 is outside the floor
        assert (summary["completed"], summary["total"]) == (2, 2)

    def test_the_sql_is_oldest_first_resolved_kalshi_within_the_floor(self):
        sql = " ".join(vhb.COHORT_SQL.split())
        assert "fm.source = 'kalshi'" in sql and "fm.status = 'resolved'" in sql
        assert "LEAST(fm.settled_at, fm.resolution_date) >= :floor" in sql
        assert "LEAST(fm.settled_at, fm.resolution_date) <= :ceiling" in sql
        assert "fm.settled_at >= :floor" in sql  # sargable twin of the LEAST bound
        assert "ORDER BY settle_ts ASC, fm.id ASC" in sql
        assert "p.status <> 'done' AND p.attempts < :max_attempts" in sql


class TestLegs:
    def test_top_ten_by_probability_plus_every_winner(self):
        legs = [leg(i, prob=i / 100) for i in range(1, 16)]
        legs.append(leg(99, prob=0.0, winner=True))
        chosen = select_chart_legs(legs)
        assert [lg.outcome_id for lg in chosen] == [15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 99]

    def test_no_ticker_is_skipped_and_a_ticker_is_fetched_once(self):
        legs = [leg(1, prob=0.5, ticker=""), leg(2, prob=0.4, ticker="T"), leg(3, prob=0.3, ticker="T")]
        assert [lg.outcome_id for lg in select_chart_legs(legs)] == [2]

    def test_groups_fit_the_candle_budget_and_never_exceed_twelve(self):
        m = market(life_days=20)
        start, end = request_span(m)
        groups = leg_groups([f"T{i}" for i in range(30)], start, end)
        assert max(len(g) for g in groups) == 12
        long_m = market(life_days=200)
        start, end = request_span(long_m)
        periods = (end - start) // 3600
        groups = leg_groups([f"T{i}" for i in range(5)], start, end)
        assert all(len(g) * periods <= 9000 + len(g) for g in groups)

    def test_the_span_runs_from_listing_minus_margin_to_settlement(self):
        m = market(settled_days_ago=10, life_days=20)
        start, end = request_span(m)
        assert end == _ts(m.settle_ts)
        assert start <= _ts(m.listed_at - timedelta(days=7))
        assert start % 3600 == 0


# ---------------------------------------------------------------------------
# The price
# ---------------------------------------------------------------------------


class TestCandleConversion:
    SETTLE = NOW - timedelta(days=10)

    def point(self, c):
        return candle_point(c, outcome_id=7, market_id=1, settle_ts=self.SETTLE)

    def test_a_tight_book_is_the_mid(self):
        p, why = self.point(candle(self.SETTLE - timedelta(hours=1), bid=0.40, ask=0.44, last=0.10))
        assert why is None and p.probability == pytest.approx(0.42)
        assert (p.price_basis, float(p.yes_bid), float(p.yes_ask)) == ("mid", 0.40, 0.44)
        assert p.observed_at == self.SETTLE - timedelta(hours=1)

    def test_a_wide_book_is_the_last_trade(self):
        p, _ = self.point(candle(self.SETTLE - timedelta(hours=2), bid=0.05, ask=0.88, last=0.07))
        assert (p.probability, p.price_basis) == (0.07, "last_trade")

    @pytest.mark.parametrize("c, reason", [
        (dict(bid=0.0, ask=1.0, last=None), "no_price"),        # settled shell
        (dict(bid=0.0, ask=0.99, last=None), "no_price"),       # lone ask on an empty book
        (dict(bid=None, ask=None, last=None), "no_price"),
        (dict(bid=0.999999, ask=1.0, last=None), "terminal"),   # rounds to 1.000000
    ])
    def test_no_honest_price_is_refused(self, c, reason):
        p, why = self.point(candle(self.SETTLE - timedelta(hours=3), **c))
        assert p is None and why == reason

    @pytest.mark.parametrize("offset", [timedelta(hours=1), timedelta(0)])
    def test_a_candle_at_or_after_settlement_is_refused(self, offset):
        p, why = self.point(candle(self.SETTLE + offset, bid=0.40, ask=0.44))
        assert p is None and why == "post_settlement"

    def test_the_price_comes_from_candle_yes_price(self, monkeypatch):
        monkeypatch.setattr(vhb, "candle_yes_price", lambda c: 0.333)
        p, _ = self.point(candle(self.SETTLE - timedelta(hours=1), bid=0.40, ask=0.44))
        assert p.probability == 0.333

    async def test_refusals_are_counted_and_never_stored(self):
        m = market()
        t = "KXEVT-1-L11"
        cs = [
            candle(m.settle_ts - timedelta(hours=2), bid=0.40, ask=0.42),
            candle(m.settle_ts - timedelta(hours=1), bid=0.0, ask=1.0),
            candle(m.settle_ts - timedelta(minutes=30), bid=0.999999, ask=1.0),
        ]
        store = FakeStore([m], {1: [leg(11)]})
        summary = await _run(store, FakeService({t: cs}))
        assert len(store.rows) == 1
        assert summary["refused"] == {"no_price": 1, "terminal": 1}
        assert summary["refused_total"] == 2


# ---------------------------------------------------------------------------
# The run: idempotency, throttle, pacing, budget, 429, verdict
# ---------------------------------------------------------------------------


class TestTheRun:
    async def test_writes_points_marks_done_and_a_rerun_inserts_zero(self):
        m = market()
        legs = [leg(11, prob=0.6), leg(12, prob=0.3)]
        cs = {lg.ticker: hourly(m, hours=24) for lg in legs}
        store = FakeStore([m], {1: legs})
        first = await _run(store, FakeService(cs))
        assert (first["rows_inserted"], first["rows_present"]) == (48, 0)
        assert store.progress[1]["status"] == "done"
        assert store.progress[1]["legs_done"] == [11, 12]
        # A done market is not selected again.
        again = await _run(store, FakeService(cs))
        assert again["total"] == 0
        # Forced rerun (progress lost): the rows conflict, nothing doubles.
        store.progress.clear()
        rerun = await _run(store, FakeService(cs))
        assert (rerun["rows_inserted"], rerun["rows_present"]) == (0, 48)
        assert len(store.rows) == 48

    async def test_the_row_throttle_sleeps_to_the_rate(self):
        m = market(life_days=60)
        lg = leg(11)
        store = FakeStore([m], {1: [lg]})
        clock = FakeClock()
        summary = await _run(
            store, FakeService({lg.ticker: hourly(m, hours=1200)}), clock=clock,
            rows_per_min=600, wall_budget_s=720,
        )
        assert summary["rows_inserted"] == 1200
        # 500 rows at 600/min is due at 50 s; 1,000 at 100 s; 1,200 at 120 s.
        assert clock.t == pytest.approx(120.0, abs=1.0)
        assert sum(clock.sleeps) >= 119.0
        assert summary["terminal"] == "complete"

    async def test_the_wall_budget_ends_the_run_and_the_leg_is_not_marked_done(self):
        m = market(life_days=120)
        legs = [leg(11, prob=0.6), leg(12, prob=0.3)]
        cs = {lg.ticker: hourly(m, hours=2000) for lg in legs}
        store = FakeStore([m, market(2, settled_days_ago=5)], {1: legs, 2: [leg(21, 2)]})
        clock = FakeClock()
        service = FakeService(cs)
        summary = await _run(store, service, clock=clock, rows_per_min=1000, wall_budget_s=60)
        assert summary["stopped_by"] == "row_throttle"
        assert summary["rows_inserted"] <= 1000 + vhb.INSERT_CHUNK_ROWS
        assert clock.t <= 60.0
        assert store.progress[1]["status"] == "in_progress"
        assert store.progress[1]["legs_done"] == []
        assert 2 not in store.progress  # the next market was never started
        assert summary["terminal"] == "partial"
        assert verdict_for(vhb.TASK_LABEL, summary).verdict == PARTIAL

    async def test_a_resumed_market_skips_the_legs_already_done(self):
        m = market(legs_done=[11])
        legs = [leg(11, prob=0.6), leg(12, prob=0.3)]
        service = FakeService({lg.ticker: hourly(m, hours=5) for lg in legs})
        store = FakeStore([m], {1: legs})
        store.progress[1] = {"status": "in_progress", "legs_done": [11], "attempts": 0, "points": 0, "last_error": None}
        await _run(store, service)
        assert {t for c in service.calls for t in c["tickers"]} == {"KXEVT-1-L12"}
        assert store.progress[1]["legs_done"] == [11, 12]

    async def test_requests_are_paced_at_two_per_second(self):
        ms = [market(i, settled_days_ago=10 + i) for i in range(1, 5)]
        store = FakeStore(ms, {m.market_id: [leg(m.market_id * 10, m.market_id)] for m in ms})
        clock = FakeClock()
        summary = await _run(store, FakeService(), clock=clock)
        assert summary["requests"] == 4
        assert clock.sleeps == [0.5, 0.5, 0.5]

    async def test_a_429_stops_the_run_and_is_not_counted_as_a_market_failure(self):
        ms = [market(i, settled_days_ago=30 - i) for i in range(1, 4)]
        store = FakeStore(ms, {m.market_id: [leg(m.market_id * 10, m.market_id)] for m in ms})
        service = FakeService(raises={2: http_error(429)})
        summary = await _run(store, service)
        assert len(service.calls) == 2  # the third market is never asked
        assert summary["stopped_by"] == "venue_429"
        assert summary["terminal"] == "partial"
        assert store.progress[2]["attempts"] == 0 and store.progress[2]["status"] == "in_progress"
        assert 3 not in store.progress
        assert verdict_for(vhb.TASK_LABEL, summary).verdict == PARTIAL

    async def test_another_venue_error_fails_that_market_and_the_run_moves_on(self):
        ms = [market(i, settled_days_ago=30 - i) for i in range(1, 4)]
        store = FakeStore(ms, {m.market_id: [leg(m.market_id * 10, m.market_id)] for m in ms})
        service = FakeService(raises={1: http_error(500)})
        summary = await _run(store, service)
        assert store.progress[1]["attempts"] == 1 and store.progress[1]["status"] == "failed"
        assert store.progress[3]["status"] == "done"
        assert summary["markets_failed"] == 1 and summary["errors"] == ["1:http_500"]
        assert verdict_for(vhb.TASK_LABEL, summary).verdict == PARTIAL

    async def test_nothing_else_is_caught_around_the_request(self):
        store = FakeStore([market()], {1: [leg(11)]})
        service = FakeService(raises={1: RuntimeError("a bug, not a venue answer")})
        with pytest.raises(RuntimeError):
            await _run(store, service)

    async def test_the_verdict_line_carries_the_counts(self, caplog):
        m = market()
        legs = [leg(11, prob=0.6), leg(12, prob=0.3)]
        cs = {legs[0].ticker: hourly(m, hours=3)}  # leg 12: the venue returns nothing
        caplog.set_level(logging.INFO, logger=vhb.__name__)
        summary = await _run(FakeStore([m], {1: legs}), FakeService(cs))
        [line] = [r.getMessage() for r in caplog.records if "venue_history_backfill verdict=" in r.getMessage()]
        for part in ("verdict=complete", "markets=1/1", "legs=2", "legs_empty=1", "requests=1",
                     "rows_inserted=3", "rows_present=0", "refused=0", "elapsed="):
            assert part in line, (part, line)
        assert verdict_for(vhb.TASK_LABEL, summary).verdict == COMPLETE

    async def test_an_empty_cohort_is_never_green(self):
        summary = await _run(FakeStore(), FakeService())
        v = verdict_for(vhb.TASK_LABEL, summary)
        assert v.verdict == UNKNOWN and v.authoritative and v.blocks_success

    async def test_unrequested_tickers_are_never_filed_under_a_leg(self):
        m = market()
        lg = leg(11)
        service = FakeService({lg.ticker: hourly(m, hours=2)})
        orig = service.get_markets_candlesticks_raw

        async def with_stranger(**kw):
            out = await orig(**kw)
            out["KXOTHER-1"] = hourly(m, hours=2)
            return out

        service.get_markets_candlesticks_raw = with_stranger
        store = FakeStore([m], {1: [lg]})
        summary = await _run(store, service)
        assert summary["unrequested_tickers"] == 1
        assert {p.outcome_id for p in store.rows.values()} == {11}


class TestRunClock:
    async def test_a_pause_that_would_cross_the_deadline_is_refused(self):
        clock = FakeClock()
        rc = RunClock(wall_budget_s=10, rows_per_min=60, clock=clock, sleep=clock.sleep)
        assert await rc.after_rows(5) is True      # due at 5 s
        assert clock.t == pytest.approx(5.0)
        assert await rc.after_rows(10) is False    # due at 15 s > 10 s deadline
        assert clock.t == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


class TestWiring:
    def test_the_beat_runs_it_every_15_minutes_on_heavy(self):
        from app.tasks import HEAVY_TASKS, celery_app

        entry = celery_app.conf.beat_schedule["backfill-venue-history-gaps"]
        assert entry["task"] == vhb.TASK_NAME
        assert sorted(entry["schedule"].minute) == [1, 16, 31, 46]
        assert entry["options"]["queue"] == "heavy"
        assert entry["options"]["expires"] == 900
        assert vhb.TASK_NAME in HEAVY_TASKS
        assert celery_app.conf.task_routes[vhb.TASK_NAME] == {"queue": "heavy"}

    def test_a_run_cannot_lap_the_next(self):
        from app.tasks import celery_app

        task = celery_app.tasks[vhb.TASK_NAME]
        assert vhb.WALL_BUDGET_BOUNDS[1] + 30 < task.soft_time_limit < task.time_limit
        assert vhb.LEASE_TTL_S >= task.time_limit
        assert (task.soft_time_limit, task.time_limit) == (vhb.SOFT_TIME_LIMIT_S, vhb.TIME_LIMIT_S)

    def test_the_four_settings_are_documented(self):
        doc = (BACKEND.parent / "docs" / "live-settings.md").read_text()
        for var in (vhb.ENABLED_ENV, vhb.ROWS_PER_MIN_ENV, vhb.MARKETS_PER_RUN_ENV, vhb.WALL_BUDGET_ENV):
            assert f"| `{var}` |" in doc, var

    def test_nothing_reads_the_new_tables_yet(self):
        """PR-B serves them. Until then the only code naming them is the model, the writer
        and the Celery task's docstring."""
        hits = []
        for path in (BACKEND / "app").rglob("*.py"):
            text = path.read_text()
            if "venue_history_points" in text or "VenueHistoryPoint" in text:
                hits.append(path.relative_to(BACKEND).as_posix())
        assert sorted(hits) == [
            "app/models/models.py", "app/tasks/__init__.py", "app/tasks/venue_history_backfill.py",
        ]


# ---------------------------------------------------------------------------
# Migration ↔ model parity (offline)
# ---------------------------------------------------------------------------


def _load_migration():
    spec = importlib.util.spec_from_file_location("venue_history_points_11929", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _RecordingOp:
    def __init__(self):
        self.md = MetaData()
        Table("futures_outcomes", self.md, Column("id", Integer, primary_key=True))
        self.tables: dict = {}
        self.dropped: list = []

    def create_table(self, name, *items, **kw):
        self.tables[name] = Table(name, self.md, *items, **kw)

    def drop_table(self, name):
        self.dropped.append(name)


def _shape(table):
    pg = postgresql.dialect()

    def default(col):
        if col.server_default is None:
            return None
        return str(col.server_default.arg.compile(dialect=pg)) if hasattr(
            col.server_default.arg, "compile") else str(col.server_default.arg)

    from sqlalchemy import CheckConstraint, UniqueConstraint

    return {
        "columns": [
            (c.name, c.type.compile(dialect=pg), bool(c.nullable), default(c)) for c in table.columns
        ],
        "pk": sorted(c.name for c in table.primary_key.columns),
        "unique": sorted(
            (u.name, tuple(c.name for c in u.columns))
            for u in table.constraints if isinstance(u, UniqueConstraint)
        ),
        "checks": sorted(
            (c.name, " ".join(str(c.sqltext).split()))
            for c in table.constraints if isinstance(c, CheckConstraint)
        ),
        "fks": sorted(
            (fk.parent.name, fk.target_fullname, fk.ondelete) for fk in table.foreign_keys
        ),
        "indexes": sorted((i.name, tuple(c.name for c in i.columns), i.unique) for i in table.indexes),
    }


class TestMigration:
    def test_revision_id_and_parent(self):
        mod = _load_migration()
        assert mod.revision == "venue_history_points_11929" and len(mod.revision) <= 32
        assert mod.down_revision == "events_fts_gin_fastupdate_off"

    def test_it_is_the_single_head(self):
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cwd = os.getcwd()
        os.chdir(BACKEND)
        try:
            script = ScriptDirectory.from_config(Config("alembic.ini"))
            heads = list(script.get_heads())
            # One head with this migration on its chain — never `== [ours]`,
            # which fails the next migration to land (it failed #12020 itself
            # on the events_fts test).
            chain = [rev.revision for rev in script.iterate_revisions(heads[0], "base")]
        finally:
            os.chdir(cwd)
        assert len(heads) == 1, heads
        assert "venue_history_points_11929" in chain

    def test_the_migration_builds_exactly_the_models_tables(self):
        mod = _load_migration()
        rec = _RecordingOp()
        mod.op = rec
        mod.upgrade()
        assert set(rec.tables) == {"venue_history_points", "venue_history_backfill_progress"}
        assert _shape(rec.tables["venue_history_points"]) == _shape(VenueHistoryPoint.__table__)
        assert _shape(rec.tables["venue_history_backfill_progress"]) == _shape(
            VenueHistoryBackfillProgress.__table__
        )
        mod.downgrade()
        assert rec.dropped == ["venue_history_backfill_progress", "venue_history_points"]

    def test_no_concurrent_index_and_no_data_write(self):
        src = MIGRATION.read_text().split('"""', 2)[2]
        for word in ("CONCURRENTLY", "op.execute", "bulk_insert", "UPDATE ", "INSERT "):
            assert word not in src, word


# ---------------------------------------------------------------------------
# Real PostgreSQL (skips without SEARCH_TEST_DATABASE_URL; a skip is not a pass)
# ---------------------------------------------------------------------------


def _pg_world():
    from tests.pm_bulk_test_support import _ENGINES, pg_engine
    from app.models.models import FuturesOutcome

    engine = pg_engine()  # skips without SEARCH_TEST_DATABASE_URL
    schema = _ENGINES[-1][2]
    markets = Table(
        "futures_markets", MetaData(),
        Column("id", Integer, primary_key=True),
        Column("source", String), Column("external_id", String),
        Column("name", String), Column("status", String),
        Column("settled_at", DateTime(timezone=True)),
        Column("resolution_date", DateTime(timezone=True)),
        Column("created_at", DateTime(timezone=True)),
    )
    markets.create(engine)
    FuturesOutcome.__table__.create(engine)
    return engine, schema, markets


def _async_engine(schema):
    from sqlalchemy.engine import make_url
    from sqlalchemy.ext.asyncio import create_async_engine

    url = make_url(os.environ["SEARCH_TEST_DATABASE_URL"]).set(drivername="postgresql+asyncpg")
    return create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})


def _seed(engine, markets_table):
    from sqlalchemy import insert
    from app.models.models import FuturesOutcome

    real_now = datetime.now(UTC)
    rows = [
        # id, source, status, settled_days_ago, resolution_days_ago
        (1, "kalshi", "resolved", 10, None),
        (2, "kalshi", "resolved", 44, 44.5),
        (3, "kalshi", "resolved", 50, None),     # past the 45-day floor
        (4, "kalshi", "resolved", 90, None),     # past the purge
        (5, "kalshi", "open", None, None),       # open
        (6, "polymarket", "resolved", 5, None),  # not Kalshi
        (7, "kalshi", "resolved", 5, 60),        # venue closed 60 days ago: LEAST excludes
        (8, "kalshi", "resolved", 20, None),     # done
        (9, "kalshi", "resolved", 30, None),     # failed 3 times
        (10, "kalshi", "resolved", 25, None),    # failed twice: still tried
    ]
    with engine.begin() as conn:
        for mid, source, status, sd, rd in rows:
            conn.execute(insert(markets_table).values(
                id=mid, source=source, external_id=f"KXEVT-{mid}", name=f"m{mid}", status=status,
                settled_at=None if sd is None else real_now - timedelta(days=sd),
                resolution_date=None if rd is None else real_now - timedelta(days=rd),
                created_at=real_now - timedelta(days=100),
            ))
            conn.execute(insert(FuturesOutcome.__table__).values(
                id=mid * 10, market_id=mid, external_id=f"KXEVT-{mid}-A", name="A",
                current_probability=0.5,
            ))
        conn.execute(insert(VenueHistoryBackfillProgress.__table__).values(
            venue="kalshi", market_id=8, status="done", legs_done=[80], attempts=0))
        conn.execute(insert(VenueHistoryBackfillProgress.__table__).values(
            venue="kalshi", market_id=9, status="failed", legs_done=[], attempts=3))
        conn.execute(insert(VenueHistoryBackfillProgress.__table__).values(
            venue="kalshi", market_id=10, status="failed", legs_done=[], attempts=2))
    return real_now


class TestRealPostgres:
    async def test_the_cohort_sql_store_and_idempotent_insert(self):
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession

        engine, schema, markets = _pg_world()
        VenueHistoryPoint.__table__.create(engine)
        VenueHistoryBackfillProgress.__table__.create(engine)
        real_now = _seed(engine, markets)
        aengine = _async_engine(schema)
        try:
            async with AsyncSession(aengine) as session:
                store = vhb.PgStore(session)
                floor, ceiling = cohort_window(real_now)
                cohort = await store.select_cohort(floor=floor, ceiling=ceiling, limit=50, max_attempts=3)
                assert [m.market_id for m in cohort] == [2, 10, 1]  # oldest settlement first
                assert cohort[1].attempts == 2
                limited = await store.select_cohort(floor=floor, ceiling=ceiling, limit=1, max_attempts=3)
                assert [m.market_id for m in limited] == [2]
                # #2's settlement is LEAST(settled_at, resolution_date): the earlier one.
                assert abs((cohort[0].settle_ts - (real_now - timedelta(days=44.5))).total_seconds()) < 5

                legs = await store.load_legs([1, 2])
                assert {k: [lg.outcome_id for lg in v] for k, v in legs.items()} == {1: [10], 2: [20]}

                m = cohort[2]
                pts = [
                    vhb.VenuePoint(10, 1, m.settle_ts - timedelta(hours=h), 0.4 + h / 100, 0.39, 0.41, "mid")
                    for h in range(1, 4)
                ]
                assert await store.insert_points(pts) == 3
                assert await store.insert_points(pts) == 0  # rerun: ON CONFLICT DO NOTHING

                await store.record_progress(1, status="in_progress", legs_done=[10], attempts_inc=0,
                                            points_inserted=3, last_error=None)
                await store.record_progress(1, status="failed", legs_done=[10], attempts_inc=1,
                                            points_inserted=0, last_error="http_500")
                await store.record_progress(1, status="done", legs_done=[10], attempts_inc=0,
                                            points_inserted=2, last_error=None)
                after = await store.select_cohort(floor=floor, ceiling=ceiling, limit=50, max_attempts=3)
                assert [x.market_id for x in after] == [2, 10]
        finally:
            await aengine.dispose()

        with engine.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM venue_history_points")).scalar_one() == 3
            row = conn.execute(text(
                "SELECT status, legs_done, attempts, points_inserted, completed_at IS NOT NULL "
                "FROM venue_history_backfill_progress WHERE market_id = 1"
            )).one()
            assert tuple(row) == ("done", [10], 1, 5, True)
            basis, resolution, venue = conn.execute(text(
                "SELECT DISTINCT price_basis, resolution_s, venue FROM venue_history_points"
            )).one()
            assert (basis, resolution, venue) == ("mid", 3600, "kalshi")

    async def test_the_check_refuses_a_terminal_probability(self):
        from sqlalchemy import insert
        from sqlalchemy.exc import IntegrityError

        engine, _schema, markets = _pg_world()
        VenueHistoryPoint.__table__.create(engine)
        VenueHistoryBackfillProgress.__table__.create(engine)
        _seed(engine, markets)
        with pytest.raises(IntegrityError):
            with engine.begin() as conn:
                conn.execute(insert(VenueHistoryPoint.__table__).values(
                    outcome_id=10, market_id=1, venue="kalshi", observed_at=NOW,
                    probability=1.0, price_basis="mid", resolution_s=3600,
                ))

    def test_the_migration_builds_the_models_schema_on_postgres(self):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        from sqlalchemy import inspect as sa_inspect
        from sqlalchemy import text

        engine, schema, _markets = _pg_world()
        tables = ("venue_history_points", "venue_history_backfill_progress")

        def shape(conn):
            insp = sa_inspect(conn)
            out = {}
            for t in tables:
                out[t] = {
                    "columns": sorted((c["name"], str(c["type"]), c["nullable"],
                                       str(c.get("default"))) for c in insp.get_columns(t, schema=schema)),
                    "pk": sorted(insp.get_pk_constraint(t, schema=schema)["constrained_columns"]),
                    "unique": sorted((u["name"], tuple(u["column_names"]))
                                     for u in insp.get_unique_constraints(t, schema=schema)),
                    "checks": sorted((c["name"], " ".join(c["sqltext"].split()))
                                     for c in insp.get_check_constraints(t, schema=schema)),
                    "indexes": sorted((i["name"], tuple(i["column_names"]), bool(i["unique"]))
                                      for i in insp.get_indexes(t, schema=schema)),
                    "fks": sorted((tuple(f["constrained_columns"]), f["referred_table"],
                                   (f.get("options") or {}).get("ondelete"))
                                  for f in insp.get_foreign_keys(t, schema=schema)),
                }
            return out

        mod = _load_migration()
        with engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                mod.upgrade()
        with engine.connect() as conn:
            from_migration = shape(conn)
        with engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                mod.downgrade()
            gone = conn.execute(text(
                "SELECT to_regclass('venue_history_points') IS NULL "
                "AND to_regclass('venue_history_backfill_progress') IS NULL"
            )).scalar_one()
        assert gone is True
        VenueHistoryPoint.__table__.create(engine)
        VenueHistoryBackfillProgress.__table__.create(engine)
        with engine.connect() as conn:
            from_models = shape(conn)
        assert from_migration == from_models
        assert from_models["venue_history_points"]["fks"] == [(("outcome_id",), "futures_outcomes", "CASCADE")]

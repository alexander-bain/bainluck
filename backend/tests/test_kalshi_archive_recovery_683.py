"""#683 archive arm — routing, admission, bounds and idempotency of the DRY-RUN plan.

PILLAR: TRUTH. SHIP: settled Kalshi questions with no price history get back
their real pre-resolution probability timeline, and archive provenance stays
separate from live capture.

Specimens are shaped like the 2026-10-15 receipt
(``artifacts/calibration-683-archive-20261015/coverage-direct-result.json``):
archive candles carry ``end_period_ts, open_interest, price, volume, yes_ask,
yes_bid`` with BARE dollar-string keys (``close``, not ``close_dollars``). Every
I/O edge is a fake. No provider or database is touched.
"""

from __future__ import annotations

import ast
import inspect
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.services import kalshi_archive_recovery as rec
from app.services.kalshi_api import KalshiAPIService
from app.utils import kalshi_archive_history as kah
from app.utils.kalshi_candle_price import candle_yes_price

UTC = timezone.utc
ARCHIVE_CUTOFF = datetime(2026, 8, 16, tzinfo=UTC)

# KXNCAAMBSPREAD-26APR05OKLAWVU-WVU9: opened 12:57Z, settled 00:03:13Z next day.
OPEN = datetime(2026, 4, 5, 12, 57, tzinfo=UTC)
SETTLED = datetime(2026, 4, 6, 0, 3, 13, tzinfo=UTC)
TIPOFF = datetime(2026, 4, 5, 22, 0, tzinfo=UTC)


def ts(dt: datetime) -> int:
    return int(dt.timestamp())


def candle(
    end: datetime,
    close=None,
    mean=None,
    previous=None,
    bid=None,
    ask=None,
    volume="0.00",
):
    return {
        "end_period_ts": ts(end),
        "open_interest": "10.00",
        "price": {
            "close": close,
            "high": close,
            "low": close,
            "mean": mean,
            "open": close,
            "previous": previous,
        },
        "volume": volume,
        "yes_ask": {"close": ask, "high": ask, "low": ask, "open": ask},
        "yes_bid": {"close": bid, "high": bid, "low": bid, "open": bid},
    }


def event(source="espn", commence=TIPOFF, completed=None):
    return SimpleNamespace(
        commence_time=commence,
        commence_time_source=source,
        created_at=datetime(2026, 3, 1),
        completed_at=completed,
    )


def classify(candles, *, cutoff=TIPOFF, refusal=None, period=60, stored=()):
    return kah.classify_candles(
        outcome_id=7,
        ticker="KXT-1-A",
        candles=candles,
        period_minutes=period,
        settled_at=SETTLED,
        cutoff=cutoff,
        cutoff_refusal=refusal,
        stored_instants=stored,
    )


# ── routing ────────────────────────────────────────────────────────────────


class TestRouting:
    def test_settled_before_provider_cutoff_is_archive(self):
        assert (
            kah.route_market(ARCHIVE_CUTOFF - timedelta(seconds=1), ARCHIVE_CUTOFF)
            == "archive"
        )

    def test_settled_at_or_after_cutoff_is_recent(self):
        assert kah.route_market(ARCHIVE_CUTOFF, ARCHIVE_CUTOFF) == "recent"
        assert (
            kah.route_market(ARCHIVE_CUTOFF + timedelta(days=3), ARCHIVE_CUTOFF)
            == "recent"
        )

    def test_no_settlement_is_unknown(self):
        assert kah.route_market(None, ARCHIVE_CUTOFF) == "unknown"

    def test_cutoff_is_read_from_the_payload_and_fails_closed(self):
        assert (
            kah.archive_settled_cutoff({"market_settled_ts": "2026-08-16T00:00:00Z"})
            == ARCHIVE_CUTOFF
        )
        assert (
            kah.archive_settled_cutoff({"trades_created_ts": "2026-08-16T00:00:00Z"})
            is None
        )
        assert kah.archive_settled_cutoff(None) is None

    def test_no_retention_constant_is_used_for_routing(self):
        src = inspect.getsource(kah) + inspect.getsource(rec)
        assert "PROVABLY_PURGED_AGE_DAYS" not in src
        assert "kalshi_retention" not in src.replace("``kalshi_retention``", "")


class TestIdentity:
    ROW = {
        "ticker": "KXA-26APR05X-Y",
        "event_ticker": "KXA-26APR05X",
        "status": "finalized",
        "settlement_ts": "2026-04-06T00:03:13Z",
    }

    def test_exact_match_passes(self):
        assert kah.identity_refusal("KXA-26APR05X-Y", "KXA-26APR05X", self.ROW) is None

    @pytest.mark.parametrize(
        "ticker,event_t,patch,why",
        [
            ("KXA-26APR05X-Z", "KXA-26APR05X", {}, "ticker_mismatch"),
            ("KXA-26APR05X-Y", "KXA-26APR05Q", {}, "event_ticker_mismatch"),
            ("KXA-26APR05X-Y", None, {}, "event_ticker_mismatch"),
            (
                "KXA-26APR05X-Y",
                "KXA-26APR05X",
                {"status": "active"},
                "not_settled_at_venue",
            ),
            (
                "KXA-26APR05X-Y",
                "KXA-26APR05X",
                {"settlement_ts": None},
                "settlement_ts_missing",
            ),
        ],
    )
    def test_any_near_miss_refuses(self, ticker, event_t, patch, why):
        assert kah.identity_refusal(ticker, event_t, {**self.ROW, **patch}) == why


# ── prices ─────────────────────────────────────────────────────────────────


class TestArchivePrice:
    def test_house_reducer_sees_nothing_in_raw_archive_spelling(self):
        # Why the adapter exists: feeding the archive candle straight in loses it.
        c = candle(TIPOFF, close="0.4200", bid="0.0000", ask="0.9900")
        assert candle_yes_price(c) is None
        assert kah.archive_candle_price(c) == (pytest.approx(0.42), kah.BASIS_TRADED)

    def test_previous_only_is_never_a_price(self):
        c = candle(TIPOFF, previous="0.0100")
        assert kah.archive_candle_price(c) == (None, kah.BASIS_PREVIOUS_ONLY)

    def test_all_null_is_no_price(self):
        assert kah.archive_candle_price(candle(TIPOFF)) == (None, kah.BASIS_NONE)

    def test_tight_quote_without_trade_is_marked_quote_only(self):
        c = candle(TIPOFF, bid="0.4000", ask="0.4400", previous="0.9000")
        price, basis = kah.archive_candle_price(c)
        assert price == pytest.approx(0.42) and basis == kah.BASIS_QUOTE

    def test_settled_shell_book_is_refused(self):
        assert (
            kah.archive_candle_price(candle(TIPOFF, bid="0.0000", ask="1.0000"))[0]
            is None
        )

    def test_dollars_spelling_also_reads(self):
        c = {"end_period_ts": ts(TIPOFF), "price": {"close_dollars": "0.3300"}}
        assert kah.archive_candle_price(c)[0] == pytest.approx(0.33)


# ── period choice: hourly evidence the daily candle misses ─────────────────


class TestResolution:
    def test_eleven_hour_market_gets_hourly_not_daily(self):
        assert kah.choose_period(OPEN, SETTLED) == kah.PERIOD_HOUR

    def test_market_opened_during_play_gets_minutes(self):
        # KXNCAAMBSPREAD-26APR06CONNMICH-MICH20: open 02:31Z, settled 03:28Z.
        assert (
            kah.choose_period(
                datetime(2026, 4, 7, 2, 31, tzinfo=UTC),
                datetime(2026, 4, 7, 3, 28, tzinfo=UTC),
            )
            == kah.PERIOD_MINUTE
        )

    @pytest.mark.parametrize(
        "span",
        [
            timedelta(hours=kah.CANDLES_PER_REQUEST_BOUND + 1),
            timedelta(days=181),
            timedelta(days=4000),
        ],
    )
    def test_a_long_market_keeps_hourly_and_is_never_coarsened_to_daily(self, span):
        # Root's reproduction: a 181-day market selected 1440 (daily) at ed55fc5fb9.
        assert kah.choose_period(SETTLED - span, SETTLED) == kah.PERIOD_HOUR

    def test_unknown_opening_is_hourly_not_short_and_not_daily(self):
        assert kah.choose_period(None, SETTLED) == kah.PERIOD_HOUR

    def test_the_daily_candle_ends_after_settlement_and_is_refused_hourly_is_kept(self):
        daily = candle(datetime(2026, 4, 6, 4, 0, tzinfo=UTC), close="0.5500")
        hourly = candle(datetime(2026, 4, 5, 21, 0, tzinfo=UTC), close="0.5500")
        d_points, _ = classify([daily], period=1440)
        h_points, _ = classify([hourly])
        assert d_points[0].admission == kah.REFUSE_POST_SETTLEMENT
        assert h_points[0].admission == kah.ADMIT_FORECAST

    def test_a_long_history_is_chunked_whole_from_opening_to_settlement(self):
        opened = SETTLED - timedelta(hours=10_000)
        windows, gap = kah.request_windows(opened, SETTLED, 60)
        assert gap is None and len(windows) == 3
        assert windows[0].start_ts == ts(opened) and windows[-1].end_ts == ts(SETTLED)
        for a, b in zip(windows, windows[1:]):
            assert a.end_ts == b.start_ts  # contiguous: no clipped span between them
        for w in windows:
            assert w.period_minutes == 60
            assert w.end_ts - w.start_ts <= 60 * 60 * kah.CANDLES_PER_REQUEST_BOUND

    def test_short_history_is_one_window(self):
        windows, gap = kah.request_windows(OPEN, SETTLED, 60)
        assert gap is None
        assert [(w.start_ts, w.end_ts) for w in windows] == [(ts(OPEN), ts(SETTLED))]

    def test_missing_opening_asks_a_bounded_window_and_owes_the_gap_before_it(self):
        # Root's reproduction: a missing open_time silently became the last 30 days.
        windows, gap = kah.request_windows(None, SETTLED, 60)
        lower = ts(SETTLED - kah.MISSING_OPEN_LOOKBACK)
        assert [(w.start_ts, w.end_ts) for w in windows] == [(lower, ts(SETTLED))]
        assert gap == {
            "start_ts": None,
            "end_ts": lower,
            "period_minutes": 60,
            "reason": kah.OWED_OPENING_UNKNOWN,
        }


# ── admission ──────────────────────────────────────────────────────────────


class TestAdmission:
    def test_whole_candle_before_start_is_forecast_boundary_inclusive(self):
        points, counts = classify([candle(TIPOFF, close="0.61")])
        assert points[0].admission == kah.ADMIT_FORECAST and counts["forecast"] == 1
        assert points[0].interval_start == (TIPOFF - timedelta(hours=1)).isoformat()

    def test_candle_crossing_start_is_reader_only(self):
        points, _ = classify([candle(TIPOFF + timedelta(minutes=30), close="0.61")])
        assert points[0].admission == kah.ADMIT_READER_ONLY
        assert points[0].reason == "interval_crosses_forecast_cutoff"

    def test_in_play_candle_is_reader_only(self):
        points, _ = classify([candle(TIPOFF + timedelta(hours=2), close="0.90")])
        assert (points[0].admission, points[0].reason) == (
            kah.ADMIT_READER_ONLY,
            "after_forecast_cutoff",
        )

    def test_candle_crossing_settlement_is_refused(self):
        points, _ = classify([candle(SETTLED + timedelta(minutes=57), close="0.99")])
        assert (points[0].admission, points[0].reason) == (
            kah.REFUSE_POST_SETTLEMENT,
            "interval_crosses_settlement",
        )

    def test_candle_ending_exactly_at_settlement_is_refused(self):
        points, _ = classify([candle(SETTLED, close="0.99")])
        assert points[0].admission == kah.REFUSE_POST_SETTLEMENT

    def test_unknown_cutoff_is_never_forecast(self):
        points, _ = classify(
            [candle(TIPOFF - timedelta(hours=5), close="0.40")],
            cutoff=None,
            refusal="unanchored_boundary",
        )
        assert points[0].admission == kah.ADMIT_READER_ONLY
        assert points[0].reason == "forecast_cutoff_unknown:unanchored_boundary"

    def test_null_and_previous_only_are_counted_not_planned_as_prices(self):
        points, counts = classify(
            [
                candle(TIPOFF - timedelta(hours=3), previous="0.01"),
                candle(TIPOFF - timedelta(hours=2)),
            ]
        )
        assert [p.admission for p in points] == [kah.REFUSE_NO_PRICE] * 2
        assert all(p.probability is None for p in points)
        assert counts["previous_only"] == 1 and kah.importable(points) == []

    def test_malformed_and_duplicate_intervals(self):
        good = candle(TIPOFF, close="0.5")
        points, counts = classify(
            [good, dict(good), {"end_period_ts": None}, "junk", {"end_period_ts": True}]
        )
        assert (
            len(points) == 1
            and counts["duplicate_interval"] == 1
            and counts["malformed"] == 3
        )

    def test_every_point_carries_archive_provenance(self):
        points, _ = classify([candle(TIPOFF, close="0.5")])
        assert points[0].source == kah.ARCHIVE_SOURCE != "kalshi"
        assert points[0].period_minutes == 60


class TestForecastCutoff:
    def test_reported_start_bounds_at_min_start_settlement(self):
        assert kah.forecast_cutoff(event(), SETTLED) == (TIPOFF, None)

    @pytest.mark.parametrize("source", ["kalshi", "kalshi_occurrence", "polymarket"])
    def test_venue_stamped_start_fails_closed(self, source):
        # A start minted on a clean minute, well before creation-poll tolerance.
        assert kah.forecast_cutoff(event(source=source), SETTLED) == (
            None,
            kah.CUTOFF_VENUE_STAMP,
        )

    def test_null_provenance_ticker_date_and_unlinked_fail_closed(self):
        assert (
            kah.forecast_cutoff(event(source=None), SETTLED)[1]
            == "start_provenance_unknown"
        )
        assert (
            kah.forecast_cutoff(event(source="kalshi_ticker"), SETTLED)[1]
            == "start_not_reported"
        )
        assert kah.forecast_cutoff(None, SETTLED)[1] == "unanchored_boundary"
        assert kah.forecast_cutoff(event(), None) == (None, kah.CUTOFF_NO_SETTLEMENT)

    def test_contradicted_start_fails_closed(self):
        late = event(commence=SETTLED + timedelta(hours=1))
        assert kah.forecast_cutoff(late, SETTLED)[1] == "settlement_precedes_start"
        merged = event(completed=TIPOFF - timedelta(hours=1))
        assert kah.forecast_cutoff(merged, SETTLED)[1] == "start_contradicted"


# ── idempotency ────────────────────────────────────────────────────────────


class TestIdempotency:
    def test_stored_instant_is_never_importable(self):
        c1 = candle(TIPOFF - timedelta(hours=1), close="0.5")
        c2 = candle(TIPOFF, close="0.6")
        points, counts = classify([c1, c2], stored=[TIPOFF])
        assert counts["already_stored"] == 1
        assert [p.interval_end for p in kah.importable(points)] == [
            (TIPOFF - timedelta(hours=1)).isoformat()
        ]

    def test_digest_is_repeatable_and_order_independent(self):
        cs = [candle(TIPOFF - timedelta(hours=h), close="0.5") for h in range(3)]
        a, _ = classify(cs)
        b, _ = classify(list(reversed(cs)))
        assert kah.plan_digest(a) == kah.plan_digest(b)

    def test_digest_after_import_shrinks_to_nothing(self):
        cs = [candle(TIPOFF - timedelta(hours=h), close="0.5") for h in range(3)]
        first, _ = classify(cs)
        stored = [datetime.fromisoformat(p.interval_end) for p in kah.importable(first)]
        again, _ = classify(cs, stored=stored)
        assert kah.importable(again) == []
        assert kah.plan_digest(again) == kah.plan_digest([])


# ── planner, with fakes at the I/O edges ───────────────────────────────────


def _row(
    oid,
    ticker="KXNCAAMBSPREAD-26APR05OKLAWVU-WVU9",
    evt="KXNCAAMBSPREAD-26APR05OKLAWVU",
    has_event=True,
    source="espn",
    resolution_date=SETTLED,
    status="resolved",
    live_snapshots=0,
):
    return SimpleNamespace(
        outcome_id=oid,
        ticker=ticker,
        event_ticker=evt,
        market_id=500 + oid,
        event_id=900 if has_event else None,
        resolution_source=None,
        resolution_date=resolution_date,
        status=status,
        has_event=has_event,
        commence_time=TIPOFF,
        commence_time_source=source,
        created_at=datetime(2026, 3, 1),
        completed_at=None,
        live_snapshots=live_snapshots,
    )


def _listed(ticker, evt, settled=SETTLED, opened=OPEN):
    return {
        "ticker": ticker,
        "event_ticker": evt,
        "status": "finalized",
        "open_time": None if opened is None else opened.isoformat(),
        "settlement_ts": settled.isoformat(),
    }


class FakeSession:
    def __init__(self, rows, stored=(), store_present=True):
        self.rows, self.stored, self.sql = rows, list(stored), []
        self.store_present = store_present

    async def execute(self, clause, params=None):
        sql = str(clause)
        self.sql.append((sql, params))
        if "SET TRANSACTION READ ONLY" in sql:
            return SimpleNamespace(fetchall=lambda: [])
        if "to_regclass" in sql:
            return SimpleNamespace(scalar=lambda: self.store_present)
        if "FROM futures_outcomes fo" in sql:
            rows = self.rows
            if "ANY(:outcome_ids)" in sql:
                rows = [r for r in rows if r.outcome_id in params["outcome_ids"]]
            else:
                rows = [r for r in rows if r.outcome_id > params["after_id"]]
            # Emulate the local filters only when the SQL really carries them.
            if "NOT EXISTS (" in sql:
                rows = [r for r in rows if not r.live_snapshots]
            if "fm.status = 'resolved'" in sql:
                rows = [r for r in rows if r.status == "resolved"]
            if ":archive_cutoff" in sql:
                cut = params["archive_cutoff"]
                rows = [
                    r
                    for r in rows
                    if r.resolution_date is None or r.resolution_date < cut
                ]
            return SimpleNamespace(fetchall=lambda: rows[: params["lim"]])
        if "FROM kalshi_archive_intervals" in sql:
            return SimpleNamespace(
                fetchall=lambda: [
                    s for s in self.stored if s.outcome_id in params["ids"]
                ]
            )
        raise AssertionError(f"unexpected SQL {sql}")


def _429(retry_after="1"):
    req = httpx.Request("GET", "https://api.elections.kalshi.com/x")
    return httpx.HTTPStatusError(
        "429",
        request=req,
        response=httpx.Response(429, headers={"Retry-After": retry_after}, request=req),
    )


class FakeService:
    def __init__(self, listings, candles, script=None, cutoff="2026-08-16T00:00:00Z"):
        self.listings, self.candles = listings, candles
        self.script = list(script or [])  # exceptions to raise on successive calls
        self.cutoff, self.calls, self.closed = cutoff, [], False

    def _maybe_raise(self):
        if self.script:
            e = self.script.pop(0)
            if e is not None:
                raise e

    async def get_historical_cutoff(self):
        self.calls.append(("cutoff",))
        self._maybe_raise()
        return {"market_settled_ts": self.cutoff}

    async def get_historical_markets(
        self, *, event_ticker=None, limit=100, cursor=None, series_ticker=None
    ):
        self.calls.append(("listing", event_ticker, cursor))
        self._maybe_raise()
        pages = self.listings.get(event_ticker, [([], None)])
        idx = 0 if cursor is None else int(cursor)
        return pages[idx]

    async def get_historical_market_candlesticks_raw(
        self, ticker, *, period_interval, start_ts, end_ts
    ):
        self.calls.append(("candles", ticker, period_interval, start_ts, end_ts))
        self._maybe_raise()
        return self.candles.get(ticker, [])

    async def get_historical_market_candlesticks_payload(
        self, ticker, *, period_interval, start_ts, end_ts
    ):
        batch = await self.get_historical_market_candlesticks_raw(
            ticker, period_interval=period_interval, start_ts=start_ts, end_ts=end_ts
        )
        return payload_of(ticker, batch)

    async def close(self):
        self.closed = True


def payload_of(ticker, candles, echoed=None):
    """A real ``KalshiArchiveCandlePayload`` built from a real response body."""
    import hashlib
    import json as _json

    from app.services.kalshi_api import KalshiArchiveCandlePayload

    body = _json.dumps(
        {"ticker": ticker if echoed is None else echoed, "candlesticks": candles}
    )
    return KalshiArchiveCandlePayload.from_raw(
        requested_ticker=ticker,
        raw_body=body,
        raw_sha256=hashlib.sha256(body.encode()).hexdigest(),
        retrieved_at="2026-10-15T20:00:00+00:00",
    )


class Clock:
    def __init__(self):
        self.t, self.sleeps = 0.0, []

    def monotonic(self):
        return self.t

    async def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


async def _plan(session, service, clock=None, cooldown=0.0, **kw):
    clock = clock or Clock()

    @asynccontextmanager
    async def factory():
        yield session

    return await rec.plan_archive_recovery(
        session_factory=factory,
        service_factory=lambda: service,
        cooldown_reader=lambda: cooldown,
        max_wait_seconds=30.0,
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        pace_seconds=0.5,
        **kw,
    )


T1, E1 = "KXNCAAMBSPREAD-26APR05OKLAWVU-WVU9", "KXNCAAMBSPREAD-26APR05OKLAWVU"
T2 = "KXNCAAMBSPREAD-26APR05OKLAWVU-OKLA3"


def _good_candles():
    return [
        candle(TIPOFF - timedelta(hours=1), close="0.41", volume="12.00"),
        candle(TIPOFF + timedelta(hours=1), close="0.70", volume="40.00"),
        candle(TIPOFF + timedelta(hours=1, minutes=1), previous="0.70"),
        candle(datetime(2026, 4, 6, 1, 0, tzinfo=UTC), close="0.99"),
    ]


class TestPlanner:
    async def test_happy_path_is_read_only_and_exact(self):
        session = FakeSession([_row(1)])
        svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        report = await _plan(session, svc, limit=5)
        assert report["mode"] == "dry_run" and report["writes"] == 0
        assert report["terminal"] == "complete" and report["walk_ended"] is True
        plan = report["plans"][0]
        assert plan["refusal"] is None and plan["period_minutes"] == 60
        assert plan["coverage"] == "complete" and plan["owed_windows"] == []
        assert plan["forecast_cutoff"] == TIPOFF.isoformat()
        adm = [p["admission"] for p in plan["points"]]
        assert adm == ["forecast", "reader_only", "no_price", "post_settlement"]
        assert report["importable_points"] == 2 and report["next_after_id"] == 1
        assert svc.closed
        assert session.sql[0][0] == "SET TRANSACTION READ ONLY"
        assert all(
            w not in s.upper()
            for s, _ in session.sql
            for w in ("INSERT ", "UPDATE ", "DELETE ")
        )
        _, ticker, period, start, end = svc.calls[-1]
        assert (ticker, period, end) == (T1, 60, ts(SETTLED)) and start == ts(OPEN)

    async def test_recent_market_is_left_to_the_live_rails(self):
        session = FakeSession([_row(1)])
        late = ARCHIVE_CUTOFF + timedelta(days=1)
        svc = FakeService(
            {E1: [([_listed(T1, E1, settled=late)], None)]}, {T1: _good_candles()}
        )
        report = await _plan(session, svc)
        assert report["plans"][0]["refusal"] == "route_recent"
        assert not [c for c in svc.calls if c[0] == "candles"]

    async def test_empty_listing_and_empty_cursor_is_a_shape_not_a_purge(self):
        session = FakeSession(
            [
                _row(
                    1,
                    ticker="KXNCAAMB-26APR06CONNMICH-CONN",
                    evt="KXNCAAMB-26APR06CONNMICH",
                )
            ]
        )
        svc = FakeService({}, {})
        report = await _plan(session, svc)
        assert report["plans"][0]["refusal"] == "archive_listing_empty"
        assert report["terminal"] == "complete"
        assert not [c for c in svc.calls if c[0] == "candles"]

    async def test_one_listing_read_serves_siblings_and_absent_ticker_refuses(self):
        session = FakeSession([_row(1), _row(2, ticker=T2), _row(3, ticker=T1 + "X")])
        svc = FakeService(
            {E1: [([_listed(T1, E1)], "1"), ([_listed(T2, E1)], None)]},
            {T1: _good_candles(), T2: []},
        )
        report = await _plan(session, svc)
        assert len([c for c in svc.calls if c[0] == "listing"]) == 2  # two pages, once
        refusals = [p["refusal"] for p in report["plans"]]
        assert refusals == [
            None,
            "archive_candles_empty",
            "absent_from_archive_listing",
        ]

    async def test_unlinked_market_plans_reader_history_but_no_forecast(self):
        session = FakeSession([_row(1, has_event=False)])
        svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        report = await _plan(session, svc)
        plan = report["plans"][0]
        assert plan["cutoff_refusal"] == "unanchored_boundary"
        assert "forecast" not in [p["admission"] for p in plan["points"]]

    async def test_shared_cooldown_sends_nothing(self):
        svc = FakeService({}, {})
        report = await _plan(FakeSession([_row(1)]), svc, cooldown=12.0)
        assert (
            report["terminal"] == "cooldown"
            and svc.calls == []
            and report["requests_sent"] == 0
        )

    async def test_429_is_waited_once_then_succeeds(self):
        session = FakeSession([_row(1)])
        svc = FakeService(
            {E1: [([_listed(T1, E1)], None)]},
            {T1: _good_candles()},
            script=[None, None, _429("2")],
        )
        clock = Clock()
        report = await _plan(session, svc, clock=clock)
        assert report["rate_limit_waits"] == 1 and 2.0 in clock.sleeps
        assert report["terminal"] == "complete" and report["importable_points"] == 2

    async def test_long_cooldown_stops_and_holds_the_cursor_before_the_refused_id(self):
        session = FakeSession([_row(1), _row(2, ticker=T2)])
        listing = {E1: [([_listed(T1, E1), _listed(T2, E1)], None)]}
        candles = {T1: _good_candles(), T2: _good_candles()}
        # cutoff ok, listing ok, T1 candles ok, T2 candles 429 with a 300 s cooldown.
        svc = FakeService(listing, candles, script=[None, None, None, _429("300")])
        report = await _plan(session, svc)
        assert (
            report["terminal"] == "rate_limited"
            and report["stopped_on_cooldown_s"] == 300.0
        )
        assert report["next_after_id"] == 1 and report["planned"] == 1
        assert report["owed_ids"] == []  # not passed, so asked first on resume

    async def test_second_429_after_the_wait_stops(self):
        session = FakeSession([_row(1)])
        svc = FakeService(
            {E1: [([_listed(T1, E1)], None)]},
            {T1: _good_candles()},
            script=[None, None, _429("1"), _429("1")],
        )
        report = await _plan(session, svc)
        assert report["terminal"] == "rate_limited" and report["next_after_id"] == 0

    async def test_non_429_error_is_owed_and_siblings_survive(self):
        session = FakeSession([_row(1), _row(2, ticker=T2)])
        boom = httpx.HTTPStatusError(
            "500",
            request=httpx.Request("GET", "https://x"),
            response=httpx.Response(500, request=httpx.Request("GET", "https://x")),
        )
        svc = FakeService(
            {E1: [([_listed(T1, E1), _listed(T2, E1)], None)]},
            {T1: _good_candles(), T2: _good_candles()},
            script=[None, None, boom],
        )
        report = await _plan(session, svc)
        assert report["owed_ids"] == [1] and report["planned"] == 1
        assert report["terminal"] == "partial" and report["next_after_id"] == 2

    async def test_request_budget_stops_partial_and_resume_finishes_the_rest(self):
        rows = [_row(i, ticker=f"{E1}-T{i}") for i in range(1, 5)]
        listing = {E1: [([_listed(f"{E1}-T{i}", E1) for i in range(1, 5)], None)]}
        candles = {f"{E1}-T{i}": _good_candles() for i in range(1, 5)}
        first = await _plan(
            FakeSession(rows), FakeService(listing, candles), max_requests=4
        )
        assert first["terminal"] == "partial" and first["requests_sent"] == 4
        assert first["next_after_id"] == 2 and first["walk_ended"] is False
        second = await _plan(
            FakeSession(rows),
            FakeService(listing, candles),
            after_id=first["next_after_id"],
            max_requests=10,
        )
        assert [p["outcome_id"] for p in second["plans"]] == [3, 4]
        assert second["terminal"] == "complete"

    async def test_exact_ids_mode_reports_ids_that_are_not_candidates(self):
        session = FakeSession([_row(1)])
        svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        report = await _plan(session, svc, outcome_ids=[1, 99])
        assert report["selection"] == "exact_ids" and report["ids_not_candidates"] == [
            99
        ]
        assert report["next_after_id"] is None

    async def test_stored_archive_rows_make_a_rerun_plan_nothing_new(self):
        # Successor (#683 store): "already stored" means already in the ARCHIVE
        # store at the same period and interval end.
        stored = [
            SimpleNamespace(
                outcome_id=1, period_minutes=60, interval_end=TIPOFF - timedelta(hours=1)
            ),
            SimpleNamespace(
                outcome_id=1, period_minutes=60, interval_end=TIPOFF + timedelta(hours=1)
            ),
        ]
        svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        report = await _plan(FakeSession([_row(1)], stored=stored), svc)
        assert report["archive_store"] == "present"
        assert report["importable_points"] == 0
        assert report["plan_digest"] == kah.plan_digest([])

    async def test_an_archive_row_at_another_period_does_not_hide_this_one(self):
        stored = [
            SimpleNamespace(
                outcome_id=1, period_minutes=1, interval_end=TIPOFF - timedelta(hours=1)
            )
        ]
        svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        report = await _plan(FakeSession([_row(1)], stored=stored), svc)
        assert report["importable_points"] == 2

    async def test_before_the_migration_the_planner_still_runs_and_says_so(self):
        svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        session = FakeSession([_row(1)], store_present=False)
        report = await _plan(session, svc)
        assert report["archive_store"] == "absent"
        assert report["importable_points"] == 2
        assert not any("kalshi_archive_intervals\n" in sql and "SELECT outcome_id" in sql
                       for sql, _ in session.sql)

    async def test_unreadable_cutoff_fails_closed_before_any_db_read(self):
        session = FakeSession([_row(1)])
        svc = FakeService({}, {}, cutoff=None)
        report = await _plan(session, svc)
        assert report["terminal"] == "failed" and session.sql == []

    async def test_caps_are_clamped(self):
        svc = FakeService({}, {})
        report = await _plan(FakeSession([]), svc, limit=10_000, max_requests=10_000)
        assert (
            report["limit"] == rec.MAX_OUTCOMES
            and report["max_requests"] == rec.MAX_REQUESTS
        )


# ── Root source review of ed55fc5fb9: the four repairs + the deadline ──────


def _listing_calls(svc):
    return [c for c in svc.calls if c[0] == "listing"]


def _candle_calls(svc):
    return [c for c in svc.calls if c[0] == "candles"]


class TestListingIsNeverTruncatedIntoAbsence:
    async def test_ticker_after_the_third_page_is_found(self):
        filler = [
            ([_listed(f"{E1}-F{p}", E1)], str(p + 1)) for p in range(4)
        ]  # four pages of siblings, then ours on the fifth
        svc = FakeService(
            {E1: filler + [([_listed(T1, E1)], None)]}, {T1: _good_candles()}
        )
        report = await _plan(FakeSession([_row(1)]), svc)
        plan = report["plans"][0]
        assert plan["refusal"] is None and plan["coverage"] == "complete"
        assert len(_listing_calls(svc)) == 5
        assert report["terminal"] == "complete"

    async def test_empty_pages_carrying_a_cursor_are_not_the_end(self):
        pages = [([], "1"), ([], "2"), ([], "3"), ([_listed(T1, E1)], None)]
        svc = FakeService({E1: pages}, {T1: _good_candles()})
        report = await _plan(FakeSession([_row(1)]), svc)
        assert report["plans"][0]["refusal"] is None
        assert len(_listing_calls(svc)) == 4

    async def test_budget_spent_mid_listing_holds_the_outcome_with_its_cursor(self):
        # Root's reproduction: three empty pages each with a next cursor became None.
        pages = [([], str(i + 1)) for i in range(10)] + [([_listed(T1, E1)], None)]
        svc = FakeService({E1: pages}, {T1: _good_candles()})
        report = await _plan(
            FakeSession([_row(1), _row(2, ticker=T2)]), svc, max_requests=4
        )
        assert report["terminal"] == "partial"
        assert report["plans"] == [] and report["owed_ids"] == []
        assert report["next_after_id"] == 0  # NOT advanced past the unproven ticker
        held = report["held_outcome"]
        assert held["outcome_id"] == 1 and held["stage"] == "listing"
        assert held["listing_pages_read"] == 3 and held["listing_cursor"] == "3"
        assert held["listing_exhausted"] is False
        assert "refusal:archive_listing_empty" not in report["totals"]
        assert "refusal:absent_from_archive_listing" not in report["totals"]

    async def test_absence_needs_an_exhausted_listing(self):
        pages = [([_listed(T2, E1)], "1"), ([], None)]
        svc = FakeService({E1: pages}, {T2: []})
        report = await _plan(FakeSession([_row(1)]), svc)
        assert report["plans"][0]["refusal"] == "absent_from_archive_listing"
        assert len(_listing_calls(svc)) == 2

    async def test_a_repeated_cursor_is_owed_and_siblings_are_not_re_asked(self):
        loop = [([_listed(f"{E1}-F", E1)], "1"), ([], "1")]
        svc = FakeService({E1: loop}, {})
        report = await _plan(FakeSession([_row(1), _row(2, ticker=T2)]), svc)
        assert report["owed_ids"] == [1, 2] and report["plans"] == []
        assert any("cursor_repeated" in e for e in report["errors"])
        assert len(_listing_calls(svc)) == 2
        assert report["terminal"] == "partial"


class TestFullHistoryIsChunkedNotSampled:
    LONG_OPEN = SETTLED - timedelta(hours=10_000)

    def _svc(self):
        return FakeService(
            {E1: [([_listed(T1, E1, opened=self.LONG_OPEN)], None)]},
            {T1: _good_candles()},
        )

    async def test_more_than_4000_hours_reads_every_hourly_window(self):
        svc = self._svc()
        report = await _plan(FakeSession([_row(1)]), svc)
        plan = report["plans"][0]
        calls = _candle_calls(svc)
        assert [c[2] for c in calls] == [60, 60, 60]  # never 1440
        assert calls[0][3] == ts(self.LONG_OPEN) and calls[-1][4] == ts(SETTLED)
        assert plan["windows_requested"] == plan["windows_read"] == 3
        assert plan["coverage"] == "complete" and report["terminal"] == "complete"
        # Overlapping boundary candles are one interval, not three.
        assert plan["counts"]["duplicate_interval"] == 2 * len(_good_candles())

    async def test_a_stop_between_windows_owes_the_rest_at_the_same_width(self):
        svc = self._svc()
        # cutoff, listing, first window, then the budget is gone.
        report = await _plan(FakeSession([_row(1)]), svc, max_requests=3)
        assert report["terminal"] == "partial" and report["plans"] == []
        assert report["next_after_id"] == 0
        held = report["held_outcome"]
        assert held["stage"] == "candles" and held["windows_read"] == 1
        owed = held["owed_windows"]
        assert len(owed) == 2 and {w["period_minutes"] for w in owed} == {60}
        assert owed[-1]["end_ts"] == ts(SETTLED)
        # The rerun asks the same hourly windows and completes.
        again = await _plan(FakeSession([_row(1)]), self._svc(), max_requests=10)
        assert again["plans"][0]["coverage"] == "complete"
        assert again["plans"][0]["period_minutes"] == 60

    async def test_missing_opening_is_incomplete_with_the_gap_owed(self):
        svc = FakeService(
            {E1: [([_listed(T1, E1, opened=None)], None)]}, {T1: _good_candles()}
        )
        report = await _plan(FakeSession([_row(1)]), svc)
        plan = report["plans"][0]
        assert plan["coverage"] == "incomplete"
        assert [w["reason"] for w in plan["owed_windows"]] == ["opening_unknown"]
        assert report["incomplete_ids"] == [1] and report["terminal"] == "partial"

    async def test_a_history_no_run_could_read_is_owed_by_name(self, monkeypatch):
        monkeypatch.setattr(rec, "MAX_REQUESTS", 2)
        svc = self._svc()
        report = await _plan(FakeSession([_row(1)]), svc, max_requests=2)
        plan = report["plans"][0]
        assert plan["refusal"] == "history_exceeds_request_cap"
        assert plan["coverage"] == "incomplete" and len(plan["owed_windows"]) == 3
        assert report["owed_ids"] == [1] and _candle_calls(svc) == []

    async def test_malformed_candle_rows_leave_the_window_owed(self):
        bad = _good_candles() + [{"end_period_ts": "soon"}]
        svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: bad})
        report = await _plan(FakeSession([_row(1)]), svc)
        plan = report["plans"][0]
        assert plan["coverage"] == "incomplete"
        assert [w["reason"] for w in plan["owed_windows"]] == ["malformed_candles"]
        assert plan["counts"]["malformed"] == 1 and report["terminal"] == "partial"


class TestExactIdsIgnoreTheLocalBackstop:
    # Stored backstop in the FUTURE, market still 'open' locally (gotcha #33),
    # but the venue settled it before the archive cutoff.
    def _session(self):
        return FakeSession(
            [
                _row(
                    1,
                    resolution_date=ARCHIVE_CUTOFF + timedelta(days=60),
                    status="open",
                )
            ]
        )

    def _svc(self):
        return FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})

    async def test_exact_id_is_read_and_the_venue_chooses_the_tier(self):
        session = self._session()
        report = await _plan(session, self._svc(), outcome_ids=[1])
        assert report["ids_not_candidates"] == []
        plan = report["plans"][0]
        assert plan["route"] == "archive" and plan["refusal"] is None
        assert "forecast" in [p["admission"] for p in plan["points"]]
        sql, params = next(x for x in session.sql if "futures_outcomes" in x[0])
        assert "resolution_date" not in sql.split("FROM futures_outcomes")[1]
        assert "archive_cutoff" not in params

    async def test_keyset_discovery_stays_bounded_and_says_what_it_misses(self):
        report = await _plan(self._session(), self._svc())
        assert report["candidates"] == 0
        assert any("backstop" in line for line in report["selector_limits"])

    async def test_exact_ids_still_refuse_a_recent_venue_settlement(self):
        late = ARCHIVE_CUTOFF + timedelta(days=1)
        svc = FakeService({E1: [([_listed(T1, E1, settled=late)], None)]}, {})
        report = await _plan(self._session(), svc, outcome_ids=[1])
        assert report["plans"][0]["refusal"] == "route_recent"


class TestMalformedIsNotEmpty:
    async def test_malformed_listing_is_owed_never_listing_empty(self):
        from app.services.kalshi_api import KalshiArchiveResponseMalformed

        svc = FakeService(
            {},
            {},
            script=[
                None,
                KalshiArchiveResponseMalformed("historical_markets", "markets_missing"),
            ],
        )
        report = await _plan(FakeSession([_row(1), _row(2, ticker=T2)]), svc)
        assert report["owed_ids"] == [1, 2] and report["plans"] == []
        assert all(
            "malformed_response:historical_markets" in e for e in report["errors"]
        )
        assert len(_listing_calls(svc)) == 1  # the sibling is not re-asked
        assert report["terminal"] == "partial"

    async def test_malformed_candles_are_owed_never_candles_empty(self):
        from app.services.kalshi_api import KalshiArchiveResponseMalformed

        svc = FakeService(
            {E1: [([_listed(T1, E1)], None)]},
            {},
            script=[
                None,
                None,
                KalshiArchiveResponseMalformed(
                    "historical_candlesticks", "candlesticks_missing"
                ),
            ],
        )
        report = await _plan(FakeSession([_row(1)]), svc)
        assert report["owed_ids"] == [1] and report["plans"] == []
        assert "refusal:archive_candles_empty" not in report["totals"]

    async def test_malformed_errors_are_not_read_as_429(self):
        from app.services.kalshi_api import KalshiArchiveResponseMalformed
        from app.tasks.kalshi import _kalshi_trade_429_wait

        exc = KalshiArchiveResponseMalformed("historical_markets", "market_row")
        assert _kalshi_trade_429_wait(exc) is None


class TestDeadlineAfterPacing:
    async def test_no_get_leaves_after_the_deadline_once_the_pace_has_slept(self):
        svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        clock = Clock()
        # cutoff at t=0, listing after the pace at t=0.5; the next pace lands at
        # t=1.0, past the 0.7 s deadline, so the candle GET must not be sent.
        report = await _plan(
            FakeSession([_row(1)]), svc, clock=clock, deadline_seconds=0.7
        )
        assert _candle_calls(svc) == [] and report["requests_sent"] == 2
        assert report["terminal"] == "partial" and report["next_after_id"] == 0

    async def test_no_get_leaves_after_the_deadline_once_a_429_wait_has_slept(self):
        svc = FakeService(
            {E1: [([_listed(T1, E1)], None)]},
            {T1: _good_candles()},
            script=[None, _429("1")],
        )
        clock = Clock()
        report = await _plan(
            FakeSession([_row(1)]), svc, clock=clock, deadline_seconds=1.8
        )
        assert report["rate_limit_waits"] == 1
        assert len(_listing_calls(svc)) == 1 and report["requests_sent"] == 2
        assert clock.t <= 2.0 and report["terminal"] == "partial"


class TestCert4130NamedControls:
    """The controls CERT-4130 named for its repairs, under the names it gave them."""

    # 683-ARCHIVE-DEADLINE-ENFORCEMENT
    async def test_no_request_is_started_after_deadline_during_pacing(self):
        # CERT-4130's control: deadline 0.25 s, pace 0.5 s. At ed55fc5fb9 the
        # listing GET started at t=0.5.
        svc = FakeService({E1: [([_listed(T1, E1)], None)]}, {T1: _good_candles()})
        clock = Clock()
        report = await _plan(
            FakeSession([_row(1)]), svc, clock=clock, deadline_seconds=0.25
        )
        assert svc.calls == [("cutoff",)] and report["requests_sent"] == 1
        assert report["terminal"] == "partial" and report["next_after_id"] == 0
        assert report["held_outcome"]["outcome_id"] == 1

    async def test_an_awaited_call_is_bounded_by_the_remaining_deadline(self):
        import asyncio
        import time

        class Hanging(FakeService):
            async def get_historical_markets(self, **kw):
                self.calls.append(("listing", kw.get("event_ticker"), kw.get("cursor")))
                await asyncio.sleep(30)  # a GET that never answers in time
                raise AssertionError("not cancelled")

        svc = Hanging({}, {})

        @asynccontextmanager
        async def factory():
            yield FakeSession([_row(1)])

        started = time.monotonic()
        report = await rec.plan_archive_recovery(
            session_factory=factory,
            service_factory=lambda: svc,
            cooldown_reader=lambda: 0.0,
            max_wait_seconds=30.0,
            pace_seconds=0.5,
            deadline_seconds=0.8,  # real clock: cutoff t=0, listing after the pace
        )
        assert time.monotonic() - started < 3.0
        assert report["terminal"] == "partial" and report["plans"] == []
        assert report["held_outcome"]["stage"] == "listing"
        assert report["owed_ids"] == [] and report["next_after_id"] == 0

    async def test_a_timeout_raised_by_the_call_itself_is_an_owed_error(self):
        svc = FakeService(
            {E1: [([_listed(T1, E1)], None)]},
            {T1: _good_candles()},
            script=[None, TimeoutError("provider read timeout")],
        )
        report = await _plan(FakeSession([_row(1)]), svc)
        assert report["owed_ids"] == [1] and report["held_outcome"] is None

    # 683-ARCHIVE-LISTING-EXHAUSTION-IS-PARTIAL
    async def test_truncated_listing_is_not_terminal_market_absence(self):
        # CERT-4130's control: T1 on page four after three unrelated rows, each
        # with a next cursor. At ed55fc5fb9: absent, complete, cursor 0 -> 1.
        pages = [([_listed(f"{E1}-U{i}", E1)], str(i + 1)) for i in range(3)]
        pages.append(([_listed(T1, E1)], None))
        found = await _plan(
            FakeSession([_row(1)]),
            FakeService({E1: pages}, {T1: _good_candles()}),
        )
        assert found["plans"][0]["refusal"] is None
        # And when the budget ends before page four, T1 is held, not absent.
        held = await _plan(
            FakeSession([_row(1)]),
            FakeService({E1: pages}, {T1: _good_candles()}),
            max_requests=4,
        )
        assert held["terminal"] == "partial" and held["plans"] == []
        assert held["next_after_id"] == 0 and held.get("walk_ended") is False
        assert held["held_outcome"]["listing_cursor"] == "3"

    async def test_terminal_listing_establishes_absence(self):
        pages = [([_listed(f"{E1}-U{i}", E1)], str(i + 1)) for i in range(3)]
        pages.append(([_listed(T2, E1)], None))
        report = await _plan(FakeSession([_row(1)]), FakeService({E1: pages}, {}))
        assert report["plans"][0]["refusal"] == "absent_from_archive_listing"
        assert report["terminal"] == "complete" and report["next_after_id"] == 1

    # 683-ARCHIVE-RETRY-WAIT-CLAMP (named non-blocking follow-up, paid here)
    async def test_caller_cannot_raise_thirty_second_429_wait_ceiling(self):
        @asynccontextmanager
        async def factory():
            yield FakeSession([_row(1)])

        svc = FakeService(
            {E1: [([_listed(T1, E1)], None)]},
            {T1: _good_candles()},
            script=[None, _429("60")],
        )
        clock = Clock()
        report = await rec.plan_archive_recovery(
            session_factory=factory,
            service_factory=lambda: svc,
            cooldown_reader=lambda: 0.0,
            max_wait_seconds=120.0,
            deadline_seconds=200.0,
            pace_seconds=0.5,
            sleep=clock.sleep,
            monotonic=clock.monotonic,
        )
        assert 60.0 not in clock.sleeps and report["rate_limit_waits"] == 0
        assert report["terminal"] == "rate_limited"
        assert report["stopped_on_cooldown_s"] == 60.0


# ── static guards ──────────────────────────────────────────────────────────


class TestStatic:
    def test_planner_module_contains_no_write_sql(self):
        src = inspect.getsource(rec).upper()
        for verb in (
            "INSERT INTO",
            "UPDATE FUTURES",
            "DELETE FROM",
            "SETEX(",
            ".SET(",
            ".DELETE(",
        ):
            assert verb not in src, verb

    def test_the_selector_uses_a_bound_like_pattern(self):
        assert "LIKE :ticker_like" in rec.CANDIDATE_SQL and rec.TICKER_LIKE == "KX%-%-%"

    def test_nothing_schedules_or_calls_the_planner_from_app_code(self):
        app = Path(__file__).resolve().parents[1] / "app"
        hits = [
            p
            for p in app.rglob("*.py")
            if "plan_archive_recovery" in p.read_text()
            and p.name != "kalshi_archive_recovery.py"
        ]
        assert hits == []

    def test_script_refuses_apply(self, capsys):
        import importlib.util

        path = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "kalshi_archive_recovery_dry_run.py"
        )
        spec = importlib.util.spec_from_file_location("archive_dry_run", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.main(["--apply"]) == 2
        assert "no write path" in capsys.readouterr().err
        ast.parse(path.read_text())


# ── service: real KalshiAPIService over a mock transport ──────────────────


class TestServiceMethods:
    def _svc(self, handler):
        svc = KalshiAPIService(api_key="")
        svc.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return svc

    async def test_paths_and_params(self):
        seen = []

        def handler(request):
            seen.append(request.url)
            if request.url.path.endswith("/historical/cutoff"):
                return httpx.Response(
                    200, json={"market_settled_ts": "2026-08-16T00:00:00Z"}
                )
            if request.url.path.endswith("/historical/markets"):
                return httpx.Response(
                    200, json={"cursor": "", "markets": [{"ticker": T1}]}
                )
            return httpx.Response(
                200, json={"candlesticks": [candle(TIPOFF, close="0.4")]}
            )

        svc = self._svc(handler)
        assert (await svc.get_historical_cutoff())["market_settled_ts"]
        markets, cursor = await svc.get_historical_markets(event_ticker=E1, limit=999)
        assert markets == [{"ticker": T1}] and cursor is None
        candles = await svc.get_historical_market_candlesticks_raw(
            T1, period_interval=60, start_ts=1, end_ts=2
        )
        assert len(candles) == 1
        assert seen[1].params["limit"] == "200" and seen[1].params["event_ticker"] == E1
        assert seen[2].path.endswith(f"/historical/markets/{T1}/candlesticks")
        assert seen[2].params["period_interval"] == "60"
        await svc.client.aclose()

    async def test_empty_page_keeps_its_cursor(self):
        svc = self._svc(
            lambda r: httpx.Response(200, json={"cursor": "c2", "markets": []})
        )
        assert await svc.get_historical_markets(event_ticker=E1) == ([], "c2")
        await svc.client.aclose()

    @pytest.mark.parametrize(
        "body,reason",
        [
            ([], "body_list"),
            ({"cursor": ""}, "markets_missing"),
            ({"markets": {"ticker": T1}}, "markets_dict"),
            ({"markets": ["KXT"]}, "market_row"),
            ({"markets": [{"event_ticker": E1}]}, "market_row"),
            ({"markets": [], "cursor": 7}, "cursor_int"),
        ],
    )
    async def test_malformed_listing_raises(self, body, reason):
        from app.services.kalshi_api import KalshiArchiveResponseMalformed

        svc = self._svc(lambda r: httpx.Response(200, json=body))
        with pytest.raises(KalshiArchiveResponseMalformed) as info:
            await svc.get_historical_markets(event_ticker=E1)
        assert info.value.reason == reason
        await svc.client.aclose()

    @pytest.mark.parametrize(
        "body,reason",
        [
            ("nope", "body_str"),
            ({}, "candlesticks_missing"),
            ({"candlesticks": None}, "candlesticks_missing"),
            ({"candlesticks": {"a": 1}}, "candlesticks_dict"),
        ],
    )
    async def test_malformed_candles_raise_and_a_real_empty_list_does_not(
        self, body, reason
    ):
        from app.services.kalshi_api import KalshiArchiveResponseMalformed

        svc = self._svc(lambda r: httpx.Response(200, json=body))
        with pytest.raises(KalshiArchiveResponseMalformed) as info:
            await svc.get_historical_market_candlesticks_raw(
                T1, period_interval=60, start_ts=1, end_ts=2
            )
        assert info.value.reason == reason
        await svc.client.aclose()
        ok = self._svc(lambda r: httpx.Response(200, json={"candlesticks": []}))
        assert (
            await ok.get_historical_market_candlesticks_raw(
                T1, period_interval=60, start_ts=1, end_ts=2
            )
            == []
        )
        await ok.client.aclose()

    async def test_malformed_cutoff_raises(self):
        from app.services.kalshi_api import KalshiArchiveResponseMalformed

        svc = self._svc(lambda r: httpx.Response(200, json=["2026-08-16"]))
        with pytest.raises(KalshiArchiveResponseMalformed):
            await svc.get_historical_cutoff()
        await svc.client.aclose()

    async def test_429_raises_never_reads_as_empty(self):
        svc = self._svc(lambda r: httpx.Response(429, headers={"Retry-After": "5"}))
        for call in (
            svc.get_historical_cutoff,
            lambda: svc.get_historical_markets(event_ticker=E1),
            lambda: svc.get_historical_market_candlesticks_raw(
                T1, period_interval=60, start_ts=1, end_ts=2
            ),
        ):
            with pytest.raises(httpx.HTTPStatusError):
                await call()
        await svc.client.aclose()

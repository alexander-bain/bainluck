"""#10955 — the venue bank keeps the history the venue really has.

PILLAR: TRUTH. SHIP: opening a long-running market shows its real probability
journey, with real moves kept and only the venue's own silences drawn as gaps.

THE SPECIMEN. `/futures/109923`, Kalshi KXCAWEALTHTAX-26 (listed 2026-02-19),
Alex's TestFlight build 79 report "hideous and far too sparse" (2026-10-22).
Production served July as 7 venue points up to twelve days apart and a 168 h
largest gap, while Kalshi held a daily candle for every day of July and 636
hourly candles. Two losses in the bank build, and both are needed for the
repair (replayed on the recorded venue answers, see the PR):

  * REACH — `candle_calls` asked for the hourly tier over 31 days only, so
    everything older came from the daily tier.
  * COMPACTION — `compact_by_band`'s band older than 30 days kept 80 points of
    whatever it was given (80 of 80 on the served payload), thinning by smallest
    move with no limit on how far apart that left two kept points.

These tests build the shape synthetically. Nothing here fetches.
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import app.tasks.generic_market_history_fill as gfill
from app.utils import futures_chart_series as fcs
from app.utils import generic_market_history as gmh

NOW = datetime(2026, 10, 22, 15, 31, tzinfo=timezone.utc)
LISTED = datetime(2026, 2, 19, 1, 22, tzinfo=timezone.utc)
JOINT = gfill.VENUE_BANK_MAX_JOINT_SECONDS
ALL_BAND_EDGE = NOW - timedelta(hours=fcs.RANGE_BANDS[-2][0])


def _reference_thin(points, target):
    """The O(n²) scan `_thin_by_smallest_move` was before #10955, verbatim."""
    if target < 2 or len(points) <= target:
        return points
    work = list(points)
    while len(work) > target:
        best_index = 1
        best_cost = None
        for i in range(1, len(work) - 1):
            (t0, p0), (t1, p1), (t2, p2) = work[i - 1], work[i], work[i + 1]
            span = (t2 - t0).total_seconds()
            if span <= 0:
                cost = 0.0
            else:
                frac = (t1 - t0).total_seconds() / span
                cost = abs(p1 - (p0 + (p2 - p0) * frac))
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best_index = i
        work.pop(best_index)
    return work


def _walk(n, *, start, step, seed, cents=True):
    rng = random.Random(seed)
    value, out = 0.33, []
    for i in range(n):
        value = min(0.97, max(0.03, value + rng.choice((-0.01, 0.0, 0.0, 0.01))))
        out.append((start + i * step, round(value, 2) if cents else value))
    return out


class TestThinningIsTheSameRuleFaster:
    @pytest.mark.parametrize("seed", range(12))
    def test_thinning_matches_the_quadratic_reference(self, seed):
        rng = random.Random(seed)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        # Whole-cent walks are full of exact ties and zero-cost flat runs, which
        # is where a heap's tie-break could part from the scan's.
        points = _walk(rng.randint(40, 260), start=start, step=timedelta(minutes=rng.choice((1, 7, 60))),
                       seed=seed, cents=seed % 2 == 0)
        if seed % 3 == 0:
            points.append((points[-1][0], points[-1][1]))  # a repeated instant: span 0
        for target in (2, 3, 17, len(points) // 2, len(points) - 1):
            assert fcs._thin_by_smallest_move(list(points), target) == _reference_thin(list(points), target)

    def test_compact_by_band_without_a_joint_is_unchanged(self):
        points = _walk(9000, start=NOW - timedelta(hours=9000), step=timedelta(hours=1), seed=7)

        def reference_series(pts, target):
            # `compact_series` before #10955, verbatim but for the thinning call.
            if len(pts) <= 2:
                return pts
            heartbeat = fcs.heartbeat_seconds_for((pts[-1][0] - pts[0][0]).total_seconds(),
                                                  target_points=target)
            kept, last_value, last_ts = [], None, None
            for index, (ts, value) in enumerate(pts):
                is_edge = index == 0 or index == len(pts) - 1
                changed = last_value is None or value != last_value
                stale = last_ts is None or (ts - last_ts).total_seconds() >= heartbeat
                if is_edge or changed or stale:
                    if kept and kept[-1][0] == ts:
                        continue
                    kept.append((ts, value))
                    last_value, last_ts = value, ts
            return _reference_thin(kept, target) if len(kept) > target else kept

        out, upper, seen = [], None, set()
        for edge, budget in fcs.RANGE_BANDS:
            lower = None if edge is None else NOW - timedelta(hours=edge)
            band = [(t, p) for t, p in points
                    if (lower is None or t > lower) and (upper is None or t <= upper)]
            upper = lower
            for t, p in reference_series(band, budget) if band else []:
                if t not in seen:
                    seen.add(t)
                    out.append((t, p))
        assert fcs.compact_by_band(points, NOW) == sorted(out)


class TestTheJoint:
    def test_compaction_never_joins_wider_than_the_joint_where_the_venue_reported_closer(self):
        hourly = _walk(5900, start=LISTED, step=timedelta(hours=1), seed=3)
        kept = fcs.compact_by_band(hourly, NOW, max_joint_s=JOINT)
        gaps = [(b[0] - a[0]).total_seconds() for a, b in zip(kept, kept[1:])]
        assert max(gaps) <= JOINT
        # Without the joint the same input is cut to the budget and the old band
        # opens day-wide holes: the defect, on the same bytes.
        cut = fcs.compact_by_band(hourly, NOW)
        old = [t for t, _ in cut if t <= ALL_BAND_EDGE]
        assert len(old) == fcs.RANGE_BANDS[-1][1]
        assert max((b - a).total_seconds() for a, b in zip(old, old[1:])) > 24 * 3600

    def test_the_overshoot_is_bounded_by_span_over_joint(self):
        hourly = _walk(5900, start=LISTED, step=timedelta(hours=1), seed=4, cents=False)
        kept = fcs.compact_series(hourly, target_points=80, max_joint_s=JOINT)
        span = (hourly[-1][0] - hourly[0][0]).total_seconds()
        assert 80 < len(kept) <= 2 * span / JOINT + 2

    def test_a_flat_stretch_is_held_to_the_joint_too(self):
        """The heartbeat would otherwise bridge a flat stretch at up to
        `MAX_HEARTBEAT_SECONDS`, before thinning ever runs."""
        start = NOW - timedelta(days=3)
        flat = [(start + timedelta(hours=h), 0.4) for h in range(72)]
        kept = fcs.compact_series(flat, target_points=4, max_joint_s=3 * 3600)
        assert max((b[0] - a[0]).total_seconds() for a, b in zip(kept, kept[1:])) <= 3 * 3600

    def test_a_silence_wider_than_the_joint_stays_a_silence(self):
        start = NOW - timedelta(days=200)
        before = _walk(1000, start=start, step=timedelta(hours=1), seed=5)
        quiet_from = before[-1][0]
        after = _walk(1000, start=quiet_from + timedelta(days=4), step=timedelta(hours=1), seed=6)
        kept = fcs.compact_series(before + after, target_points=80, max_joint_s=JOINT)
        stamps = [t for t, _ in kept]
        # Both edges of the venue's four-day silence survive and nothing is put inside it.
        assert quiet_from in stamps and after[0][0] in stamps
        assert not [t for t in stamps if quiet_from < t < after[0][0]]

    def test_the_last_point_before_a_silence_is_kept_and_the_drawn_gap_is_the_venues(self):
        """lane1b R1(a): flat hourly, observed up to T+11 h after the last kept
        point, silent until T+40 h. 869bc dropped T+11 h and drew a 40 h gap over
        a 29 h venue silence."""
        start = NOW - timedelta(days=100)
        lead = start + timedelta(days=50, hours=11)
        trail = start + timedelta(days=50, hours=40)
        flat = [(start + timedelta(hours=h), 0.4) for h in range(24 * 50 + 12)]
        flat += [(start + timedelta(days=50, hours=h), 0.4) for h in range(40, 24 * 50)]
        assert flat[24 * 50 + 11][0] == lead
        kept = fcs.compact_series(flat, target_points=80, max_joint_s=JOINT)
        stamps = [t for t, _ in kept]
        assert lead in stamps and trail in stamps
        drawn = trail - max(t for t in stamps if t < trail)
        assert drawn == trail - lead == timedelta(hours=29)

    @pytest.mark.parametrize("seed", range(4))
    def test_irregular_spacing_never_joins_wider_than_the_joint(self, seed):
        """lane1b R1(b): 1–7 h venue spacing (largest venue gap 7 h, under the
        joint). 869bc kept joints up to 18 h, so a uniform-hourly test could not
        see the heartbeat landing past the joint."""
        rng = random.Random(seed)
        t, value, points = NOW - timedelta(days=200), 0.4, []
        while t < NOW - timedelta(days=1):
            t += timedelta(hours=rng.choice((1, 1, 1, 2, 3, 5, 7)))
            if rng.random() >= 0.9:
                value = round(value + rng.choice((-0.01, 0.01)), 2)
            points.append((t, value))
        assert max((b[0] - a[0]).total_seconds() for a, b in zip(points, points[1:])) <= 7 * 3600
        for kept in (
            fcs.compact_series(points, target_points=80, max_joint_s=JOINT),
            fcs.compact_by_band(points, NOW, max_joint_s=JOINT),
        ):
            assert max((b[0] - a[0]).total_seconds() for a, b in zip(kept, kept[1:])) <= JOINT

    def test_the_bank_compacts_with_the_joint(self, monkeypatch):
        seen = {}
        real = fcs.compact_by_band

        def spy(points, now, **kw):
            seen.update(kw)
            return real(points, now, **kw)

        monkeypatch.setattr(fcs, "compact_by_band", spy)
        point = gmh.VenuePoint(NOW - timedelta(hours=1), 0.4, tier="kalshi_candle_60m")
        entries = {1: {"contract": {}, "points": [point]}}
        gfill._compact_entries([SimpleNamespace(id=1, external_id="KXQ-26", name="Yes")], entries, NOW)
        assert seen == {"max_joint_s": fcs.MAX_HEARTBEAT_SECONDS}


class TestTheHourlyReach:
    def test_the_concept_fill_keeps_its_31_day_reach(self):
        assert fcs.candle_calls(5900)[1] == fcs.CandleCall(fcs.KALSHI_HOURLY_INTERVAL, timedelta(days=31))

    def test_the_venue_bank_reaches_hourly_over_the_whole_life(self):
        calls = fcs.candle_calls(5900, hourly_whole_life=True)
        assert [c.period_interval for c in calls] == [1, 60, 1440]
        assert calls[1].lookback == timedelta(hours=5900)
        assert calls[-1].lookback is None
        # Never less than the old reach, never past one request per ticker.
        assert fcs.candle_calls(200, hourly_whole_life=True)[1].lookback == timedelta(days=31)
        assert fcs.candle_calls(20000, hourly_whole_life=True)[1].lookback == timedelta(
            hours=fcs.KALSHI_HOURLY_WHOLE_LIFE_MAX_HOURS
        )
        assert fcs.KALSHI_HOURLY_WHOLE_LIFE_MAX_HOURS <= fcs.KALSHI_MAX_CANDLES_PER_REQUEST
        assert len(fcs.candle_calls(24, hourly_whole_life=True)) == 2

    def test_the_declared_hole_grains_read_the_banks_own_plan(self):
        grains = gmh.declared_hole_grains("kalshi", 5900)
        assert (timedelta(hours=5900).total_seconds(), 3600.0) in grains


# ── The specimen's shape, through the real build ─────────────────────────────


def _candle(end, price):
    cents = f"{price:.4f}"
    return {
        "end_period_ts": int(end.timestamp()),
        "price": {"close_dollars": cents, "previous_dollars": cents},
        "yes_bid": {"close_dollars": f"{max(0.01, price - 0.01):.4f}"},
        "yes_ask": {"close_dollars": f"{min(0.99, price + 0.01):.4f}"},
    }


class _ReplayKalshi:
    """The venue as measured on the specimen: an hourly candle for every hour
    since listing, a daily one at 04:00, minute candles for the last six days.
    Records every request so the cost is asserted, not described."""

    def __init__(self, tickers):
        self.requests = []
        self.series = {}
        for n, ticker in enumerate(tickers):
            hourly = _walk(int((NOW - LISTED).total_seconds() // 3600), start=LISTED.replace(minute=0)
                           + timedelta(hours=1), step=timedelta(hours=1), seed=100 + n)
            self.series[ticker] = hourly

    async def get_markets_candlesticks_raw(self, *, tickers, period_interval, start_ts, end_ts):
        self.requests.append((tuple(tickers), period_interval, start_ts, end_ts))
        out = {}
        for ticker in tickers:
            rows = self.series[ticker]
            if period_interval == 60:
                picked = rows
            elif period_interval == 1440:
                picked = [(t, p) for t, p in rows if t.hour == 4]
            else:
                picked = [(t - timedelta(minutes=m), p) for t, p in rows for m in (0, 20, 40)]
            out[ticker] = [_candle(t, p) for t, p in picked if start_ts <= t.timestamp() <= end_ts]
        return out

    async def close(self):
        pass


def _field(n):
    outcomes = [SimpleNamespace(id=10 + i, name=f"Leg {i}", external_id=f"KXCAWEALTHTAX-26-{i}",
                                current_probability=0.5 - i / 100, is_winner=None) for i in range(n)]
    market = SimpleNamespace(id=109923, source="kalshi", external_id="KXCAWEALTHTAX-26", status="open",
                             created_at=LISTED, outcomes=outcomes, mutually_exclusive=False)
    return market, outcomes


def _build(market, venue):
    async def go():
        return await gfill.build_generic_history(None, market, kalshi_service=venue, now=NOW)

    return asyncio.run(go())


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch):
    import app.tasks.futures_chart_series_fill as cfill

    monkeypatch.setattr(cfill, "REQUEST_PAUSE_SECONDS", 0)


class TestTheSpecimenShape:
    def test_july_reaches_the_reader_at_the_venues_own_spacing(self):
        market, outcomes = _field(1)
        venue = _ReplayKalshi([o.external_id for o in outcomes])
        payload = _build(market, venue)
        stamps = sorted(datetime.fromisoformat(p[0]) for p in payload["outcomes"]["10"]["points"])
        july = [t for t in stamps if t.month == 7]
        old = [t for t in stamps if t <= ALL_BAND_EDGE]
        # Master: 80 points for everything older than 30 days, July a handful of
        # points days apart. Now every joint in that band is no wider than the
        # venue's own spacing allows.
        assert max((b - a).total_seconds() for a, b in zip(old, old[1:])) <= JOINT
        assert len(july) >= 31 * 24 * 3600 / JOINT
        # The hourly tier was asked for from listing, not from 31 days back.
        hourly_starts = [r[2] for r in venue.requests if r[1] == 60]
        assert min(hourly_starts) <= int(LISTED.timestamp())

    def test_a_twelve_leg_field_costs_at_most_one_hourly_request_per_leg(self):
        market, outcomes = _field(12)
        venue = _ReplayKalshi([o.external_id for o in outcomes])
        payload = _build(market, venue)
        by_tier = {}
        for _tickers, period, _s, _e in venue.requests:
            by_tier[period] = by_tier.get(period, 0) + 1
        assert by_tier[60] <= 12 and by_tier[1440] == 1
        # Inside the per-fill request ceiling `CLAIM_TTL_SECONDS` is sized for.
        assert sum(by_tier.values()) <= 37
        # Each band keeps its budget or, where the joint binds, at most
        # `2 * span / joint + 2` — the cost bound the PR states.
        bound, upper = 0.0, NOW
        for edge, budget in fcs.RANGE_BANDS:
            lower = LISTED if edge is None else NOW - timedelta(hours=edge)
            bound += max(budget, 2 * (upper - lower).total_seconds() / JOINT + 2)
            upper = lower
        for entry in payload["outcomes"].values():
            assert len(entry["points"]) <= bound

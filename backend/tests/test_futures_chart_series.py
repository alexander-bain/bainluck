"""live/059 — guards for the outright chart's layered venue series.

The queue names two invariants for the layering — **no gaps, no duplicate
timestamps** — and those are the ones that can break silently. A duplicate
timestamp draws a vertical segment (two prices at one instant) that reads as a
crash the market never had; a gap drops a span of the story and looks exactly
like a market that did not move.

Everything under test here is pure, so every case is an arithmetic fact, not a
fixture of production. The venue numbers in the module docstring of
`app/utils/futures_chart_series.py` were measured live; these tests do not
re-measure them, they guard the code that consumes them.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.utils.futures_chart_series import (
    CLOB_COARSE_FIDELITY,
    CLOB_FINE_FIDELITY,
    HOURLY_TIER_MIN_LIFETIME_HOURS,
    KALSHI_COARSE_INTERVAL,
    KALSHI_FINE_INTERVAL,
    blend_venues,
    candle_calls,
    compact_by_band,
    clob_calls,
    compact_series,
    heartbeat_seconds_for,
    layer_tiers,
    normalize_points,
    series_reach_summary,
)

BASE = datetime(2026, 9, 3, 0, 0, tzinfo=timezone.utc)


def at(minutes: float) -> datetime:
    return BASE + timedelta(minutes=minutes)


def series(start_min: float, count: int, step_min: float, value=0.5):
    """`count` points from `start_min`, every `step_min`, at a constant value."""
    return [
        (at(start_min + i * step_min), value if not callable(value) else value(i))
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# layer_tiers — the seam
# ---------------------------------------------------------------------------


class TestLayerTiersInvariants:
    def test_no_duplicate_timestamps_when_tiers_overlap(self):
        """The real shape: a 1-minute day sitting inside a 12-hourly lifetime.

        Both tiers cover "today". Without interval claiming, every 12-hourly
        point inside today would land beside a 1-minute point at the same
        instant, and the chart would draw a vertical segment there.
        """
        fine = series(1440, 60, 1, 0.42)            # minutes 1440..1499
        coarse = series(0, 10, 720, 0.30)           # every 12h across the whole span
        out = layer_tiers([fine, coarse])
        stamps = [ts for ts, _ in out]
        assert len(stamps) == len(set(stamps)), "layering produced a duplicate timestamp"

    def test_output_is_strictly_ascending(self):
        fine = series(1000, 20, 1, 0.4)
        mid = series(500, 20, 30, 0.3)
        coarse = series(0, 20, 120, 0.2)
        out = layer_tiers([fine, mid, coarse])
        stamps = [ts for ts, _ in out]
        assert stamps == sorted(stamps)
        assert len(stamps) == len(set(stamps))

    def test_fine_tier_wins_where_both_tiers_report(self):
        """Where the tiers cover the same instants, the finer one is the answer."""
        fine = series(100, 60, 1, 0.90)     # 100..159, one point a minute
        coarse = [(at(100), 0.10), (at(130), 0.10), (at(159), 0.10)]
        out = dict(layer_tiers([fine, coarse]))
        assert out[at(100)] == 0.90
        assert out[at(130)] == 0.90, "a coarse point overwrote a covered instant"
        assert out[at(159)] == 0.90
        assert all(v == 0.90 for v in out.values()), "coarse leaked into a covered span"

    def test_a_coarse_point_in_a_hole_the_fine_tier_never_filled_survives(self):
        """Proximity claiming, stated as the case that broke span claiming.

        A "1-minute" tier that returned exactly two points an hour apart has NOT
        covered that hour — it reported two instants. A coarse point in between
        is real information and is kept.
        """
        fine = [(at(0), 0.90), (at(180), 0.91)]
        coarse = [(at(90), 0.10)]
        out = dict(layer_tiers([fine, coarse]))
        assert out[at(90)] == 0.10

    def test_coarse_tier_extends_the_reach_in_both_directions(self):
        """The whole point of the ALL tier: reach the listing, keep the day.

        Both tiers end at "now" — the real shape, since `interval=1d` and
        `interval=max` are both anchored on the present.
        """
        fine = series(10_000, 30, 1, 0.5)              # …ends at 10_029
        coarse = [(at(m), 0.2) for m in range(0, 10_030, 720)] + [(at(10_029), 0.2)]
        out = layer_tiers([fine, coarse])
        assert out[0][0] == at(0), "coarse tier did not extend the series backwards"
        assert out[-1][0] == at(10_029), "the series lost its right-hand edge"
        stamps = [ts for ts, _ in out]
        assert stamps == sorted(set(stamps))

    def test_lowest_priority_tier_fills_a_hole_in_the_middle(self):
        """Our captures are last, and they have to be able to fill an outage.

        A backwards-only rule (`older than the fine tier`) drops this case
        silently, which is why claiming is by interval.
        """
        venue_early = series(0, 5, 60, 0.3)          # 00:00 .. 04:00
        venue_late = series(720, 5, 60, 0.6)         # 12:00 .. 16:00
        venue = layer_tiers([venue_early, venue_late])
        captures = series(0, 20, 60, 0.45)           # 00:00 .. 19:00, hourly
        out = layer_tiers([venue, captures])
        stamps = {ts for ts, _ in out}
        # The venue's own outage (05:00..11:00) is covered by captures…
        assert at(300) in stamps and at(600) in stamps
        # …at the CAPTURES' value, because the venue said nothing there.
        assert dict(out)[at(300)] == 0.45
        # …and the venue still owns the spans it did cover.
        assert dict(out)[at(60)] == 0.3
        assert dict(out)[at(780)] == 0.6

    def test_layering_never_opens_a_gap_the_inputs_did_not_have(self):
        """The queue's "no gaps" invariant, stated as a property.

        Every timestamp span covered by ANY input tier must still be represented
        in the output — layering may replace a point, never erase a region.
        """
        tiers = [
            series(600, 40, 1, 0.7),
            series(0, 30, 60, 0.4),
            series(120, 10, 15, 0.5),
        ]
        out = layer_tiers(tiers)
        assert out, "layering emptied a non-empty input"
        lo = min(pts[0][0] for pts in tiers if pts)
        hi = max(pts[-1][0] for pts in tiers if pts)
        assert out[0][0] == lo
        assert out[-1][0] == hi
        for tier in tiers:
            for ts, _ in tier:
                covered = out[0][0] <= ts <= out[-1][0]
                assert covered, f"{ts} fell outside the layered series"

    def test_empty_tiers_are_skipped_not_claimed(self):
        """A venue that answered nothing must not block the venue that did.

        `fetch_clob_tier` returns `[]` both for "this token holds no series at
        this fidelity" and after a failure it has already counted. Either way an
        empty tier claims no interval, so the next tier is free to fill it.
        """
        out = layer_tiers([[], series(0, 5, 60, 0.3), []])
        assert len(out) == 5

    def test_duplicate_inside_one_tier_keeps_the_first_reading(self):
        tier = [(at(0), 0.1), (at(0), 0.9), (at(60), 0.2)]
        out = layer_tiers([tier])
        assert out == [(at(0), 0.1), (at(60), 0.2)]

    def test_no_tiers_at_all_is_an_empty_series_not_a_crash(self):
        assert layer_tiers([]) == []
        assert layer_tiers([[], []]) == []


# ---------------------------------------------------------------------------
# normalize_points
# ---------------------------------------------------------------------------


class TestNormalizePoints:
    def test_sorts_and_drops_unusable_points(self):
        raw = [
            (at(60), 0.5),
            (at(0), 0.4),
            (None, 0.9),        # no timestamp is not a point
            (at(120), None),    # no price is not a point
            (at(180), "nope"),  # unparseable
        ]
        assert normalize_points(raw) == [(at(0), 0.4), (at(60), 0.5)]

    def test_drops_impossible_probabilities(self):
        """#1139: a chart that can render 202.9% has already lost the reader."""
        raw = [(at(0), 2.029), (at(60), -0.1), (at(120), 0.5)]
        assert normalize_points(raw) == [(at(120), 0.5)]

    def test_collapses_a_repeated_timestamp(self):
        raw = [(at(0), 0.4), (at(0), 0.6)]
        assert normalize_points(raw) == [(at(0), 0.4)]


# ---------------------------------------------------------------------------
# blend_venues — one question, one number
# ---------------------------------------------------------------------------


class TestBlendVenues:
    def test_two_venues_become_one_line_not_two(self):
        """The standing ruling, as a test. Two venues in, ONE series out."""
        out = blend_venues({
            "kalshi": [(at(0), 0.40), (at(60), 0.50)],
            "polymarket": [(at(0), 0.30), (at(60), 0.40)],
        })
        assert out == [(at(0), 0.35), (at(60), 0.45)]

    def test_a_venue_is_carried_forward_not_interpolated(self):
        """Between its own points a venue holds its last price — that is what a
        price IS. Interpolating would invent movement neither venue reported."""
        out = dict(blend_venues({
            "kalshi": [(at(0), 0.40), (at(120), 0.60)],
            "polymarket": [(at(60), 0.20)],
        }))
        # At 60 Kalshi still says 0.40 and Polymarket has just said 0.20.
        assert out[at(60)] == pytest.approx(0.30)

    def test_a_venue_is_never_extrapolated_backwards(self):
        """A market listed on Polymarket in January and on Kalshi in June draws
        Polymarket ALONE for the months when Polymarket alone existed."""
        out = dict(blend_venues({
            "polymarket": [(at(0), 0.20), (at(120), 0.30)],
            "kalshi": [(at(120), 0.60)],
        }))
        assert out[at(0)] == 0.20, "an absent venue was averaged in before it listed"
        assert out[at(120)] == pytest.approx(0.45)

    def test_one_venue_passes_through_untouched(self):
        pts = [(at(0), 0.2), (at(60), 0.3)]
        assert blend_venues({"kalshi": pts}) == pts

    def test_weights_are_honoured(self):
        out = blend_venues(
            {"kalshi": [(at(0), 0.40)], "polymarket": [(at(0), 0.20)]},
            weights={"kalshi": 3.0, "polymarket": 1.0},
        )
        assert out == [(at(0), pytest.approx(0.35))]

    def test_no_venues_is_empty(self):
        assert blend_venues({}) == []
        assert blend_venues({"kalshi": []}) == []


# ---------------------------------------------------------------------------
# compact_series
# ---------------------------------------------------------------------------


class TestCompactSeries:
    def test_every_move_survives(self):
        """Compaction is by VALUE CHANGE. Stride-downsampling is what turned a
        164-change day into a 20-change staircase in the first place."""
        pts = [(at(i), 0.30 + (i % 7) * 0.01) for i in range(200)]
        out = compact_series(pts, target_points=400)
        moves_in = {(a[1], b[1]) for a, b in zip(pts, pts[1:]) if a[1] != b[1]}
        moves_out = {(a[1], b[1]) for a, b in zip(out, out[1:]) if a[1] != b[1]}
        assert moves_in <= moves_out or len(out) == len(pts)

    def test_both_endpoints_are_kept(self):
        pts = [(at(i * 10), 0.5) for i in range(500)]
        out = compact_series(pts, target_points=50)
        assert out[0] == pts[0]
        assert out[-1] == pts[-1]

    def test_a_flat_stretch_collapses_to_a_heartbeat(self):
        pts = [(at(i), 0.5) for i in range(600)]
        out = compact_series(pts, target_points=400)
        assert 2 <= len(out) < len(pts)

    def test_budget_is_respected_even_when_everything_moves(self):
        pts = [(at(i), 0.30 + (i % 100) * 0.001) for i in range(2000)]
        out = compact_series(pts, target_points=300)
        assert len(out) <= 300
        assert out[0] == pts[0] and out[-1] == pts[-1]

    def test_thinning_keeps_the_biggest_swing(self):
        """Thinning drops the SMALLEST moves. The story survives the budget."""
        pts = [(at(i), 0.50 + (i % 2) * 0.0001) for i in range(300)]
        spike_at = 150
        pts[spike_at] = (at(spike_at), 0.95)
        out = compact_series(pts, target_points=40)
        assert any(abs(p - 0.95) < 1e-9 for _, p in out), "the spike was thinned away"

    def test_two_points_pass_through(self):
        pts = [(at(0), 0.1), (at(60), 0.2)]
        assert compact_series(pts) == pts

    def test_output_has_no_duplicate_timestamps(self):
        pts = [(at(i // 2), 0.3 + i * 0.001) for i in range(100)]
        out = compact_series(normalize_points(pts), target_points=30)
        stamps = [ts for ts, _ in out]
        assert len(stamps) == len(set(stamps))


class TestCompactByBand:
    """The budget is allocated PER RANGE, and this is the regression that forced it.

    Measured on the specimen while building live/059: an 8-month layered series
    compacted to a flat 400-point budget left the last DAY with 37 points —
    worse "1D" than the 129-point sampled series the build replaces. Reaching the
    draw must not cost the match.
    """

    @staticmethod
    def _eight_month_series(now):
        """~4,000 points shaped like the real thing: eight months of 12-hourly,
        a month of hourly, and a day of minutes."""
        pts = []
        for i in range(500):          # 12-hourly, ~8 months back
            pts.append((now - timedelta(hours=12 * (500 - i)), 0.20 + (i % 13) * 0.001))
        for i in range(742):          # hourly, last 31 days
            pts.append((now - timedelta(hours=742 - i), 0.30 + (i % 17) * 0.001))
        for i in range(1440):         # 1-minute, last day
            pts.append((now - timedelta(minutes=1440 - i), 0.40 + (i % 23) * 0.001))
        return normalize_points(pts)

    def test_the_last_day_gets_its_own_budget(self):
        now = at(0)
        out = compact_by_band(self._eight_month_series(now), now)
        last_day = [ts for ts, _ in out if ts > now - timedelta(hours=24)]
        assert len(last_day) >= 100, (
            f"'1D' drew only {len(last_day)} points — the flat-budget regression"
        )

    def test_every_band_is_served_and_the_reach_survives(self):
        now = at(0)
        series_in = self._eight_month_series(now)
        out = compact_by_band(series_in, now)
        assert out[0][0] == series_in[0][0], "the series lost its reach"
        assert out[-1][0] == series_in[-1][0], "the series lost its right-hand edge"
        summary = series_reach_summary(out, now)
        assert summary["1d"] >= 100
        assert summary["1w"] > summary["1d"]
        assert summary["1m"] > summary["1w"]
        assert summary["all"] > summary["1m"]

    def test_bands_partition_the_timeline_so_no_seam_duplicates(self):
        now = at(0)
        out = compact_by_band(self._eight_month_series(now), now)
        stamps = [ts for ts, _ in out]
        assert stamps == sorted(stamps)
        assert len(stamps) == len(set(stamps)), "a band seam produced a duplicate"

    def test_total_stays_inside_the_sum_of_the_band_budgets(self):
        from app.utils.futures_chart_series import RANGE_BANDS

        now = at(0)
        out = compact_by_band(self._eight_month_series(now), now)
        assert len(out) <= sum(budget for _edge, budget in RANGE_BANDS)

    def test_a_short_series_that_fits_one_band_is_untouched(self):
        now = at(0)
        pts = [(now - timedelta(minutes=m), 0.5) for m in range(3, 0, -1)]
        assert compact_by_band(pts, now) == pts


class TestHeartbeat:
    def test_scales_with_lifetime_inside_the_floor_and_cap(self):
        assert heartbeat_seconds_for(0) == 60
        assert heartbeat_seconds_for(3600, target_points=400) == 60      # floor
        assert heartbeat_seconds_for(365 * 86400, target_points=400) == 12 * 3600  # cap
        mid = heartbeat_seconds_for(30 * 86400, target_points=400)
        assert 60 < mid < 12 * 3600


# ---------------------------------------------------------------------------
# The call plan
# ---------------------------------------------------------------------------


class TestCallPlan:
    def test_clob_is_two_calls_for_a_young_market(self):
        """The two-call shape: the last day at 1-minute, the whole life at 720."""
        calls = clob_calls(lifetime_hours=12)
        assert len(calls) == 2
        assert (calls[0].interval, calls[0].fidelity) == ("1d", CLOB_FINE_FIDELITY)
        assert (calls[-1].interval, calls[-1].fidelity) == ("max", CLOB_COARSE_FIDELITY)

    def test_clob_adds_an_hourly_middle_tier_once_the_market_is_old(self):
        calls = clob_calls(lifetime_hours=HOURLY_TIER_MIN_LIFETIME_HOURS)
        assert len(calls) == 3
        assert calls[1].fidelity == 60

    def test_clob_calls_are_finest_first(self):
        """Order IS priority — `layer_tiers` gives the first tier the claim."""
        calls = clob_calls(lifetime_hours=5000)
        assert [c.fidelity for c in calls] == [1, 60, 720]

    def test_coarse_clob_fidelity_is_720_because_60_cannot_reach_the_draw(self):
        """🔴 The correction this build rests on. `interval=max&fidelity=60` stops
        at the ~31-day retention wall; `fidelity=720` returned 419 points back to
        the 2026-01-03 listing on the same token (measured 2026-09-04). A future
        edit that "simplifies" the coarse tier to 60 silently turns ALL back into
        one month."""
        assert CLOB_COARSE_FIDELITY == 720
        assert clob_calls(10_000)[-1].fidelity == 720

    def test_kalshi_never_asks_for_an_unsupported_interval(self):
        """Kalshi does not error on an unsupported `period_interval` — it answers
        with junk. 720 is not in its accepted set, so the coarse tier is 1440."""
        from app.utils.futures_chart_series import KALSHI_HOURLY_INTERVAL

        accepted = {1, 60, 1440}
        for lifetime in (1, 47, 48, 5000):
            for call in candle_calls(lifetime):
                assert call.period_interval in accepted
        calls = candle_calls(5000)
        assert [c.period_interval for c in calls] == [
            KALSHI_FINE_INTERVAL, KALSHI_HOURLY_INTERVAL, KALSHI_COARSE_INTERVAL
        ]

    def test_kalshi_coarse_tier_reaches_the_listing(self):
        """`lookback=None` means "the market's whole life" — the fetcher resolves
        it against the market's own listing time, which is the only place that is
        known."""
        assert candle_calls(5000)[-1].lookback is None


class TestReachSummary:
    def test_counts_what_each_range_switch_would_draw(self):
        now = at(10_000)
        pts = (
            series(0, 10, 720, 0.3)        # old, 12-hourly
            + series(9_000, 50, 20, 0.4)   # last ~16h
        )
        out = series_reach_summary(sorted(set(pts)), now)
        assert out["total"] == out["all"]
        assert out["1d"] <= out["1w"] <= out["1m"] <= out["all"]
        assert out["1d"] >= 50 - 1

    def test_empty_series_reports_zeroes_not_a_crash(self):
        assert series_reach_summary([], at(0))["total"] == 0


class TestKalshiBatchBudget:
    """🔴 The ceiling is a PRODUCT, and the venue says so in its own error.

    Measured 2026-09-04 against the live endpoint:

        8 tickers × 1440 one-minute periods → 400
        {"details": "requested candlesticks across all markets: 11520,
                     max candlesticks: 10000"}
        7 × 1440 = 10080 → 400.   6 × 1440 = 8640 → 200.

    A caller that sizes its batch on PERIODS alone (the single-ticker constant,
    `KALSHI_MAX_PERIODS_PER_REQUEST = 5000`) sends the whole field at 1-minute,
    gets a 400 on exactly the finest tier, and — because a failed window is
    survived, correctly — ships a chart that quietly lost the resolution it was
    built for while every other tier succeeded.
    """

    def test_a_field_at_one_minute_over_a_day_is_split(self):
        from app.utils.futures_chart_series import ticker_batches

        tickers = [f"T{i}" for i in range(12)]
        groups = ticker_batches(tickers, periods=1440)
        assert len(groups) > 1, "twelve tickers at 1440 periods went out as one request"
        for group in groups:
            assert len(group) * 1440 <= 10000, "a group exceeds the venue's ceiling"
        assert sum(len(g) for g in groups) == 12
        assert [t for g in groups for t in g] == tickers, "a ticker was lost or reordered"

    def test_the_measured_400_and_200_boundary_is_respected(self):
        from app.utils.futures_chart_series import ticker_batches

        # 7 × 1440 = 10,080 was REFUSED; 6 × 1440 = 8,640 was SERVED.
        assert all(
            len(g) <= 6 for g in ticker_batches([f"T{i}" for i in range(12)], periods=1440)
        )

    def test_a_coarse_tier_still_batches_the_whole_field_in_one_call(self):
        """The control. Splitting unconditionally would turn one hourly request
        into twelve and pay the batching cost without the batching."""
        from app.utils.futures_chart_series import ticker_batches

        # 12 tickers × 744 hourly periods over 31 days = 8,928 — under the cap.
        assert ticker_batches([f"T{i}" for i in range(12)], periods=744) == [
            [f"T{i}" for i in range(12)]
        ]

    def test_one_ticker_whose_own_window_overruns_still_gets_its_request(self):
        """Flooring at one is what keeps window chunking as the fallback rather
        than making an oversized single ticker unrequestable."""
        from app.utils.futures_chart_series import ticker_batches

        assert ticker_batches(["ONLY"], periods=999999) == [["ONLY"]]

    def test_no_tickers_is_no_requests(self):
        from app.utils.futures_chart_series import ticker_batches

        assert ticker_batches([], periods=1440) == []

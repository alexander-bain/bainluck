"""live/059 — guards for the venue-history fill and the read path that uses it.

The pure layering is guarded in `test_futures_chart_series.py`. This file guards
the two places the layering meets the world and can go wrong without failing:

  * the Kalshi BATCH response, whose entries are neither in request order nor the
    same length as the request — measured, and the reason
    `get_markets_candlesticks_raw` keys by `market_ticker`;
  * `apply_venue_history`, where a cold cache, a dead Redis or a partial fill
    must all degrade to the chart that existed before this queue rather than to
    a blank one.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import futures_chart_series_fill as fill
from app.utils.event_concept import apply_venue_history

NOW = datetime(2026, 9, 4, 0, 0, tzinfo=timezone.utc)


def iso(minutes_ago: int) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).isoformat()


# ---------------------------------------------------------------------------
# The Kalshi batch, and the mislabelling it can cause
# ---------------------------------------------------------------------------


class _StubCandleService:
    """Answers like the real endpoint: OUT OF ORDER, and short by the unknowns."""

    def __init__(self, known: dict[str, list[dict]]):
        self.known = known
        self.calls: list[tuple] = []

    async def get_markets_candlesticks_raw(self, tickers, period_interval=60,
                                           start_ts=None, end_ts=None):
        self.calls.append((tuple(tickers), period_interval))
        # Reversed on purpose — the live endpoint returned `SHE, ALC` for a
        # request of `ALC, NOSUCH, SHE` (measured 2026-09-04).
        return {
            t: self.known[t] for t in reversed(list(tickers)) if t in self.known
        }


def _candle(ts: int, price: str) -> dict:
    return {
        "end_period_ts": ts,
        "price": {"close_dollars": price, "mean_dollars": price},
        "yes_bid": {"close_dollars": price},
        "yes_ask": {"close_dollars": price},
    }


class TestKalshiBatchIsKeyedByTicker:
    @pytest.mark.asyncio
    async def test_each_ticker_keeps_its_own_prices_when_one_is_unknown(self):
        """🔴 THE MISLABELLING GUARD. Zipping the response against the request
        list would draw Shelton's 9% curve as Alcaraz's 43% one, silently."""
        base = int(NOW.timestamp())
        service = _StubCandleService({
            "ALC": [_candle(base - 120, "0.4300"), _candle(base - 60, "0.4400")],
            "SHE": [_candle(base - 120, "0.0900"), _candle(base - 60, "0.0800")],
        })
        out = await fill.fetch_candle_tier(
            service, ["ALC", "GONE", "SHE"],
            fill.CandleCall(1, timedelta(hours=1)),
            listed_at=None, now=NOW, stats={},
        )
        assert set(out) == {"ALC", "SHE"}, "a ticker the venue omitted was invented"
        assert [round(p, 4) for _ts, p in out["ALC"]] == [0.43, 0.44]
        assert [round(p, 4) for _ts, p in out["SHE"]] == [0.09, 0.08]

    @pytest.mark.asyncio
    async def test_a_ticker_the_venue_omits_is_absent_not_empty(self):
        """An omission and an empty series are different facts (gotcha #53)."""
        service = _StubCandleService({})
        out = await fill.fetch_candle_tier(
            service, ["ALC"], fill.CandleCall(1, timedelta(hours=1)),
            listed_at=None, now=NOW, stats={},
        )
        assert out == {}

    @pytest.mark.asyncio
    async def test_the_whole_field_costs_one_request_per_tier(self):
        """Batching is the reason 12 outcomes are affordable at three tiers."""
        base = int(NOW.timestamp())
        service = _StubCandleService({
            t: [_candle(base - 60, "0.10")] for t in ("A", "B", "C", "D")
        })
        stats: dict = {}
        await fill.fetch_candle_tier(
            service, ["A", "B", "C", "D"], fill.CandleCall(60, timedelta(hours=2)),
            listed_at=None, now=NOW, stats=stats,
        )
        assert stats["candle_requests"] == 1
        assert service.calls[0][0] == ("A", "B", "C", "D")

    @pytest.mark.asyncio
    async def test_a_failed_window_is_counted_not_swallowed(self):
        class _Boom:
            async def get_markets_candlesticks_raw(self, **_kw):
                raise RuntimeError("502")

        stats: dict = {}
        out = await fill.fetch_candle_tier(
            _Boom(), ["A"], fill.CandleCall(60, timedelta(hours=2)),
            listed_at=None, now=NOW, stats=stats,
        )
        assert out == {}
        assert stats["window_errors"] == 1
        assert "candle_requests" not in stats


# ---------------------------------------------------------------------------
# The CLOB tier
# ---------------------------------------------------------------------------


class TestClobTier:
    @pytest.mark.asyncio
    async def test_an_empty_answer_is_recorded_as_empty_not_as_a_failure(self):
        class _Empty:
            async def get_prices_history(self, **_kw):
                return []

        stats: dict = {}
        assert await fill.fetch_clob_tier(
            _Empty(), "tok", fill.ClobCall("1d", 1), stats=stats
        ) == []
        assert stats["clob_empty"] == 1
        assert "fetch_errors" not in stats

    @pytest.mark.asyncio
    async def test_a_failure_is_recorded_as_a_failure_not_as_empty(self):
        """gotcha #53 — the two must never collapse into one signal."""
        from app.services.polymarket_api import PolymarketHistoryUnavailable

        class _Down:
            async def get_prices_history(self, **_kw):
                raise PolymarketHistoryUnavailable("timeout")

        stats: dict = {}
        assert await fill.fetch_clob_tier(
            _Down(), "tok", fill.ClobCall("1d", 1), stats=stats
        ) == []
        assert stats["fetch_errors"] == 1
        assert "clob_empty" not in stats


# ---------------------------------------------------------------------------
# Cache freshness bookkeeping
# ---------------------------------------------------------------------------


class TestCacheAge:
    def test_reports_the_age_of_a_stamped_payload(self):
        payload = {"built_at": (NOW - timedelta(hours=2)).isoformat()}
        assert fill.cache_age_seconds(payload, now=NOW) == pytest.approx(7200, abs=1)

    def test_an_unstamped_payload_answers_none_not_zero(self):
        """None means UNKNOWN, and the read path treats unknown as stale. Zero
        would mean 'just built' and would suppress the refresh forever."""
        assert fill.cache_age_seconds({}, now=NOW) is None
        assert fill.cache_age_seconds({"built_at": "not-a-date"}, now=NOW) is None


class TestStalenessOrdering:
    def test_a_redis_that_is_down_returns_the_input_order(self, monkeypatch):
        monkeypatch.setattr(
            "app.tasks.redis_state.get_redis_client", lambda *a, **k: None
        )
        assert fill.order_by_staleness([3, 1, 2]) == [3, 1, 2]

    def test_never_filled_markets_lead_then_least_recently_filled(self, monkeypatch):
        class _RC:
            def zmscore(self, _key, members):
                scores = {"1": 500.0, "2": None, "3": 100.0}
                return [scores.get(m) for m in members]

        monkeypatch.setattr(
            "app.tasks.redis_state.get_redis_client", lambda *a, **k: _RC()
        )
        assert fill.order_by_staleness([1, 2, 3]) == [2, 3, 1]


# ---------------------------------------------------------------------------
# The point budget, spent per RANGE BAND
# ---------------------------------------------------------------------------


class _Outcome:
    def __init__(self, id, name, external_id, probability="0.42"):
        self.id = id
        self.name = name
        self.external_id = external_id
        self.current_probability = probability


class _Market:
    def __init__(self, outcomes, created_at):
        self.id = 4242
        self.source = "kalshi"
        self.outcomes = outcomes
        self.created_at = created_at


class TestTheBudgetIsSpentPerBand:
    """🔴 ONE flat budget over a lifetime series starves the range a reader
    opens on.

    This is the ship's own failure mode wearing the ship's clothes. "All reaches
    the draw" means the series spans eight months; a single 400-point budget
    spread across eight months leaves the last DAY with a few dozen points —
    fewer than the ~78-minute sampler this queue exists to replace. The chart
    would look longer and read worse, and every other guard in this file would
    still be green, because the series is present, dense in aggregate, gapless
    and duplicate-free. Only counting the points INSIDE a range catches it.
    """

    async def _series_for_an_eight_month_market(self, monkeypatch):
        """One outcome, eight months old, dense to the minute for the last day.

        Every value distinct, so compaction is being asked for its budget rather
        than being let off by a flat line.
        """
        outcome = _Outcome(11, "Carlos Alcaraz", "KXATP-26USO-ALC")
        market = _Market([outcome], NOW - timedelta(days=244))

        venue: list[tuple[datetime, float]] = []
        # Eight months at 12-hourly — the `interval=max&fidelity=720` tier.
        for i in range(488, 0, -1):
            venue.append((NOW - timedelta(hours=12 * i), 0.20 + (i % 97) * 0.001))
        # The last day at the venue's minutes — the `interval=1d&fidelity=1` tier.
        for i in range(1440, 0, -1):
            venue.append((NOW - timedelta(minutes=i), 0.40 + (i % 89) * 0.001))

        async def _legs(_session, _market, **_kw):
            return [market]

        async def _captures(_session, _ids):
            return {}

        async def _kalshi(_service, _outcomes, **_kw):
            return {"KXATP-26USO-ALC": venue}

        monkeypatch.setattr(fill, "find_venue_legs", _legs)
        monkeypatch.setattr(fill, "capture_series_by_name", _captures)
        monkeypatch.setattr(fill, "kalshi_field_series", _kalshi)

        payload = await fill.build_market_series(
            None, market, kalshi_service=object(), now=NOW
        )
        points = payload["outcomes"]["carlos alcaraz"]
        return [
            (datetime.fromisoformat(ts), p) for ts, p in points
        ]

    async def test_the_last_day_keeps_its_own_budget_inside_an_eight_month_series(
        self, monkeypatch
    ):
        series = await self._series_for_an_eight_month_market(monkeypatch)

        # The control: the series really does reach back eight months, so the
        # count below is being measured on the hard case and not on a short one.
        assert series[0][0] < NOW - timedelta(days=200), "not an ALL-range series"

        last_day = [p for p in series if p[0] > NOW - timedelta(hours=24)]
        assert len(last_day) >= 100, (
            f"1D drew {len(last_day)} points out of {len(series)} — the budget "
            f"was spent over the lifetime instead of per band"
        )

    async def test_the_older_bands_are_not_starved_by_the_dense_day_either(
        self, monkeypatch
    ):
        """The other direction, and the reason this is a BAND split rather than
        'give the last day more'. A reader who opens All must get a drawn line
        for the eight months too, not a flat stub with a spike on the end."""
        series = await self._series_for_an_eight_month_market(monkeypatch)

        older = [p for p in series if p[0] <= NOW - timedelta(hours=720)]
        assert len(older) >= 40, f"the pre-1M reach drew only {len(older)} points"

        # And the whole thing still fits a chart payload — a per-band budget
        # that simply spent more everywhere would pass both counts above.
        assert len(series) <= 600, f"{len(series)} points is not a compaction"


# ---------------------------------------------------------------------------
# The read path
# ---------------------------------------------------------------------------


def _competitor(name, points, outcome_id=7):
    return {
        "name": name,
        "outcome_id": outcome_id,
        "probability": 0.4,
        "history": [{"timestamp": ts, "probability": p} for ts, p in points],
    }


class TestOutcomeIdSurvivesTheSwap:
    """🔴 A line the renderer cannot key is a line it does not draw.

    `competitorsToOutcomeHistory` skips any competitor whose `outcome_id` is not
    a number. A competitor the venue fill matched by NAME but the sampled pass
    did not would otherwise be handed 400 points and then dropped from the chart
    entirely — strictly worse than before the fill existed.
    """

    def test_the_cache_supplies_an_id_the_sampled_pass_never_set(self, monkeypatch):
        monkeypatch.setattr(
            fill, "read_cached_series",
            lambda *_a, **_k: {
                "built_at": NOW.isoformat(),
                "outcomes": {"carlos alcaraz": [[iso(m), 0.3] for m in range(60, 0, -1)]},
                "outcome_ids": {"carlos alcaraz": 4242},
            },
        )
        comps = [_competitor("Carlos Alcaraz", [(iso(60), 0.4), (iso(30), 0.4)],
                             outcome_id=None)]
        assert apply_venue_history(99, comps) == 1
        assert comps[0]["outcome_id"] == 4242

    def test_an_unkeyable_competitor_is_left_alone_rather_than_half_swapped(
        self, monkeypatch
    ):
        """No id anywhere: keep the sampled series, which at least has an id
        wherever the renderer already accepted it."""
        monkeypatch.setattr(
            fill, "read_cached_series",
            lambda *_a, **_k: {
                "built_at": NOW.isoformat(),
                "outcomes": {"carlos alcaraz": [[iso(m), 0.3] for m in range(60, 0, -1)]},
                "outcome_ids": {},
            },
        )
        sampled = [(iso(60), 0.4), (iso(30), 0.4)]
        comps = [_competitor("Carlos Alcaraz", sampled, outcome_id=None)]
        assert apply_venue_history(99, comps) == 0
        assert comps[0]["history"] == [
            {"timestamp": ts, "probability": p} for ts, p in sampled
        ]

    def test_an_existing_id_is_never_overwritten(self, monkeypatch):
        monkeypatch.setattr(
            fill, "read_cached_series",
            lambda *_a, **_k: {
                "built_at": NOW.isoformat(),
                "outcomes": {"carlos alcaraz": [[iso(m), 0.3] for m in range(60, 0, -1)]},
                "outcome_ids": {"carlos alcaraz": 4242},
            },
        )
        comps = [_competitor("Carlos Alcaraz", [(iso(60), 0.4), (iso(30), 0.4)],
                             outcome_id=11)]
        apply_venue_history(99, comps)
        assert comps[0]["outcome_id"] == 11


class TestApplyVenueHistory:
    def test_a_cold_cache_leaves_every_line_exactly_as_it_was(self, monkeypatch):
        monkeypatch.setattr(fill, "read_cached_series", lambda *_a, **_k: None)
        monkeypatch.setattr(fill, "claim_on_demand_fill", lambda *_a, **_k: False)
        sampled = [(iso(120), 0.40), (iso(60), 0.41)]
        comps = [_competitor("Carlos Alcaraz", sampled)]
        before = json.dumps(comps)
        assert apply_venue_history(99, comps) == 0
        assert json.dumps(comps) == before

    def test_a_cold_cache_asks_for_a_fill_exactly_once(self, monkeypatch):
        asked: list[int] = []
        monkeypatch.setattr(fill, "read_cached_series", lambda *_a, **_k: None)
        monkeypatch.setattr(
            fill, "claim_on_demand_fill",
            lambda market_id, **_k: not asked and (asked.append(market_id) or True),
        )
        comps = [_competitor("Carlos Alcaraz", [(iso(60), 0.4), (iso(30), 0.4)])]
        apply_venue_history(99, comps)
        apply_venue_history(99, comps)
        assert asked == [99], "a second page view bought a second fill"

    def test_venue_points_are_layered_in_and_the_line_gets_denser(self, monkeypatch):
        venue = [[iso(m), 0.30 + (m % 7) * 0.001] for m in range(600, 0, -1)]
        monkeypatch.setattr(
            fill, "read_cached_series",
            lambda *_a, **_k: {
                "built_at": NOW.isoformat(),
                "outcomes": {"carlos alcaraz": venue},
            },
        )
        sampled = [(iso(300), 0.40), (iso(150), 0.41)]
        comps = [_competitor("Carlos Alcaraz", sampled)]
        assert apply_venue_history(99, comps) == 1
        assert len(comps[0]["history"]) > len(sampled) * 5

    def test_the_fresh_sampled_tail_survives_a_stale_cache(self, monkeypatch):
        """THE STALENESS GUARD. The cache may be hours old; the chart may not be.

        The venue series stops where the last fill stopped. The sampled captures
        run to now. Layering — not replacing — is what keeps the right-hand edge
        current, and it is why the cache TTL can be 36 hours.
        """
        venue = [[iso(m), 0.30] for m in range(600, 300, -1)]  # stops 5h ago
        monkeypatch.setattr(
            fill, "read_cached_series",
            lambda *_a, **_k: {
                "built_at": (NOW - timedelta(hours=5)).isoformat(),
                "outcomes": {"carlos alcaraz": venue},
            },
        )
        monkeypatch.setattr(fill, "claim_on_demand_fill", lambda *_a, **_k: False)
        comps = [_competitor("Carlos Alcaraz", [(iso(120), 0.55), (iso(2), 0.58)])]
        apply_venue_history(99, comps)
        latest = comps[0]["history"][-1]["timestamp"]
        assert latest >= iso(3), (
            "the chart ended where the stale cache ended, not where the data does"
        )

    def test_a_stale_cache_is_still_used_and_also_triggers_a_refresh(self, monkeypatch):
        asked: list[int] = []
        venue = [[iso(m), 0.30] for m in range(600, 300, -1)]
        monkeypatch.setattr(
            fill, "read_cached_series",
            lambda *_a, **_k: {
                "built_at": (NOW - timedelta(hours=9)).isoformat(),
                "outcomes": {"carlos alcaraz": venue},
            },
        )
        monkeypatch.setattr(
            fill, "claim_on_demand_fill",
            lambda market_id, **_k: bool(asked.append(market_id)) or True,
        )
        comps = [_competitor("Carlos Alcaraz", [(iso(120), 0.5), (iso(60), 0.5)])]
        assert apply_venue_history(99, comps) == 1, "a stale payload was thrown away"
        assert asked == [99]

    def test_a_competitor_the_fill_missed_keeps_its_sampled_series(self, monkeypatch):
        monkeypatch.setattr(
            fill, "read_cached_series",
            lambda *_a, **_k: {
                "built_at": NOW.isoformat(),
                "outcomes": {"carlos alcaraz": [[iso(m), 0.3] for m in range(60, 0, -1)]},
            },
        )
        sampled = [(iso(120), 0.20), (iso(60), 0.21)]
        comps = [_competitor("Carlos Alcaraz", sampled), _competitor("Ben Shelton", sampled)]
        assert apply_venue_history(99, comps) == 1
        assert comps[1]["history"] == [
            {"timestamp": ts, "probability": p} for ts, p in sampled
        ], "a partial fill blanked the outcomes it missed"

    def test_a_dead_redis_costs_density_not_the_chart(self, monkeypatch):
        def _boom(*_a, **_k):
            raise RuntimeError("redis down")

        monkeypatch.setattr(fill, "read_cached_series", _boom)
        sampled = [(iso(120), 0.4), (iso(60), 0.41)]
        comps = [_competitor("Carlos Alcaraz", sampled)]
        assert apply_venue_history(99, comps) == 0
        assert comps[0]["history"] == [
            {"timestamp": ts, "probability": p} for ts, p in sampled
        ]

    def test_no_evolution_market_is_a_no_op(self):
        comps = [_competitor("Carlos Alcaraz", [(iso(60), 0.4)])]
        assert apply_venue_history(None, comps) == 0
        assert apply_venue_history(99, []) == 0

    def test_the_merged_series_has_no_duplicate_timestamps(self, monkeypatch):
        """The queue's invariant, asserted on the payload a browser receives."""
        venue = [[iso(m), 0.30] for m in range(600, 0, -1)]
        monkeypatch.setattr(
            fill, "read_cached_series",
            lambda *_a, **_k: {
                "built_at": NOW.isoformat(),
                "outcomes": {"carlos alcaraz": venue},
            },
        )
        # Sampled points deliberately land ON venue timestamps.
        comps = [_competitor("Carlos Alcaraz", [(iso(500), 0.9), (iso(100), 0.9)])]
        apply_venue_history(99, comps)
        stamps = [pt["timestamp"] for pt in comps[0]["history"]]
        assert stamps == sorted(stamps)
        assert len(stamps) == len(set(stamps))

"""Queue #183 Item 4 (#182 historical twin): curve-side WEATHER wide-spread
FABRICATED-MIDPOINT exclusion.

#182 proved that a WIDE Kalshi book (yes_ask - yes_bid >= 0.50) with no trade has
NO real price discovery at its midpoint — the captured cal_prob is a fabricated
number, not a market line. #182 fixed this FORWARD (the poll's
``_kalshi_yes_probability`` now skips wide/one-sided no-trade books,
``_KALSHI_TIGHT_SPREAD_MAX = 0.50``). This is the read-side HISTORICAL twin: the
rows captured before that guard shipped still poison the published curve.

WEATHER-GATED ONLY. #182's census showed weather's ~65 wide-spread rows are the
disease (weather ECE ~3.97 → ~3.49pp once excluded), while tech's miscalibration
is genuine (~10pp is real, NOT wide-book noise), so tech is deliberately left in
(its census is parked). These rows carry a live bid (bid > 0), so the #940
liquidity filter KEEPS them — the SPREAD is the discriminator the liquidity filter
misses.

Read-side only (gotcha #21) — never mutates is_winner / calibration_probability.
This suite covers the canonical predicate (weather gate, spread threshold,
no-trade rule), the rule text, and that BOTH the precompute task and the route
fallback embed the exclusion.
"""

import inspect

from app.tasks import precompute_calibration
from app.tasks.precompute_calibration import (
    WEATHER_WIDE_SPREAD_MIN,
    WEATHER_WIDE_SPREAD_RULE_TEXT,
    outcome_is_weather_wide_spread,
)


class TestWeatherWideSpreadPredicate:
    def test_wide_no_trade_weather_excluded(self):
        # bid=0.05 / ask=0.95 → spread 0.90 (>= 0.50), no trade → fabricated midpoint.
        assert outcome_is_weather_wide_spread("kalshi", "weather", 0.05, 0.95, None) is True
        assert outcome_is_weather_wide_spread("kalshi", "weather", 0.05, 0.95, 0) is True
        # Exactly at the 0.50 boundary is wide (>=).
        assert outcome_is_weather_wide_spread("kalshi", "weather", 0.20, 0.70, None) is True

    def test_tight_book_kept(self):
        # A tight two-sided book (spread < 0.50) is real price discovery — KEEP.
        assert outcome_is_weather_wide_spread("kalshi", "weather", 0.45, 0.55, None) is False
        assert outcome_is_weather_wide_spread("kalshi", "weather", 0.40, 0.60, None) is False

    def test_wide_but_traded_kept(self):
        # A wide book that ACTUALLY traded has real evidence (#182 uses last_price
        # then) — KEEP, do not exclude.
        assert outcome_is_weather_wide_spread("kalshi", "weather", 0.05, 0.95, 0.42) is False

    def test_gated_to_weather_only(self):
        # Tech (and every other category) is deliberately NOT excluded — its
        # miscalibration is genuine per #182's census.
        assert outcome_is_weather_wide_spread("kalshi", "tech", 0.05, 0.95, None) is False
        assert outcome_is_weather_wide_spread("kalshi", "economics", 0.05, 0.95, None) is False
        assert outcome_is_weather_wide_spread("kalshi", None, 0.05, 0.95, None) is False

    def test_scoped_to_kalshi_only(self):
        assert outcome_is_weather_wide_spread("polymarket", "weather", 0.05, 0.95, None) is False
        assert outcome_is_weather_wide_spread("odds_api", "weather", 0.05, 0.95, None) is False
        assert outcome_is_weather_wide_spread(None, "weather", 0.05, 0.95, None) is False

    def test_missing_book_safe(self):
        # A one-sided/absent book (no bid or no ask) is handled by the liquidity
        # filter, not here — this predicate needs a two-sided book to measure spread.
        assert outcome_is_weather_wide_spread("kalshi", "weather", None, 0.95, None) is False
        assert outcome_is_weather_wide_spread("kalshi", "weather", 0.05, None, None) is False
        assert outcome_is_weather_wide_spread("kalshi", "weather", None, None, None) is False

    def test_threshold_constant(self):
        assert WEATHER_WIDE_SPREAD_MIN == 0.50


class TestRuleText:
    def test_rule_describes_the_exclusion(self):
        t = WEATHER_WIDE_SPREAD_RULE_TEXT.lower()
        assert "weather" in t
        assert "spread" in t
        assert "midpoint" in t
        # Weather-only, tech kept.
        assert "tech" in t
        # Read-side guarantee (gotcha #21).
        assert "never" in t and "mutate" in t


class TestPrecomputeQueryEmbedsExclusion:
    def test_main_query_excludes_weather_wide_spread(self):
        src = (inspect.getsource(precompute_calibration.compute_calibration_payload)
               + precompute_calibration._calibration_population_ctes())
        assert "is_weather_wide_spread" in src
        assert "NOT ro.is_weather_wide_spread" in src
        # Transparency count + payload surface.
        assert "weather_wide_spread_excluded" in src
        assert '"weather_wide_spread_filter"' in src

    def test_exclusion_is_read_side_only(self):
        src = inspect.getsource(
            precompute_calibration.compute_calibration_payload
        ).lower()
        assert "update futures_outcomes" not in src
        assert "update futures_markets" not in src
        assert "delete from futures_outcomes" not in src


class TestRouteFallbackDelegatesToSharedPath:
    def test_route_fallback_delegates_to_shared_payload(self):
        # Queue #257 Item 1: the cold-cache fallback delegates to the ONE shared
        # compute_calibration_payload, so it inherits the weather wide-spread
        # exclusion by construction — a cache miss can never be poisoned.
        from app.routes import calibration as calibration_route

        src = inspect.getsource(calibration_route.public_calibration)
        assert "compute_calibration_payload" in src

"""Queue #159 (#1010): curve-side ESPORTS malformed-MULTI "match bundle" exclusion.

Polymarket flattens a whole esports match into ONE non-partition market —
cumulative "Total Kills Over/Under X.5 in Game N" ladders (Over 17.5, 18.5, ...
54.5), per-game winners, first-blood props — with dozens of outcomes (market
128754: 73 outcomes, 71 winners). Because the Over rungs are CUMULATIVE, a
high-kill game legitimately resolves many YES at once (gotcha #17), so the market
has >=2 winners. That is the exact counter-class #157's normalization refuses:
the prices neither sum to ~1.0 (multiple partitions mashed — can't be normalized
by one divisor) nor bucket as a clean single prediction. OPS-557 census
(2026-07-11): n=93,629 poly outcomes, winrate 0.395 vs cp 0.487 (+9.2pp), avg
per-market cp-sum 17.9; sub-bands <25%-win +23.7pp / 25-50% +10.1pp / >50%
-4.1pp. The >=2-winner grading is CORRECT for cumulative ladders, so these rows
are EXCLUDED from the curve, never re-graded — the >=3-outcome sibling of the
malformed-binary filter.

Read-side only (gotcha #21) — never mutates is_winner / calibration_probability.
This suite covers the canonical predicate, the rule text, the corrections-log
entry, and that BOTH the precompute task and the route fallback embed the
exclusion so a cache miss is not silently esports-inflated.
"""

import inspect

from app.tasks import precompute_calibration
from app.tasks.precompute_calibration import (
    CALIBRATION_CORRECTIONS,
    ESPORTS_MULTI_BUNDLE_CATEGORY,
    ESPORTS_MULTI_BUNDLE_RULE_TEXT,
    market_is_esports_multi_bundle,
)


class TestEsportsMultiBundlePredicate:
    def test_esports_multi_winner_bundle_excluded(self):
        # >=3 outcomes AND >=2 winners in esports = the match-bundle cohort.
        assert market_is_esports_multi_bundle("esports", 73, 71) is True
        assert market_is_esports_multi_bundle("esports", 3, 2) is True
        assert market_is_esports_multi_bundle("esports", 98, 22) is True

    def test_single_winner_partition_kept(self):
        # A genuine single-winner partition (e.g. tournament winner) is NOT a
        # bundle — it is the class #157 normalizes, not excludes.
        assert market_is_esports_multi_bundle("esports", 16, 1) is False
        assert market_is_esports_multi_bundle("esports", 3, 1) is False

    def test_zero_winner_not_a_bundle(self):
        # Zero winners is a void (handled elsewhere), not the >=2-winner class.
        assert market_is_esports_multi_bundle("esports", 10, 0) is False

    def test_two_outcome_market_is_binary_not_multi(self):
        # 2-outcome markets are the malformed_binary filter's job, not this one.
        assert market_is_esports_multi_bundle("esports", 2, 2) is False

    def test_other_categories_untouched(self):
        # esports-scoped: the same poly bundle shape is well-calibrated in
        # basketball/tennis/hockey (~+1.5pp), so a blanket exclusion would drop
        # good data. The general sweep is #160's sentinel.
        assert market_is_esports_multi_bundle("basketball", 73, 71) is False
        assert market_is_esports_multi_bundle("tennis", 10, 5) is False
        assert market_is_esports_multi_bundle("soccer", 20, 8) is False

    def test_none_and_empty_safe(self):
        assert market_is_esports_multi_bundle(None, 73, 71) is False
        assert market_is_esports_multi_bundle("", 73, 71) is False

    def test_category_constant(self):
        assert ESPORTS_MULTI_BUNDLE_CATEGORY == "esports"


class TestRuleText:
    def test_rule_describes_the_exclusion(self):
        t = ESPORTS_MULTI_BUNDLE_RULE_TEXT.lower()
        assert "esports" in t
        assert "bundle" in t
        # Names the cumulative-ladder mechanism.
        assert "cumulative" in t
        assert "ladder" in t
        # Read-side guarantee.
        assert "never" in t and "mutate" in t
        # Frames it as the malformed-binary sibling.
        assert "malformed-binary" in t or "malformed binary" in t


class TestCorrectionsLog:
    def test_esports_correction_present(self):
        titles = [c["title"].lower() for c in CALIBRATION_CORRECTIONS]
        assert any("esports" in t and "bundle" in t for t in titles)


class TestPrecomputeQueryEmbedsExclusion:
    def test_main_query_excludes_esports_bundles(self):
        src = inspect.getsource(
            precompute_calibration._precompute_calibration_main
        )
        # The CTE that identifies the >=3-outcome/>=2-winner esports markets.
        assert "esports_multi_bundles AS (" in src
        # The exclusion is applied in the deduped filter.
        assert "NOT ro.is_esports_bundle" in src
        # Transparency count + payload surface.
        assert "esports_bundle_excluded" in src
        assert '"esports_multi_bundle_filter"' in src

    def test_exclusion_is_read_side_only(self):
        # Guardrail (gotcha #21): the exclusion must never mutate is_winner/cp.
        src = inspect.getsource(
            precompute_calibration._precompute_calibration_main
        ).lower()
        assert "update futures_outcomes" not in src
        assert "update futures_markets" not in src
        assert "delete from futures_outcomes" not in src


class TestRouteFallbackEmbedsExclusion:
    def test_route_fallback_mirrors_exclusion(self):
        # The cold-cache fallback in routes/calibration.py must stay in sync so a
        # cache miss is not silently esports-inflated.
        from app.routes import calibration as calibration_route

        src = inspect.getsource(calibration_route)
        assert "esports_multi_bundles AS (" in src
        assert "NOT ro.is_esports_bundle" in src
        assert "esports_multi_bundle_filter" in src

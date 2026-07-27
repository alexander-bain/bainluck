"""L2-79 (#997/#1010, #940/#762): curve-side exclusion of two contamination
classes surfaced by the 2026-07-09 census.

Item 1 — MALFORMED BINARIES: a resolved 2-outcome mutually-exclusive market must
have exactly one winner. Zero winners (both-false = void/malformed) and two
winners (both-winner = impossible) are data artifacts, not scoreable outcomes.
The census found ~43K both-false + ~1.5K both-winner across every category.

Item 2 — GOLF FIELD ONE-SIDED-ASK PLACEHOLDERS: in a mutually-exclusive golf
winner/round-leader market, at most one outcome can legitimately price >=0.80
(mex probabilities must sum to ~1). Over-subscribed markets (>=2 outcomes >=0.80)
are Kalshi one-sided-ask placeholders (98.6% loss @ cp 0.93); genuine single
leaders (one outcome >=0.80, 82% win) stay in.

Both are read-side exclusions only — they never mutate is_winner /
calibration_probability (gotcha #21). This suite covers the canonical predicates,
the rule text, and that the production precompute query embeds the exclusions +
transparency counts + payload keys.
"""

import inspect

from app.tasks import precompute_calibration
from app.tasks.precompute_calibration import (
    GOLF_PLACEHOLDER_HIGH_BAND,
    GOLF_PLACEHOLDER_RULE_TEXT,
    MALFORMED_BINARY_RULE_TEXT,
    binary_is_malformed,
    outcome_in_golf_high_band,
)


class TestMalformedBinaryPredicate:
    def test_both_false_is_malformed(self):
        # Zero winners in a 2-outcome mex market = void/malformed resolution.
        assert binary_is_malformed(2, 0) is True

    def test_both_winner_is_malformed(self):
        # Two winners in a 2-outcome mex market = impossible / double-graded.
        assert binary_is_malformed(2, 2) is True

    def test_well_formed_binary_kept(self):
        # Exactly one winner is the correct, scoreable shape.
        assert binary_is_malformed(2, 1) is False

    def test_non_binary_markets_unaffected(self):
        # The rule is scoped to 2-outcome markets; multi-outcome markets (e.g. a
        # 10-nominee award) are never flagged by this filter, whatever their
        # winner count.
        assert binary_is_malformed(3, 0) is False
        assert binary_is_malformed(10, 1) is False
        assert binary_is_malformed(1, 0) is False


class TestGolfHighBandPredicate:
    def test_high_band_flagged(self):
        assert outcome_in_golf_high_band(0.80) is True
        assert outcome_in_golf_high_band(0.95) is True

    def test_below_band_kept(self):
        # The low-priced field (most players) is genuine and stays in.
        assert outcome_in_golf_high_band(0.79) is False
        assert outcome_in_golf_high_band(0.02) is False

    def test_none_is_not_in_band(self):
        assert outcome_in_golf_high_band(None) is False

    def test_threshold_value(self):
        assert GOLF_PLACEHOLDER_HIGH_BAND == 0.80


class TestRuleText:
    def test_malformed_rule_describes_the_filter(self):
        t = MALFORMED_BINARY_RULE_TEXT.lower()
        assert "2-outcome" in t or "two-outcome" in t
        assert "mutually-exclusive" in t
        assert "never mutates" in t

    def test_golf_rule_describes_the_filter(self):
        t = GOLF_PLACEHOLDER_RULE_TEXT.lower()
        assert "golf" in t
        assert "0.80" in t or ">=0.80" in t
        assert "single-leader" in t or "single leader" in t
        assert "never mutates" in t


class TestPrecomputeQueryEmbedsExclusions:
    def test_main_query_embeds_malformed_binary_exclusion(self):
        src = (inspect.getsource(precompute_calibration.compute_calibration_payload)
               + precompute_calibration._calibration_population_ctes())
        # The CTE that identifies malformed binaries.
        assert "malformed_binaries" in src
        assert "HAVING COUNT(*) = 2" in src
        # Applied in the deduped WHERE (the published denominator).
        assert "NOT ro.is_malformed_binary" in src
        # Transparency counts + payload surface.
        assert "both_false_excluded" in src
        assert "both_winner_excluded" in src
        assert '"malformed_binary_filter"' in src

    def test_main_query_embeds_golf_placeholder_exclusion(self):
        src = (inspect.getsource(precompute_calibration.compute_calibration_payload)
               + precompute_calibration._calibration_population_ctes())
        # The CTE that identifies over-subscribed golf placeholder markets.
        assert "golf_placeholder_markets" in src
        assert "HAVING COUNT(*) >= 2" in src
        # Applied in the deduped WHERE.
        assert "NOT ro.is_golf_placeholder" in src
        # Transparency count + payload surface.
        assert "golf_placeholder_excluded" in src
        assert '"golf_placeholder_filter"' in src

    def test_exclusions_are_read_side_only(self):
        # Guardrail (gotcha #21): the exclusions must never mutate resolutions.
        # The precompute task is a SELECT-only read path — assert it issues no
        # UPDATE/DELETE against futures_outcomes / futures_markets.
        src = (inspect.getsource(precompute_calibration.compute_calibration_payload)
               + precompute_calibration._calibration_population_ctes())
        lowered = src.lower()
        assert "update futures_outcomes" not in lowered
        assert "update futures_markets" not in lowered
        assert "delete from futures_outcomes" not in lowered

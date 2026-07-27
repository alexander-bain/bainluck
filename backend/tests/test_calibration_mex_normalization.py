"""Queue #157 (#1012): curve-side MULTI-CANDIDATE NORMALIZATION.

A resolved mutually-exclusive market with >=3 outcomes is a partition of ONE
question — its outcome probabilities MUST sum to ~1.0. Kalshi/Polymarket stamp
each candidate at its one-sided ask, so the per-market cp sum inflates to 2.4-5.3
(census 2026-07-09: economics 2.37, entertainment 3.09, tech 2.23, football 4.63).
The fix divides each eligible outcome's cp by the per-market sum when that sum
exceeds the threshold, so the market sums to ~1.

Counter-class guard: a genuine partition resolves with EXACTLY one winner.
Cumulative-threshold ladders and independent binaries mislabeled mutually_exclusive
resolve with 2+ winners — they legitimately sum >1 and must NOT be normalized
(#155 pass3 ladder lesson; gotcha #23 caveat). Zero-winner voids are excluded too.

Read-side only (gotcha #21) — never mutates is_winner / calibration_probability.
This suite covers the canonical predicate, the rule text, and that both the
precompute task and the route fallback embed the normalization CTEs.
"""

import inspect

from app.tasks import precompute_calibration
from app.tasks.precompute_calibration import (
    MEX_NORMALIZE_RULE_TEXT,
    MEX_NORMALIZE_THRESHOLD,
    market_needs_mex_normalization,
)


class TestMexNormalizationPredicate:
    def test_inflated_single_winner_partition_normalized(self):
        # 3+ outcomes, exactly one winner, sum well over 1 = the target class.
        assert market_needs_mex_normalization(4, 1, 3.09) is True
        assert market_needs_mex_normalization(3, 1, 1.16) is True

    def test_already_calibrated_sum_untouched(self):
        # A genuine mex market that already sums to ~1.0 needs no correction.
        assert market_needs_mex_normalization(5, 1, 1.0) is False
        assert market_needs_mex_normalization(5, 1, 1.15) is False  # at threshold

    def test_multi_winner_ladder_excluded(self):
        # 2+ winners = cumulative ladder / independent binaries mislabeled mex.
        # Their probabilities legitimately sum >1; normalizing would corrupt them.
        assert market_needs_mex_normalization(4, 2, 3.0) is False
        assert market_needs_mex_normalization(5, 3, 4.0) is False

    def test_zero_winner_void_excluded(self):
        # No winner = void / incomplete resolution; not a scoreable partition.
        assert market_needs_mex_normalization(4, 0, 3.0) is False

    def test_binary_and_small_markets_excluded(self):
        # Only >=3-outcome markets are the multi-candidate class; 2-outcome
        # binaries are handled by the malformed-binary filter, not here.
        assert market_needs_mex_normalization(2, 1, 1.9) is False
        assert market_needs_mex_normalization(1, 1, 2.0) is False

    def test_none_sum_is_safe(self):
        assert market_needs_mex_normalization(4, 1, None) is False

    def test_threshold_value(self):
        assert MEX_NORMALIZE_THRESHOLD == 1.15


class TestRuleText:
    def test_rule_describes_the_normalization(self):
        t = MEX_NORMALIZE_RULE_TEXT.lower()
        assert "mutually-exclusive" in t
        assert "one winner" in t
        assert "divided by" in t
        assert "never mutates" in t


class TestPrecomputeQueryEmbedsNormalization:
    def test_main_query_embeds_mex_normalization(self):
        src = (inspect.getsource(precompute_calibration.compute_calibration_payload)
               + precompute_calibration._calibration_population_ctes())
        # The support CTEs.
        assert "mex_win_counts" in src
        assert "mex_norm_markets" in src
        # Winner-count structure gate (genuine single-winner partition).
        assert "win_count = 1" in src
        # Applied as the divisor in the completeness-gated ``normalized`` CTE
        # (Queue #257 Item 1 moved the division out of ranked_outcomes so it can
        # be gated on field completeness).
        assert "ro.raw_cp / ro.mnm_cp_sum" in src
        assert "is_mex_normalized" in src
        # Queue #257 Item 1: normalization is gated on field completeness — a
        # partial field is excluded, never normalized over survivors.
        assert "field_completeness" in src
        assert "is_field_incomplete" in src
        # Transparency count + payload surface (candidate vs published split).
        assert "mex_normalized_outcomes" in src
        assert '"mex_normalization"' in src
        assert "candidate_markets" in src

    def test_normalization_is_read_side_only(self):
        # Guardrail (gotcha #21): normalization must never mutate resolutions.
        src = (inspect.getsource(precompute_calibration.compute_calibration_payload)
               + precompute_calibration._calibration_population_ctes())
        lowered = src.lower()
        assert "update futures_outcomes" not in lowered
        assert "update futures_markets" not in lowered
        assert "delete from futures_outcomes" not in lowered


class TestRouteFallbackDelegatesToSharedPath:
    def test_route_fallback_delegates_to_shared_payload(self):
        # Queue #257 Item 1: the cold-cache fallback delegates to the ONE shared
        # compute_calibration_payload, so it inherits the multi-candidate
        # normalization by construction — a cache miss can never be
        # over-confident on mex/field markets.
        from app.routes import calibration as calibration_route

        src = inspect.getsource(calibration_route.public_calibration)
        assert "compute_calibration_payload" in src


class TestFieldShapeGate254:
    """#254: the normalization gate must ALSO trust market_type='field', not only
    the mutually_exclusive flag — 65K field markets carry the flag unset yet are
    definitionally single-winner partitions summing ~4.56, and were polluting the
    curve raw. Both synced query sites must embed the extended gate."""

    def test_precompute_gate_includes_field_shape(self):
        src = (inspect.getsource(precompute_calibration.compute_calibration_payload)
               + precompute_calibration._calibration_population_ctes())
        assert "mi.market_type = 'field'" in src
        # market_info must expose market_type for the gate to reference it.
        assert "fm.market_type" in src

    def test_route_fallback_gate_includes_field_shape(self):
        # Queue #257 Item 1: the field-shape gate lives once in the shared
        # compute_calibration_payload; the route inherits it by delegating.
        from app.routes import calibration as calibration_route

        src = inspect.getsource(calibration_route.public_calibration)
        assert "compute_calibration_payload" in src

    def test_field_shape_still_guarded_by_single_winner_and_threshold(self):
        # The extension does NOT loosen the safety guards: a field that is
        # multi-winner or already ~1.0 is still left untouched by the predicate.
        assert market_needs_mex_normalization(80, 1, 4.56) is True   # the target class
        assert market_needs_mex_normalization(80, 2, 4.56) is False  # multi-winner field
        assert market_needs_mex_normalization(80, 1, 1.0) is False   # coherent field

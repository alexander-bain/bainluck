"""One canonical calibration-error definition (Fable addendum, CAL-P067).

Two jobs, and the second is the one that matters:

1. **Pin the reconciliation.** The canonical scorer must compute exactly what
   the frozen production implementation already computes, for both weightings
   and for the SQL's binning. A second implementation that provably agrees is
   not a second definition — it is the first one, written down. If this suite
   ever goes red, we have grown a genuine fork.

2. **Pin the contradiction that already exists.** Four published field names
   carry two quantities, and the names disagree with both textbook usage and
   each other. That is recorded as an assertion rather than a comment, so it
   cannot quietly grow a fifth name while the shape axis is being added.
"""

import pytest

from app.tasks.precompute_calibration import _compute_horizon_mce, _ece_from_buckets
from app.utils.calibration_ece import (
    CANONICAL_BINS,
    PRODUCTION_MIN_BIN_N,
    PUBLISHED_FIELD_DEFINITIONS,
    V3835_MIN_BIN_N,
    WEIGHTING_EQUAL,
    WEIGHTING_N,
    bin_index,
    calibration_error,
    ece,
    equal_weighted_error,
    floor_divergence,
    v3835_ece,
)

#: A cohort with a fat well-calibrated bulk and a thin badly-calibrated tail —
#: the r108 artifact shape, and the only shape where the parameters disagree.
BULK_AND_TAIL = [
    {"n": 10_000, "winners": 3_010, "sum_prob": 3_000.0},  # 30.1% vs 30.0% → 0.1pp
    {"n": 8_000, "winners": 5_600, "sum_prob": 5_600.0},   # exact
    {"n": 5, "winners": 5, "sum_prob": 1.0},               # 100% vs 20% → 80pp, n=5
]


# =============================================================================
# 1. The canonical scorer IS the production one
# =============================================================================


@pytest.mark.parametrize(
    "buckets",
    [
        BULK_AND_TAIL,
        [{"n": 100, "winners": 30, "sum_prob": 30.0}],
        [{"n": 1, "winners": 1, "sum_prob": 0.05}],
        [
            {"n": 500, "winners": 100, "sum_prob": 125.0},
            {"n": 250, "winners": 200, "sum_prob": 190.0},
            {"n": 0, "winners": 0, "sum_prob": 0.0},  # empty bin, must be ignored
        ],
    ],
)
def test_canonical_n_weighted_matches_the_frozen_production_implementation(buckets):
    assert ece(buckets) == _compute_horizon_mce(buckets, weighted=True)


@pytest.mark.parametrize("buckets", [BULK_AND_TAIL, [{"n": 7, "winners": 3, "sum_prob": 2.0}]])
def test_canonical_equal_weighted_matches_production(buckets):
    assert equal_weighted_error(buckets) == _compute_horizon_mce(buckets, weighted=False)


def test_canonical_equal_weighted_also_matches_the_OTHER_production_copy():
    """``_ece_from_buckets`` is a third implementation of the equal-weighted
    number over a different accumulator shape. It must agree too, or we have
    two equal-weighted definitions as well as two names for it."""
    as_dict = {i: b for i, b in enumerate(BULK_AND_TAIL)}
    assert equal_weighted_error(BULK_AND_TAIL) == _ece_from_buckets(as_dict)


def test_an_empty_cohort_is_none_everywhere_and_never_zero():
    """A perfect score standing in for no data is gotcha #53, and all three
    implementations must refuse it identically."""
    assert ece([]) is None
    assert equal_weighted_error([]) is None
    assert _compute_horizon_mce([], weighted=True) is None
    assert _ece_from_buckets({}) is None
    assert ece([{"n": 0, "winners": 0, "sum_prob": 0.0}]) is None


# =============================================================================
# The binning must match the SQL exactly
# =============================================================================


def test_bin_index_reproduces_the_builds_LEAST_FLOOR_expression():
    """The build computes ``LEAST(FLOOR(prob * 10)::int, 9)``. The LEAST is
    load-bearing: p=1.0 floors to 10, an eleventh bin in a ten-bin scheme."""
    assert CANONICAL_BINS == 10
    assert bin_index(0.0) == 0
    assert bin_index(0.09999) == 0
    assert bin_index(0.1) == 1
    assert bin_index(0.55) == 5
    assert bin_index(0.9) == 9
    assert bin_index(0.99999) == 9
    assert bin_index(1.0) == 9  # the LEAST clamp, not an 11th bin


def test_bin_index_clamps_below_zero_too():
    assert bin_index(-0.01) == 0


# =============================================================================
# 2. The only real methodological difference: the per-bin floor
# =============================================================================


def test_production_has_no_bin_floor_and_v3835_has_thirty():
    assert PRODUCTION_MIN_BIN_N == 0
    assert V3835_MIN_BIN_N == 30


def test_the_floor_is_the_one_knob_that_moves_a_number():
    """Same rows, same bins, same weighting — the floor alone changes the
    answer. Making that a value you pass is the whole reconciliation."""
    unfloored = ece(BULK_AND_TAIL)
    floored = v3835_ece(BULK_AND_TAIL)
    assert unfloored != floored
    assert floored == calibration_error(
        BULK_AND_TAIL, weighting=WEIGHTING_N, min_bin_n=V3835_MIN_BIN_N
    )


def test_the_floor_barely_moves_an_n_weighted_number_and_dominates_an_equal_one():
    """WHY the two surfaces can disagree loudly. Under n-weighting a 5-outcome
    bin is 0.03% of the weight, so dropping it is nearly a no-op. Under equal
    weighting it is a third of the answer. Same floor, same rows, opposite
    consequence — which is exactly why 'the MCE' must not name both."""
    n_delta = abs(ece(BULK_AND_TAIL) - v3835_ece(BULK_AND_TAIL))
    equal_delta = abs(
        equal_weighted_error(BULK_AND_TAIL)
        - calibration_error(
            BULK_AND_TAIL, weighting=WEIGHTING_EQUAL, min_bin_n=V3835_MIN_BIN_N
        )
    )
    assert n_delta < 0.1
    assert equal_delta > 20.0


def test_floor_divergence_attributes_the_gap_instead_of_leaving_it_arguable():
    d = floor_divergence(BULK_AND_TAIL)
    assert d["production_ece"] == ece(BULK_AND_TAIL)
    assert d["v3835_ece"] == v3835_ece(BULK_AND_TAIL)
    assert d["delta_pp"] == round(d["v3835_ece"] - d["production_ece"], 2)
    assert d["bins_dropped_by_floor"] == 1
    assert d["outcomes_dropped_by_floor"] == 5
    assert d["min_bin_n"] == 30


def test_a_cohort_entirely_under_the_floor_scores_none_not_zero():
    """v3835's floor applied to a thin shape cell must yield "cannot say",
    never a clean 0.0pp. A shape with only thin bins is the likeliest place for
    this to bite."""
    thin = [{"n": 5, "winners": 5, "sum_prob": 1.0}, {"n": 9, "winners": 0, "sum_prob": 8.0}]
    assert v3835_ece(thin) is None
    assert ece(thin) is not None


# =============================================================================
# 3. The naming collision, asserted so it cannot quietly grow
# =============================================================================


def test_four_published_names_carry_exactly_two_quantities():
    """Measured on the live payload 2026-08-17: ``ece == mce`` on every cell and
    ``mce_worst == mce_unweighted`` on every cell. Recorded as an assertion so
    adding the shape axis cannot multiply the ambiguity by seven shapes without
    someone seeing this fail."""
    assert len(PUBLISHED_FIELD_DEFINITIONS) == 4
    assert len(set(PUBLISHED_FIELD_DEFINITIONS.values())) == 2
    assert PUBLISHED_FIELD_DEFINITIONS["ece"] == PUBLISHED_FIELD_DEFINITIONS["mce"]
    assert (
        PUBLISHED_FIELD_DEFINITIONS["mce_worst"]
        == PUBLISHED_FIELD_DEFINITIONS["mce_unweighted"]
    )


def test_the_headline_is_n_weighted_and_the_worst_bucket_one_is_not():
    assert PUBLISHED_FIELD_DEFINITIONS["ece"][0] == WEIGHTING_N
    assert PUBLISHED_FIELD_DEFINITIONS["mce_worst"][0] == WEIGHTING_EQUAL


def test_the_published_pairs_reproduce_on_a_real_shaped_cohort():
    """End to end on one cohort: the two distinct numbers the API ships, from
    the canonical scorer, matching the frozen implementation for both."""
    headline = ece(BULK_AND_TAIL)
    worst = equal_weighted_error(BULK_AND_TAIL)
    assert headline != worst  # they are genuinely different statistics
    assert headline == _compute_horizon_mce(BULK_AND_TAIL, weighted=True)
    assert worst == _compute_horizon_mce(BULK_AND_TAIL, weighted=False)

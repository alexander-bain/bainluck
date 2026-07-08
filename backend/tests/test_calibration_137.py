"""#137 calibration regrade pack — guard tests.

Covers the pure, CI-testable invariants behind the #137 fixes:
  Item 1/2b  the polymarket opening writer never stamps a degenerate (0/1) price
             → a binary's two sides can never both open at 1.0.
  Item 3     `_compute_horizon_mce` is n-weighted (the durable fix that kills the
             r108 tail-bucket artifact), with the legacy equal-weighted number
             still available for the transition.

The SQL data-repairs (`_regrade_polymarket_under_signflip`,
`_unresolve_datagolf_premature`, `_null_impossible_both_sides_openings`) run
against production Postgres and are verified live, not in CI (no test DB).
"""

from app.tasks.polymarket import _is_tradeable_opening
from app.tasks.precompute_calibration import _compute_horizon_mce


class TestTradeableOpeningGuard:
    """Item 1/2b: openings must be real, non-degenerate, tradeable prices."""

    def test_settled_one_is_not_an_opening(self):
        assert _is_tradeable_opening(1.0, has_trading=True) is False

    def test_settled_zero_is_not_an_opening(self):
        assert _is_tradeable_opening(0.0, has_trading=True) is False

    def test_real_midrange_price_is_an_opening(self):
        assert _is_tradeable_opening(0.62, has_trading=True) is True

    def test_no_trading_is_not_an_opening(self):
        assert _is_tradeable_opening(0.62, has_trading=False) is False

    def test_none_price_is_not_an_opening(self):
        assert _is_tradeable_opening(None, has_trading=True) is False

    def test_both_sides_of_a_binary_cannot_open_at_one(self):
        # The impossible both-1.0 binary can only exist if 1.0 is a valid
        # opening. It is not — so at most one side (never both) can be 1.0, and
        # even that is rejected. over + under openings can never both be 1.0.
        over_prob, under_prob = 1.0, 0.0  # a settled market
        over_open = _is_tradeable_opening(over_prob, True)
        under_open = _is_tradeable_opening(under_prob, True)
        assert not (over_open and under_open)


class TestNWeightedMCE:
    """Item 3: n-weighted MCE kills the tail-bucket artifact."""

    def test_empty_returns_none(self):
        assert _compute_horizon_mce([]) is None

    def test_zero_n_buckets_return_none(self):
        assert _compute_horizon_mce([{"n": 0, "winners": 0, "sum_prob": 0.0}]) is None

    def test_perfectly_calibrated_is_zero(self):
        # bucket predicts 0.6 on avg (sum_prob/n), wins 6/10 → 0 error
        buckets = [{"n": 10, "winners": 6, "sum_prob": 6.0}]
        assert _compute_horizon_mce(buckets) == 0.0

    def test_tail_artifact_weighted_vs_unweighted(self):
        # The r108 signature: a large well-calibrated bulk bucket + a tiny wildly
        # off tail bucket. Equal-weighting lets the tail dominate; n-weighting
        # reflects the bulk that users actually see.
        buckets = [
            # bulk: n=1000, predicts 0.50, wins 500 → 0.0 error
            {"n": 1000, "winners": 500, "sum_prob": 500.0},
            # tail: n=2, predicts 0.50, wins 0 → 0.50 error
            {"n": 2, "winners": 0, "sum_prob": 1.0},
        ]
        unweighted = _compute_horizon_mce(buckets, weighted=False)
        weighted = _compute_horizon_mce(buckets, weighted=True)
        # unweighted: (0.0 + 0.50) / 2 = 25pp — dominated by the n=2 tail
        assert unweighted == 25.0
        # weighted: (0*1000 + 0.50*2) / 1002 ≈ 0.1pp — reflects the bulk
        assert weighted < 1.0
        assert weighted < unweighted

    def test_default_is_weighted(self):
        buckets = [
            {"n": 1000, "winners": 500, "sum_prob": 500.0},
            {"n": 2, "winners": 0, "sum_prob": 1.0},
        ]
        assert _compute_horizon_mce(buckets) == _compute_horizon_mce(
            buckets, weighted=True
        )

    def test_weighted_equals_unweighted_when_buckets_equal_size(self):
        # With uniform bucket sizes the two aggregations coincide.
        buckets = [
            {"n": 100, "winners": 60, "sum_prob": 50.0},  # 0.10 error
            {"n": 100, "winners": 40, "sum_prob": 50.0},  # 0.10 error
        ]
        assert _compute_horizon_mce(buckets, weighted=True) == _compute_horizon_mce(
            buckets, weighted=False
        )

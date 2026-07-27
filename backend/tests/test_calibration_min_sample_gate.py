"""#997 App Store ship-gate: the minimum-sample gate on /calibration.

A per-category / per-sport reliability chart below N resolved outcomes is
statistical noise (a handful of resolutions swings MCE by tens of points). The
gate is enforced server-side in the calibration precompute so web AND future
native both inherit the same bar, and the threshold is Redis-tunable at runtime.

Covers:
- _get_min_category_outcomes: Redis-tunable read, fail-safe defaults
- the payload ships the threshold + the transparency list of what was gated out
- the gate never silently disables on a malformed/negative key
"""

import inspect

from app.tasks import precompute_calibration
from app.tasks.precompute_calibration import (
    _DEFAULT_MIN_CATEGORY_OUTCOMES,
    _get_min_category_outcomes,
)


class _FakeRedis:
    def __init__(self, value):
        self._value = value

    def get(self, _key):
        return self._value


class TestMinCategoryOutcomesTunable:
    """The bar must be readable from Redis (no-deploy tuning) but fail SAFE:
    any miss/garbage falls back to the default so it can never open the
    thin-sample floodgates."""

    def test_default_when_no_redis(self):
        assert _get_min_category_outcomes(None) == _DEFAULT_MIN_CATEGORY_OUTCOMES

    def test_default_when_key_absent(self):
        assert _get_min_category_outcomes(_FakeRedis(None)) == _DEFAULT_MIN_CATEGORY_OUTCOMES

    def test_reads_tuned_value(self):
        assert _get_min_category_outcomes(_FakeRedis(b"500")) == 500
        assert _get_min_category_outcomes(_FakeRedis("2500")) == 2500

    def test_zero_disables_gate_explicitly(self):
        # 0 is a valid, deliberate "show everything" override (>= 0), distinct
        # from the fail-safe default path.
        assert _get_min_category_outcomes(_FakeRedis(b"0")) == 0

    def test_malformed_value_falls_back_to_default(self):
        assert _get_min_category_outcomes(_FakeRedis(b"not-an-int")) == _DEFAULT_MIN_CATEGORY_OUTCOMES

    def test_negative_value_falls_back_to_default(self):
        assert _get_min_category_outcomes(_FakeRedis(b"-1")) == _DEFAULT_MIN_CATEGORY_OUTCOMES

    def test_raising_redis_falls_back_to_default(self):
        class _Boom:
            def get(self, _key):
                raise RuntimeError("redis down")

        assert _get_min_category_outcomes(_Boom()) == _DEFAULT_MIN_CATEGORY_OUTCOMES


class TestDefaultBar:
    """Ship-gate bar starts at the 1000-outcome guardrail (queue #132 Item 2)."""

    def test_default_is_1000(self):
        assert _DEFAULT_MIN_CATEGORY_OUTCOMES == 1000


class TestPrecomputeGateWiring:
    """Guard that the precompute actually APPLIES the gate to the published
    sub-category lists and ships the bar in the payload — a gate that only
    lived on the frontend would not be inherited by native (the whole point)."""

    def _src(self):
        return inspect.getsource(precompute_calibration.compute_calibration_payload)

    def test_gate_applied_to_by_category(self):
        src = self._src()
        assert "_get_min_category_outcomes(" in src
        assert "_min_cat_outcomes" in src
        # by_category loop must skip sub-threshold categories
        assert "total_n < _min_cat_outcomes" in src

    def test_gate_applied_to_by_sport(self):
        src = self._src()
        assert "sn < _min_cat_outcomes" in src

    def test_payload_ships_threshold_and_transparency_list(self):
        src = self._src()
        assert '"min_category_outcomes": _min_cat_outcomes' in src
        assert '"small_sample_categories": small_sample_categories' in src

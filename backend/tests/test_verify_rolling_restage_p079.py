"""``evaluate()`` — the pure half of the rolling-restage verifier.

The instrument's whole job is to separate two things that look identical in a
single sample: a bank that ADVANCED, and a bank that was republished. So the
suite that matters here is not "does it pass on good data" — it is **does it
fail on the frozen bank**, which is the state that shipped to production and
sat undetected for 23 hours.

The negative control is real data: the 2026-08-20 pre-deploy reading, where the
curve served 200 with 1,935 coherent buckets the whole time and was nonetheless
completely frozen. Any verifier that grades that GREEN is re-manufacturing
#2007, and every check below is arranged so it cannot.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "verify_rolling_restage",
    Path(__file__).resolve().parent.parent / "scripts" / "verify_rolling_restage.py",
)
_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules["verify_rolling_restage"] = _MOD
_SPEC.loader.exec_module(_MOD)

evaluate = _MOD.evaluate


def _obs(**kw):
    base = {
        "http_status": 200,
        "bucket_count": 1935,
        "staged_at": "2026-08-19T17:16:31.866144+00:00",
        "units_drifted": 115,
        "rolling_restage": True,
        "rebuild_units_this_beat": 12,
        "tolerance_pp": 90.625,
    }
    base.update(kw)
    return base


#: The real pre-deploy production reading, twice — the frozen bank.
_FROZEN = [
    _obs(rolling_restage=None, rebuild_units_this_beat=None),
    _obs(rolling_restage=None, rebuild_units_this_beat=None),
]


class TestTheFrozenBankFails:
    def test_the_real_pre_deploy_reading_is_graded_fail(self):
        result = evaluate(_FROZEN)
        assert result["verdict"] == "fail"

    def test_it_fails_specifically_on_movement_not_on_serving(self):
        """The distinction the whole instrument exists for. A frozen bank serves
        a perfectly coherent curve; grading it on availability finds nothing."""
        checks = evaluate(_FROZEN)["checks"]
        assert checks["served_census_advanced"]["pass"] is False
        assert checks["drift_falling"]["pass"] is False
        # ...while the curve itself was genuinely fine, and says so.
        assert checks["served_200_and_coherent_throughout"]["pass"] is True

    def test_a_republished_but_unmoved_bank_still_fails(self):
        """The exact #2007 shape: the new code IS serving, the BUILDER is busy,
        and the served census has not moved. Two of five checks green, and the
        verdict must still be fail — this is why `bank_advanced_this_beat` is
        recorded but never graded."""
        obs = [
            _obs(bank_advanced_this_beat=True, rebuild_units_this_beat=16),
            _obs(bank_advanced_this_beat=True, rebuild_units_this_beat=16),
        ]
        result = evaluate(obs)
        assert result["checks"]["rolling_restage_present"]["pass"] is True
        assert result["checks"]["builder_alive"]["pass"] is True
        assert result["verdict"] == "fail"


class TestTheAdvancingBankPasses:
    def test_a_bank_that_moves_and_drains_passes(self):
        obs = [
            _obs(staged_at="2026-08-20T17:00:00+00:00", units_drifted=115,
                 tolerance_pp=90.625),
            _obs(staged_at="2026-08-20T17:15:00+00:00", units_drifted=64,
                 tolerance_pp=50.0),
            _obs(staged_at="2026-08-20T17:30:00+00:00", units_drifted=9,
                 tolerance_pp=7.03),
        ]
        result = evaluate(obs)
        assert result["verdict"] == "pass"
        assert result["checks"]["bound"]["first"] == pytest.approx(90.625)
        assert result["checks"]["bound"]["last"] == pytest.approx(7.03)

    def test_movement_alone_is_not_enough_drift_must_fall(self):
        """A bank that re-stages the same backlog forever is churn, not drain."""
        obs = [
            _obs(staged_at="2026-08-20T17:00:00+00:00", units_drifted=115),
            _obs(staged_at="2026-08-20T17:15:00+00:00", units_drifted=118),
        ]
        result = evaluate(obs)
        assert result["checks"]["served_census_advanced"]["pass"] is True
        assert result["checks"]["drift_falling"]["pass"] is False
        assert result["verdict"] == "fail"


class TestItRefusesToGuess:
    def test_one_sample_is_unmeasurable_not_a_pass(self):
        """Movement needs two readings. One sample must never grade — that is
        the single-observation blindness the instrument was built against."""
        result = evaluate([_obs()])
        assert result["verdict"] == "unmeasurable"
        assert result["checks"]["samples"]["pass"] is False

    def test_errored_samples_do_not_count_toward_movement(self):
        result = evaluate([_obs(), {"error": "URLError: nope"}])
        assert result["verdict"] == "unmeasurable"

    def test_a_non_200_anywhere_fails_the_serving_check(self):
        obs = [
            _obs(staged_at="2026-08-20T17:00:00+00:00", units_drifted=115),
            _obs(staged_at="2026-08-20T17:15:00+00:00", units_drifted=9,
                 http_status=503, bucket_count=0),
        ]
        result = evaluate(obs)
        assert result["checks"]["served_200_and_coherent_throughout"]["pass"] is False
        assert result["verdict"] == "fail"

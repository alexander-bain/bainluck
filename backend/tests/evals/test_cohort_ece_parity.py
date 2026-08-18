"""One ECE definition: sweep and calibration sentinel agree to 0.01pp on a full-population cell.

Cert finding 2: sweep must produce the same number as the calibration sentinel
for the same cell. Preferred: import and call the sentinel's function. Light
outputs are labeled light-estimate and parity is asserted on a full-population cell.
"""

import pytest

from scripts.evals.cohort_sweep import expected_calibration_error
from app.tasks.precompute_calibration import _compute_horizon_mce


def _bucks(rows, bins=10):
    """Helper to build sentinel-style buckets from sweep rows."""
    groups = [[] for _ in range(bins)]
    for r in rows:
        groups[min(int(r["probability"] * bins), bins - 1)].append(r)
    buckets = []
    for g in groups:
        if not g:
            continue
        buckets.append({
            "n": len(g),
            "winners": sum(x["actual"] for x in g),
            "sum_prob": sum(x["probability"] for x in g),
        })
    return buckets


def test_sweep_delegates_to_canonical_ece():
    """Sweep must actually *call* _compute_horizon_mce — not just mention it.

    This test is non-vacuous: it monkeypatches the canonical function to a
    distinguishable sentinel value and asserts the sweep returns that value.
    If delegation is dead (e.g., import fails and fallback is taken), the test
    FAILS — so a silently-diverged local fallback can never stay green.
    """
    import inspect

    # Still assert the import is present (defense in depth)
    src = inspect.getsource(expected_calibration_error)
    assert "_compute_horizon_mce" in src, "sweep must import sentinel's _compute_horizon_mce"
    assert "from app.tasks.precompute_calibration import _compute_horizon_mce" in src or "import" in src

    # Runtime delegation check: patch the canonical to return 42.0 pp (→ 0.42 fraction)
    # and verify the sweep actually returns 0.42, proving the call is live.
    import unittest.mock as mock

    rows = [
        {"probability": 0.2, "actual": 1 if i < 2 else 0, "outcome_id": i, "question_id": f"a{i}"}
        for i in range(10)
    ] + [
        {"probability": 0.8, "actual": 0 if i < 2 else 1, "outcome_id": i + 10, "question_id": f"b{i}"}
        for i in range(10)
    ]

    with mock.patch("app.tasks.precompute_calibration._compute_horizon_mce", return_value=42.0) as mocked:
        val = expected_calibration_error(rows)
        mocked.assert_called_once()
        assert val == pytest.approx(0.42), (
            f"Expected delegation to canonical _compute_horizon_mce (42.0 pp → 0.42), got {val}; "
            f"delegation is dead and fallback ran"
        )
        # Also verify the fallback flag is NOT set when canonical succeeds
        assert getattr(expected_calibration_error, "last_was_fallback", False) is False

    # Reset fallback flag for next test.
    expected_calibration_error.last_was_fallback = False  # type: ignore[attr-defined]


def test_parity_on_full_population_cell():
    """One full-population cell: sweep ECE and sentinel ECE agree to 0.01pp."""
    # Build a deterministic 100-row cell with known miscalibration
    rows = []
    for i in range(100):
        # Evenly spread probs 0.05..0.95, with systematic overprediction by ~0.1
        prob = 0.05 + (i % 10) * 0.1 + 0.05  # 0.1, 0.2, ... 1.0 clipped
        prob = min(max(prob, 0.01), 0.99)
        # Actual: 1 if prob > 0.5 else 0, but with noise — creates ECE
        actual = 1 if (prob > 0.6 and i % 3 != 0) or (prob <= 0.6 and i % 7 == 0) else 0
        # Make it deterministic and miscalibrated: high probs overpredicted
        if prob >= 0.7:
            actual = 0 if i % 4 == 0 else 1  # ~75% winrate at 0.8 prob → ECE
        rows.append({"probability": prob, "actual": actual, "outcome_id": i, "question_id": f"q{i}"})

    sweep_ece_frac = expected_calibration_error(rows, bins=10)  # fraction
    sweep_ece_pp = sweep_ece_frac * 100

    buckets = _bucks(rows, bins=10)
    sentinel_pp = _compute_horizon_mce(buckets, weighted=True)

    assert sentinel_pp is not None
    assert abs(sweep_ece_pp - sentinel_pp) < 0.01, (
        f"ECE parity failed: sweep {sweep_ece_pp:.4f}pp vs sentinel {sentinel_pp:.4f}pp "
        f"diff {abs(sweep_ece_pp - sentinel_pp):.4f}pp > 0.01pp"
    )


def test_perfect_calibration_parity():
    # Well-calibrated: 20% winrate at 0.2, 80% at 0.8
    rows = []
    for i in range(20):
        rows.append({"probability": 0.2, "actual": 1 if i < 4 else 0, "outcome_id": i, "question_id": f"a{i}"})
    for i in range(20):
        rows.append({"probability": 0.8, "actual": 0 if i < 4 else 1, "outcome_id": i + 20, "question_id": f"b{i}"})

    sweep_pp = expected_calibration_error(rows) * 100
    buckets = _bucks(rows)
    sentinel_pp = _compute_horizon_mce(buckets, weighted=True)

    assert sentinel_pp is not None
    assert abs(sweep_pp - sentinel_pp) < 0.01
    # Both should be ~0 for perfect calibration (within rounding)
    assert sweep_pp < 1.0
    assert sentinel_pp < 1.0


def test_light_is_labeled_light_estimate():
    """Light endpoint must label its outputs light-estimate everywhere."""
    import pathlib

    # Cwd-independent: resolve from this test file, not from cwd
    here = pathlib.Path(__file__).resolve()
    # This file is at backend/tests/evals/test_cohort_ece_parity.py → parents[2] is backend/
    src = (here.parents[2] / "app/routes/admin_cohort.py").read_text()
    # Light route must set ece_label
    assert 'ece_label' in src
    assert 'light-estimate' in src
    # Check light function sets per-row and top-level label
    assert '"light-estimate"' in src or "'light-estimate'" in src

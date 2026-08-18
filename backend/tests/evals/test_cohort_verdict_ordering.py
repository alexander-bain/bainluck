"""Verdict ordering: graded_share <50% wins before ≤5pp GREEN.

Cert finding 1: a cell with graded_share < 50% must NEVER render GREEN,
even if its ECE would otherwise pass. The selection-biased check runs FIRST.
"""

from scripts.evals.cohort_sweep import _verdict_for, analyze_cohort


def test_sub_threshold_cell_with_low_ece_is_not_green():
    # Sub-threshold graded_share that would be GREEN on ECE alone (2pp)
    ece = 2.0  # ≤5pp
    sufficient = True
    graded_share = 0.49  # <50% threshold

    verdict = _verdict_for(ece, sufficient, graded_share)

    assert verdict == "NOT-PROVABLE-selection-biased", (
        f"Expected NOT-PROVABLE-selection-biased for graded_share={graded_share}, ece={ece}, "
        f"but got {verdict!r} — selection-biased check must win before GREEN"
    )
    assert verdict != "GREEN"


def test_sub_threshold_cell_via_analyze_cohort():
    # Build a cohort that is well-calibrated (ECE ~0) but graded_share is 0.3.
    # For prob 0.2, 20% should win; for prob 0.8, 80% should win.
    rows = []
    for i in range(40):
        prob = 0.2 if i % 2 == 0 else 0.8
        # Well-calibrated: 20% of 0.2-prob win, 80% of 0.8-prob win
        # i%5==0 gives 20% winrate for 0.2 group (4/20), 80% for 0.8 group (16/20)
        if prob == 0.2:
            actual = 1 if i % 5 == 0 else 0  # 4 wins /20 = 20%
        else:
            actual = 0 if i % 5 == 0 else 1  # 16 wins /20 = 80%
        rows.append({
            "probability": prob,
            "actual": actual,
            "outcome_id": f"oid-{i}",
            "question_id": f"q-{i}",
            "source": "polymarket",
            "league_category": "test",
            "market_type": "quantity",
            "graded_share": 0.3,  # sub-threshold
            "total_n": 100,
            "graded_n": 30,
        })

    # Analyze — sufficient=True (40 independent questions), ECE ~0, but graded_share 0.3
    result = analyze_cohort(("polymarket", "test", "quantity"), rows)

    # Must be NOT-PROVABLE-selection-biased, never GREEN, even though ECE is ~0
    assert result["verdict"] == "NOT-PROVABLE-selection-biased"
    assert result["ece"] is not None and result["ece"] * 100 <= 5.0
    assert result["graded_share"] is not None and result["graded_share"] < 0.5


def test_threshold_boundary_is_not_biased():
    # Exactly 0.5 is NOT selection-biased — boundary is <0.5
    assert _verdict_for(2.0, True, 0.5) == "GREEN"
    assert _verdict_for(2.0, True, 0.5001) == "GREEN"
    assert _verdict_for(2.0, True, 0.4999) == "NOT-PROVABLE-selection-biased"


def test_high_ece_sub_threshold_is_still_selection_biased_not_red():
    # Even with high ECE, selection-biased wins — ordering is first
    assert _verdict_for(20.0, True, 0.1) == "NOT-PROVABLE-selection-biased"
    assert _verdict_for(20.0, True, 0.49) == "NOT-PROVABLE-selection-biased"

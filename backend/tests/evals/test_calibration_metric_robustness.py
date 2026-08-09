from scripts.evals.calibration_metric_robustness import (
    compare,
    equal_mass_ece,
    fixed_width_ece,
    report,
)


def rows(n=200, *, shift=0.0, clusters=100):
    result = []
    for i in range(n):
        truth = i % 2
        base = 0.8 if truth else 0.2
        p = min(0.999, max(0.001, base + (shift if truth else -shift)))
        result.append({"id": i, "question_id": f"q-{i % clusters}", "p": p, "y": truth})
    return result


def test_perfect_calibration_is_zero_under_both_binnings():
    perfect = [{"id": i, "question_id": i, "p": float(i % 2), "y": i % 2} for i in range(100)]
    assert fixed_width_ece(perfect, 10)[0] == 0
    assert equal_mass_ece(perfect, 10)[0] == 0


def test_report_discloses_rows_and_independent_clusters():
    result = report(rows(200, clusters=10))
    assert result["rows"] == 200
    assert result["question_clusters"] == 10
    assert result["rows_per_cluster"] == 20


def test_clear_improvement_survives_all_bin_choices_and_brier():
    before = rows(400, shift=-0.15, clusters=100)
    after = rows(400, shift=-0.02, clusters=100)
    result = compare(before, after)
    assert result["verdict"] == "ROBUST_IMPROVEMENT", result
    assert all(delta < -0.005 for delta in result["ece_deltas"])
    assert result["after"]["brier"] < result["before"]["brier"]


def test_tiny_change_is_not_called_improvement():
    result = compare(rows(400, shift=-0.02), rows(400, shift=-0.019))
    assert "PRACTICAL_IMPROVEMENT_NOT_ESTABLISHED" in result["reasons"]


def test_many_rows_from_few_questions_are_refused():
    result = compare(rows(10_000, shift=-0.15, clusters=5), rows(10_000, shift=-0.02, clusters=5))
    assert "TOO_FEW_QUESTION_CLUSTERS" in result["reasons"]


def test_sparse_bins_are_disclosed():
    result = report(rows(40), bin_counts=(20,), sparse_floor=30)
    assert result["sparse_bins"]["20"] > 0


def test_brier_blocks_ece_only_win():
    before = rows(400, shift=-0.15)
    after = rows(400, shift=-0.02)
    # Corrupt individual predictions while preserving broad bin averages.
    for i, row in enumerate(after):
        if i % 4 == 0:
            row["p"] = 0.99 if row["y"] == 0 else 0.01
    result = compare(before, after)
    assert "BRIER_DID_NOT_IMPROVE" in result["reasons"] or result["verdict"] == "REFUSE_CLAIM"

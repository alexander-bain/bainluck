import copy
import json
from pathlib import Path

from scripts.evals.paired_latency_experiment_contract import evaluate_pairs, percentile


FIXTURES = Path(__file__).parent / "fixtures" / "paired_latency_experiment_contract.json"


def pack():
    return json.loads(FIXTURES.read_text())


def clean_pairs(n=20):
    rows = []
    for i in range(n):
        row = copy.deepcopy(pack()["clean_pair_template"])
        row["order"] = "baseline_first" if i % 2 == 0 else "candidate_first"
        row["baseline_ms"] += i
        row["candidate_ms"] += i
        row["control_ms"] += i % 3
        rows.append(row)
    return rows


def test_clean_interleaved_experiment_is_comparable():
    result = evaluate_pairs(clean_pairs())
    assert result["verdict"] == "COMPARE"
    assert result["candidate_faster_pairs"] == 20
    assert result["candidate_p95_ms"] < result["baseline_p95_ms"]


def test_nearest_rank_p95_keeps_tail_observation():
    assert percentile(list(range(1, 21)), 0.95) == 19
    assert percentile([1, 2, 3, 30_000], 0.95) == 30_000


def test_timeout_is_counted_not_dropped():
    rows = clean_pairs()
    rows[-1]["candidate_failed"] = True
    result = evaluate_pairs(rows)
    assert result["candidate_p95_ms"] == 518
    assert result["failures_counted_as_ms"] == 30_000
    # p95 with 20 observations is rank 19; the timeout remains in the sample but
    # the max is not mislabeled p95. A second timeout crosses the p95 boundary.
    rows[-2]["candidate_failed"] = True
    assert evaluate_pairs(rows)["candidate_p95_ms"] == 30_000


def test_one_sided_order_is_refused():
    rows = clean_pairs()
    for row in rows:
        row["order"] = "baseline_first"
    assert "ORDER_NOT_INTERLEAVED" in evaluate_pairs(rows)["reasons"]


def test_control_drift_refuses_quiet_trough_comparison():
    rows = clean_pairs()
    for row in rows[10:]:
        row["control_ms"] = 500
    result = evaluate_pairs(rows)
    assert "CONTROL_DRIFT_EXCESSIVE" in result["reasons"]


def test_small_sample_is_refused():
    assert "PAIR_SAMPLE_TOO_SMALL" in evaluate_pairs(clean_pairs(5))["reasons"]


def test_each_fixture_adversary_bites():
    for case in pack()["adversaries"]:
        rows = clean_pairs()
        rows[0].update(case["set"])
        result = evaluate_pairs(rows)
        assert case["reason"] in result["reasons"], (case["id"], result)

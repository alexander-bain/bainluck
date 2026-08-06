from scripts.evals.debug_serving_drift_contract import evaluate_case, evaluate_corpus, load_corpus


def test_every_drifted_pair_has_exactly_one_fixture():
    corpus = load_corpus()
    drifted = {row["pair_id"] for row in corpus["audit_pairs"] if row["classification"] == "DRIFTED"}
    fixture_pairs = [row["pair_id"] for row in corpus["drift_fixtures"]]
    assert set(fixture_pairs) == drifted
    assert len(fixture_pairs) == len(set(fixture_pairs))


def test_committed_corpus_reproduces_every_divergence():
    report = evaluate_corpus(load_corpus())
    assert report["total"] == 7
    assert report["passed"] == report["total"], report["cases"]
    assert all(row["actual"]["diverged"] for row in report["cases"])


def test_every_fixture_names_paths_claim_reason_and_contract():
    for row in load_corpus()["drift_fixtures"]:
        assert row["diagnostic_path"]
        assert row["serving_path"]
        assert row["claimed_behavior"]
        assert row["expected_mismatch_reason"]
        assert row["shared_authority_contract"]


def test_stale_hook_and_score_adjustment_are_numerically_different():
    cases = {row["id"]: row for row in load_corpus()["drift_fixtures"]}
    for case_id in ("stale-hook-inflates-debug-score", "trace-final-omits-live-adjustments"):
        result = evaluate_case(cases[case_id])
        assert result["diagnostic_verdict"] != result["serving_verdict"]


def test_shared_and_debug_only_pairs_have_no_speculative_fixtures():
    corpus = load_corpus()
    fixture_pairs = {row["pair_id"] for row in corpus["drift_fixtures"]}
    for row in corpus["audit_pairs"]:
        if row["classification"] != "DRIFTED":
            assert row["pair_id"] not in fixture_pairs

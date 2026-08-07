from scripts.evals.espn_live_capture_continuity_contract import decide, evaluate, load, recovery


def _case(case_id):
    return next(row for row in load()["cases"] if row["id"] == case_id)


def test_committed_corpus_matches_oracle():
    report = evaluate(load())
    assert report["total"] == 28
    assert report["passed"] == report["total"], report["cases"]


def test_empty_slate_never_vouches_for_capture_health():
    assert decide(_case("empty-slate-unknown"))["verdict"] == "unknown"
    assert decide(_case("live-gated-zero-capture"))["verdict"] == "red"


def test_partial_and_poison_runs_preserve_siblings_but_stay_red():
    for case_id in ("partial-sport-failure", "poison-first-sibling-survival", "poison-middle-sibling-survival", "poison-last-sibling-survival"):
        case = _case(case_id)
        assert case["committed_games"] > 0
        assert decide(case)["verdict"] == "red"


def test_success_requires_commit_bound_complete_denominator():
    for case_id in ("commit-failure", "hard-timeout-before-commit", "overlapping-minute-beats", "metric-before-commit", "one-global-snapshot-hides-game-gap", "first-point-never-arrives"):
        assert decide(_case(case_id))["verdict"] == "red"


def test_recovery_requires_authoritative_history_and_identity():
    assert recovery(_case("recoverable-summary-history"))["verdict"] == "recoverable"
    for case_id in ("ambiguous-recovery-refusal", "wrong-link-recovery-refusal"):
        assert recovery(_case(case_id))["verdict"] == "refuse"

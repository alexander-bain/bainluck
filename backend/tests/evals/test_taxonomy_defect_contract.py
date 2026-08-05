from scripts.evals.taxonomy_defect_contract import census_decision, evaluate_corpus, load_corpus


def _case(case_id):
    return next(row for row in load_corpus()["cases"] if row["id"] == case_id)


def test_committed_corpus_matches_oracle():
    report = evaluate_corpus(load_corpus())
    assert report["total"] == 18
    assert report["passed"] == report["total"], report["cases"]


def test_sql_narrowing_cannot_hide_identity_or_invalid_defects():
    for case_id in (
        "invalid-out-of-vocab",
        "league-disagree-with-matching-sport",
        "category-disagree-with-matching-sport",
    ):
        assert census_decision(_case(case_id))["verdict"] == "red"


def test_ineligible_and_backfill_debt_decoys_do_not_alarm():
    for case_id in (
        "pure-backfill-debt",
        "probability-extreme-ineligible",
        "title-stale-ineligible",
        "resolved-ineligible",
        "expired-resolution-ineligible",
    ):
        assert census_decision(_case(case_id))["verdict"] == "green"


def test_incomplete_and_failed_censuses_fail_closed():
    assert census_decision(_case("incomplete-no-defects"))["verdict"] == "yellow"
    assert census_decision(_case("failed-census"))["verdict"] == "unknown"

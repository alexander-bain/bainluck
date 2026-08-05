from scripts.evals.live_probability_freshness_contract import evaluate_case, evaluate_corpus, load_corpus


def _case(case_id):
    return next(row for row in load_corpus()["cases"] if row["id"] == case_id)


def test_committed_corpus_matches_oracle():
    report = evaluate_corpus(load_corpus())
    assert report["total"] == 10
    assert report["passed"] == report["total"], report["cases"]


def test_stale_signal_is_withheld_not_replaced_by_half():
    assert evaluate_case(_case("started-game-17h-stale-99pct"))["display_probability"] is None
    assert evaluate_case(_case("stale-does-not-fallback-to-half"))["display_probability"] is None
    assert evaluate_case(_case("padres-degenerate-half-no-signal"))["display_probability"] is None


def test_quiet_but_current_live_signal_remains_visible():
    assert evaluate_case(_case("quiet-live-half-is-valid"))["display_probability"] == 0.5
    assert evaluate_case(_case("quiet-live-99-is-valid"))["display_probability"] == 0.99


def test_future_commence_can_never_be_live():
    result = evaluate_case(_case("future-game-17h-stale-99pct"))
    assert result["status_live"] is False
    assert result["reason_codes"] == ["future_commence_not_live"]

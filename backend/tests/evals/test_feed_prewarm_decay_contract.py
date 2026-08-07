from scripts.evals.feed_prewarm_decay_contract import evaluate_case, evaluate_corpus, load_corpus


def _case(case_id):
    return next(row for row in load_corpus()["cases"] if row["id"] == case_id)


def test_committed_corpus_matches_oracle():
    report = evaluate_corpus(load_corpus())
    assert report["total"] == 24
    assert report["passed"] == report["total"], report["cases"]


def test_only_exact_anonymous_first_paint_shapes_are_warmed():
    for case_id in ("discover-exact-warm", "discover-default-rewrite-warm", "sports-exact-warm"):
        assert evaluate_case(_case(case_id))["warmed"] is True
    for case_id in ("pagination-cold", "native-limit-50-cold", "session-first-page-cold", "authenticated-first-page-cold", "sport-filter-cold", "tag-filter-cold", "events-only-cold"):
        assert evaluate_case(_case(case_id))["warmed"] is False


def test_beat_death_outlives_both_redis_entries():
    for case_id in ("beat-dead-10m", "beat-dead-30m", "beat-dead-300m"):
        assert evaluate_case(_case(case_id))["visitor_state"] == "cold_build"


def test_last_good_is_currently_unbounded_and_opaque():
    result = evaluate_case(_case("redis-down-with-unbounded-last-good"))
    assert result == {"visitor_state": "last_good", "age_bounded": False, "age_disclosed": False}


def test_write_failures_abort_shape_isolation():
    for case_id in ("fresh-write-failure-aborts-loop", "stale-write-failure-aborts-loop"):
        result = evaluate_case(_case(case_id))
        assert result["outcome"] == "raises"
        assert result["second_shape_attempted"] is False

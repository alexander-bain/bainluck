from copy import deepcopy

from scripts.evals.feed_trust_contract import (
    CREDIBILITY_FIXTURES,
    SPEED_FIXTURES,
    evaluate,
    load_fixture,
    validate_credibility,
    validate_speed,
)


def test_credibility_corpus_is_versioned_and_scoped() -> None:
    corpus = load_fixture(CREDIBILITY_FIXTURES)
    assert corpus["schema_version"] == "feed-credibility/v1"
    assert corpus["audited_commit"] == "12aac732"
    assert "what may surface" in corpus["ownership"]


def test_credibility_scenarios_are_valid() -> None:
    corpus = load_fixture(CREDIBILITY_FIXTURES)
    result = evaluate(corpus, validate_credibility)
    assert len(result["accepted"]) == 10
    assert all(not errors for errors in result["accepted"].values()), result


def test_credibility_counterexamples_fail_exactly() -> None:
    corpus = load_fixture(CREDIBILITY_FIXTURES)
    for row in corpus["rejected_counterexamples"]:
        assert set(validate_credibility(row, corpus)) == set(row["expected_violations"])


def test_price_alone_never_settles() -> None:
    corpus = load_fixture(CREDIBILITY_FIXTURES)
    row = deepcopy(next(r for r in corpus["scenarios"] if r["id"] == "near_certain_but_open"))
    row["surface"] = False
    assert validate_credibility(row, corpus) == [
        "surfacing_decision_mismatch", "price_only_settlement"
    ]


def test_authoritative_resolution_always_suppresses() -> None:
    corpus = load_fixture(CREDIBILITY_FIXTURES)
    for row_id in ("date_past_taylor_equivalent", "authoritative_resolved", "linked_event_completed"):
        row = deepcopy(next(r for r in corpus["scenarios"] if r["id"] == row_id))
        row["surface"] = True
        assert validate_credibility(row, corpus) == ["surfacing_decision_mismatch"]


def test_speed_corpus_is_versioned_and_separate() -> None:
    corpus = load_fixture(SPEED_FIXTURES)
    assert corpus["schema_version"] == "feed-speed/v1"
    assert corpus["audited_commit"] == "12aac732"
    assert corpus["initial_page_limit_max"] == 20
    assert "request multiplicity" in corpus["ownership"]


def test_speed_scenarios_are_valid() -> None:
    corpus = load_fixture(SPEED_FIXTURES)
    result = evaluate(corpus, validate_speed)
    assert len(result["accepted"]) == 5
    assert all(not errors for errors in result["accepted"].values()), result


def test_speed_counterexamples_fail_exactly() -> None:
    corpus = load_fixture(SPEED_FIXTURES)
    for row in corpus["rejected_counterexamples"]:
        assert set(validate_speed(row, corpus)) == set(row["expected_violations"])


def test_overlapping_payload_is_clean_only_after_stable_id_dedup() -> None:
    corpus = load_fixture(SPEED_FIXTURES)
    row = deepcopy(next(r for r in corpus["scenarios"] if r["id"] == "overlap_deduped_by_stable_id"))
    row["rendered_ids"] = [item for page in row["page_ids"] for item in page]
    assert validate_speed(row, corpus) == ["duplicate_render_id"]

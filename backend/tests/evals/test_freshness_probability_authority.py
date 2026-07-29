from copy import deepcopy

from scripts.evals.freshness_probability_authority import (
    LIFECYCLE_FIXTURES,
    PROBABILITY_FIXTURES,
    evaluate,
    load_fixture,
    validate_lifecycle,
    validate_probability,
)


def test_lifecycle_corpus_is_versioned_and_rejects_non_authorities() -> None:
    corpus = load_fixture(LIFECYCLE_FIXTURES)
    assert corpus["schema_version"] == "real-world-lifecycle/v1"
    assert corpus["audited_commit"] == "e925284b"
    assert {"price", "title_inference", "model_knowledge"} <= set(corpus["non_authorities"])


def test_lifecycle_scenarios_are_valid() -> None:
    corpus = load_fixture(LIFECYCLE_FIXTURES)
    result = evaluate(corpus, validate_lifecycle)
    assert len(result["accepted"]) == 10
    assert all(not errors for errors in result["accepted"].values()), result


def test_lifecycle_counterexamples_fail_exactly() -> None:
    corpus = load_fixture(LIFECYCLE_FIXTURES)
    for row in corpus["rejected_counterexamples"]:
        assert set(validate_lifecycle(row, corpus)) == set(row["expected_violations"])


def test_current_authority_overrides_future_open_metadata() -> None:
    corpus = load_fixture(LIFECYCLE_FIXTURES)
    for row_id in (
        "future_open_authoritative_link_complete",
        "provider_settlement_future_metadata",
        "authoritative_winner_future_metadata",
    ):
        row = next(row for row in corpus["scenarios"] if row["id"] == row_id)
        assert row["suppress_live_prediction"]
        assert validate_lifecycle(row, corpus) == []


def test_reopen_invalidates_old_winner_authority() -> None:
    corpus = load_fixture(LIFECYCLE_FIXTURES)
    row = deepcopy(next(r for r in corpus["scenarios"] if r["id"] == "correction_reopens_previous_settlement"))
    row["declared_state"] = "settled"
    row["suppress_live_prediction"] = True
    assert validate_lifecycle(row, corpus) == [
        "completion_decision_mismatch", "reopen_retains_settled_state"
    ]


def test_probability_corpus_is_versioned_and_names_visible_surfaces() -> None:
    corpus = load_fixture(PROBABILITY_FIXTURES)
    assert corpus["schema_version"] == "card-probability-authority/v1"
    assert corpus["audited_commit"] == "e925284b"
    assert set(corpus["visible_probability_surfaces"]) == {
        "top_rows", "distribution_rows", "headline_rows", "context_rows"
    }


def test_probability_scenarios_are_valid() -> None:
    corpus = load_fixture(PROBABILITY_FIXTURES)
    result = evaluate(corpus, validate_probability)
    assert len(result["accepted"]) == 3
    assert all(not errors for errors in result["accepted"].values()), result


def test_probability_counterexamples_fail_exactly() -> None:
    corpus = load_fixture(PROBABILITY_FIXTURES)
    for row in corpus["rejected_counterexamples"]:
        assert set(validate_probability(row, corpus)) == set(row["expected_violations"])


def test_internal_raw_and_normalized_can_coexist_but_visible_cannot_mix() -> None:
    corpus = load_fixture(PROBABILITY_FIXTURES)
    row = deepcopy(next(r for r in corpus["scenarios"] if r["id"] == "independent_binary_normalized_basis"))
    row["distribution_rows"] = row["raw_outcomes"]
    assert validate_probability(row, corpus) == [
        "distribution_rows_authority_mismatch:A",
        "distribution_rows_authority_mismatch:B",
        "visible_probability_divergence:A",
        "visible_probability_divergence:B",
    ]

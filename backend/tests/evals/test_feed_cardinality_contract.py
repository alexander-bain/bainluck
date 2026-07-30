from copy import deepcopy

from scripts.evals.feed_cardinality_contract import (
    CARDINALITY_FIXTURES,
    CONCEPT_FIXTURES,
    load_fixture,
    validate_cardinality,
    validate_concept,
)


def test_corpora_are_versioned() -> None:
    cardinality = load_fixture(CARDINALITY_FIXTURES)
    concepts = load_fixture(CONCEPT_FIXTURES)
    assert cardinality["schema_version"] == "feed-cardinality-integrity/v1"
    assert concepts["schema_version"] == "concept-envelope-authority/v1"
    assert cardinality["audited_commit"] == concepts["audited_commit"] == "3df4ca19"


def test_cardinality_scenarios_are_coherent() -> None:
    corpus = load_fixture(CARDINALITY_FIXTURES)
    assert len(corpus["scenarios"]) == 8
    assert all(not validate_cardinality(row) for row in corpus["scenarios"])


def test_cardinality_counterexamples_fail_exactly() -> None:
    corpus = load_fixture(CARDINALITY_FIXTURES)
    for row in corpus["rejected_counterexamples"]:
        assert set(validate_cardinality(row)) == set(row["expected_violations"])


def test_limit_is_cache_identity_not_candidate_demand() -> None:
    corpus = load_fixture(CARDINALITY_FIXTURES)
    rows = {row["id"]: row for row in corpus["scenarios"]}
    for row_id in ("complete_limit_20", "complete_limit_60", "complete_limit_200_candidate_exhaustion"):
        row = rows[row_id]
        assert row["stage_counts"]["futures"] == 58
        assert row["total"] == 68
        assert row["cache_key_limit"] == row["limit"]


def test_degraded_precursor_pool_is_truthful_and_not_cached() -> None:
    corpus = load_fixture(CARDINALITY_FIXTURES)
    row = next(r for r in corpus["scenarios"] if r["id"] == "futures_timeout_returns_precursor_pool")
    assert row["returned"] == 22
    assert row["stage_counts"]["futures"] == 0
    assert row["build_quality"] == "degraded"
    assert not row["cache_fresh_written"] and not row["cache_stale_written"]


def test_concept_scenarios_are_coherent() -> None:
    corpus = load_fixture(CONCEPT_FIXTURES)
    assert len(corpus["scenarios"]) == 9
    assert all(not validate_concept(row) for row in corpus["scenarios"])


def test_probability_free_hub_is_not_an_empty_prediction() -> None:
    corpus = load_fixture(CONCEPT_FIXTURES)
    row = next(r for r in corpus["scenarios"] if r["id"] == "meaningful_probability_free_hub")
    assert not row.get("probabilities")
    assert row["expected"]["surface"] is True


def test_resolution_date_proxy_cannot_assert_live() -> None:
    corpus = load_fixture(CONCEPT_FIXTURES)
    row = deepcopy(next(r for r in corpus["scenarios"] if r["id"] == "resolution_date_only_is_not_start"))
    row["expected"]["live"] = True
    assert validate_concept(row) == ["live_authority_mismatch"]

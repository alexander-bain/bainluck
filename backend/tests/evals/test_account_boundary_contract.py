from copy import deepcopy

from scripts.evals.account_boundary_contract import (
    GOOGLE_FIXTURES,
    NATIVE_FIXTURES,
    evaluate,
    load_fixture,
    validate_google,
    validate_native,
)


def test_native_corpus_is_versioned_and_opaque() -> None:
    corpus = load_fixture(NATIVE_FIXTURES)
    assert corpus["schema_version"] == "native-account-isolation/v1"
    assert corpus["audited_commit"] == "e1eb40c2"
    assert set(corpus["opaque_identities"]) == {"anon", "user_a", "user_b"}


def test_native_scenarios_are_valid() -> None:
    corpus = load_fixture(NATIVE_FIXTURES)
    result = evaluate(corpus, validate_native)
    assert len(result["accepted"]) == 12
    assert all(not errors for errors in result["accepted"].values()), result


def test_native_counterexamples_fail_exactly() -> None:
    corpus = load_fixture(NATIVE_FIXTURES)
    for row in corpus["rejected_counterexamples"]:
        assert set(validate_native(row, corpus)) == set(row["expected_violations"])


def test_stale_generation_rejects_each_mutation_independently() -> None:
    corpus = load_fixture(NATIVE_FIXTURES)
    base = deepcopy(corpus["scenarios"][1])
    mapping = {
        "items_mutated": "stale_generation_items_mutation",
        "offset_mutated": "stale_generation_offset_mutation",
        "has_more_mutated": "stale_generation_has_more_mutation",
        "error_mutated": "stale_generation_error_mutation",
        "analytics_emitted": "stale_generation_analytics_mutation",
    }
    for field, violation in mapping.items():
        row = deepcopy(base)
        row[field] = True
        assert validate_native(row, corpus) == [violation]


def test_google_corpus_has_symbolic_server_authority() -> None:
    corpus = load_fixture(GOOGLE_FIXTURES)
    assert corpus["schema_version"] == "google-access-token-audience/v1"
    assert corpus["audited_commit"] == "e1eb40c2"
    assert set(corpus["configuration_authority"]["symbolic_allowed_client_ids"]) == {
        "web_client", "ios_client"
    }


def test_google_scenarios_are_valid() -> None:
    corpus = load_fixture(GOOGLE_FIXTURES)
    result = evaluate(corpus, validate_google)
    assert len(result["accepted"]) == 12
    assert all(not errors for errors in result["accepted"].values()), result


def test_google_counterexamples_fail_exactly() -> None:
    corpus = load_fixture(GOOGLE_FIXTURES)
    for row in corpus["rejected_counterexamples"]:
        assert set(validate_google(row, corpus)) == set(row["expected_violations"])


def test_every_google_rejection_is_side_effect_free() -> None:
    corpus = load_fixture(GOOGLE_FIXTURES)
    for row in corpus["scenarios"]:
        if not row["accepted"]:
            assert not any(row[name] for name in corpus["forbidden_rejection_side_effects"])


def test_allowlisted_admin_does_not_override_client_audience() -> None:
    corpus = load_fixture(GOOGLE_FIXTURES)
    row = deepcopy(next(r for r in corpus["scenarios"] if r["id"] == "wrong_audience_admin"))
    row["accepted"] = True
    assert validate_google(row, corpus) == ["acceptance_mismatch"]

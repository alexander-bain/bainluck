from copy import deepcopy

from scripts.evals.closure_boundary_contract import (
    GOLF_FIXTURES,
    NATIVE_FIXTURES,
    evaluate,
    load_fixture,
    validate_golf,
    validate_native,
)


def test_golf_corpus_contract_and_commit() -> None:
    corpus = load_fixture(GOLF_FIXTURES)
    assert corpus["schema_version"] == "golf-session-provenance/v1"
    assert corpus["audited_commit"].startswith("2b46d679")
    assert set(corpus["allowed_provenance"]) == {"fresh", "last_good", "inline", "unavailable"}


def test_required_golf_rows_are_valid() -> None:
    corpus = load_fixture(GOLF_FIXTURES)
    result = evaluate(corpus, validate_golf)
    assert len(result["accepted"]) == 12
    assert all(not errors for errors in result["accepted"].values()), result


def test_golf_counterexamples_fail_exactly_as_declared() -> None:
    corpus = load_fixture(GOLF_FIXTURES)
    for row in corpus["rejected_counterexamples"]:
        assert set(validate_golf(row, corpus)) == set(row["expected_violations"])


def test_cancelled_request_session_must_rollback_or_isolate() -> None:
    corpus = load_fixture(GOLF_FIXTURES)
    row = deepcopy(corpus["scenarios"][7])
    row["session_state"] = "statement_cancelled"
    assert validate_golf(row, corpus) == ["dirty_session_reused"]


def test_rollback_failure_cannot_continue_queries() -> None:
    corpus = load_fixture(GOLF_FIXTURES)
    row = deepcopy(corpus["scenarios"][10])
    row["later_queries"] = True
    assert validate_golf(row, corpus) == ["rollback_failure_reused"]


def test_every_golf_path_has_one_allowlisted_signal() -> None:
    corpus = load_fixture(GOLF_FIXTURES)
    for row in corpus["scenarios"]:
        assert row["observable"]
        assert row["signal_fields"] == ["provenance"]
        assert row["provenance"] in corpus["allowed_provenance"]


def test_native_corpus_contract_and_commit() -> None:
    corpus = load_fixture(NATIVE_FIXTURES)
    assert corpus["schema_version"] == "native-principal-render/v1"
    assert corpus["audited_commit"].startswith("7077eb40")
    assert set(corpus["opaque_identities"]) == {"anon", "user_a", "user_b"}


def test_required_native_rows_are_valid() -> None:
    corpus = load_fixture(NATIVE_FIXTURES)
    result = evaluate(corpus, validate_native)
    assert len(result["accepted"]) == 13
    assert all(not errors for errors in result["accepted"].values()), result


def test_native_counterexamples_fail_exactly_as_declared() -> None:
    corpus = load_fixture(NATIVE_FIXTURES)
    for row in corpus["rejected_counterexamples"]:
        assert set(validate_native(row, corpus)) == set(row["expected_violations"])


def test_boolean_only_a_to_b_is_rejected_for_display_and_store() -> None:
    corpus = load_fixture(NATIVE_FIXTURES)
    row = deepcopy(corpus["scenarios"][3])
    row["publish"] = True
    row["store"] = True
    assert validate_native(row, corpus) == ["cross_identity_publish", "cross_identity_store"]


def test_render_token_freezes_start_and_count_and_matches_ack() -> None:
    corpus = load_fixture(NATIVE_FIXTURES)
    row = deepcopy(corpus["scenarios"][8])
    row["ack_generation"] = row["render_token"]["generation"] - 1
    row["reads_live_count"] = True
    row["reads_mutable_start"] = True
    assert validate_native(row, corpus) == [
        "render_ack_generation_mismatch", "mutable_render_count", "mutable_render_start"
    ]


def test_retained_same_id_never_requires_onappear_refire() -> None:
    corpus = load_fixture(NATIVE_FIXTURES)
    row = deepcopy(corpus["scenarios"][8])
    row["ack_source"] = "business_row_id"
    row["requires_onappear_refire"] = True
    assert validate_native(row, corpus) == ["invalid_ack_source", "onappear_refire_assumption"]


def test_telemetry_fields_never_include_fixture_identity() -> None:
    corpus = load_fixture(NATIVE_FIXTURES)
    for row in corpus["scenarios"]:
        assert not (set(row["telemetry_fields"]) & set(corpus["opaque_identities"]))

from copy import deepcopy

from scripts.evals.degraded_cache_privacy_contract import (
    DEGRADED_FIXTURES,
    KID_FIXTURES,
    evaluate,
    load_fixture,
    validate_degraded,
    validate_kid,
)


def test_degraded_corpus_is_versioned_and_chooses_no_publication() -> None:
    corpus = load_fixture(DEGRADED_FIXTURES)
    assert corpus["schema_version"] == "degraded-feed-publication/v1"
    assert corpus["audited_commit"] == "fa15d6ab"
    assert "skip process last-good and both Redis publications" in corpus["mechanical_default"]


def test_degraded_scenarios_are_valid() -> None:
    corpus = load_fixture(DEGRADED_FIXTURES)
    result = evaluate(corpus, validate_degraded)
    assert len(result["accepted"]) == 7
    assert all(not errors for errors in result["accepted"].values()), result


def test_degraded_counterexamples_fail_exactly() -> None:
    corpus = load_fixture(DEGRADED_FIXTURES)
    for row in corpus["rejected_counterexamples"]:
        assert set(validate_degraded(row, corpus)) == set(row["expected_violations"])


def test_every_degraded_state_rebuilds_and_skips_durable_cache() -> None:
    corpus = load_fixture(DEGRADED_FIXTURES)
    for row in corpus["scenarios"]:
        if row["build_state"] in corpus["degraded_build_states"]:
            assert row["degraded_marker"]
            assert not row["process_last_good_written"]
            assert not row["redis_fresh_written"]
            assert not row["redis_stale_written"]
            assert row["next_same_key_action"] == "rebuild"


def test_kid_corpus_is_versioned_and_contains_only_synthetic_display_tokens() -> None:
    corpus = load_fixture(KID_FIXTURES)
    assert corpus["schema_version"] == "kid-session-privacy/v1"
    assert corpus["audited_commit"] == "fa15d6ab"
    assert all(
        row["display_token"].startswith(("display_", "legacy_"))
        for row in corpus["scenarios"] + corpus["rejected_counterexamples"]
    )


def test_kid_scenarios_are_valid() -> None:
    corpus = load_fixture(KID_FIXTURES)
    result = evaluate(corpus, validate_kid)
    assert len(result["accepted"]) == 8
    assert all(not errors for errors in result["accepted"].values()), result


def test_kid_counterexamples_fail_exactly() -> None:
    corpus = load_fixture(KID_FIXTURES)
    for row in corpus["rejected_counterexamples"]:
        assert set(validate_kid(row, corpus)) == set(row["expected_violations"])


def test_display_rename_cannot_rotate_device_identity() -> None:
    corpus = load_fixture(KID_FIXTURES)
    row = deepcopy(next(r for r in corpus["scenarios"] if r["id"] == "rename_same_device"))
    row["session_id"] = "kid_device:rotated_99"
    assert validate_kid(row, corpus) == ["session_stability_mismatch"]


def test_two_devices_with_same_display_never_share_identity() -> None:
    corpus = load_fixture(KID_FIXTURES)
    first = next(r for r in corpus["scenarios"] if r["id"] == "first_launch_device_a")
    second = deepcopy(next(r for r in corpus["scenarios"] if r["id"] == "same_display_device_b"))
    second["session_id"] = first["session_id"]
    second["expected_session_id"] = first["session_id"]
    assert validate_kid(second, corpus) == ["cross_device_collision"]

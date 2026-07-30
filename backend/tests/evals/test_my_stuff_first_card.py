from copy import deepcopy

from scripts.evals.my_stuff_first_card import (
    decide,
    load_corpus,
    validate_row,
    validate_telemetry,
)


def _row(row_id: str) -> dict:
    return next(row for row in load_corpus()["scenarios"] if row["id"] == row_id)


def _telemetry(**overrides) -> dict:
    packet = {
        "auth_ready_ms": 2.0,
        "network_ms": 80.0,
        "backend_elapsed_ms": 35.0,
        "decode_ms": 4.0,
        "required_data_ready_ms": 90.0,
        "first_render_ms": 110.0,
        "cache_outcome": "miss",
        "cache_age_seconds": -1,
        "item_count": 5,
        "app_build": "fixture",
        "surface": "my_stuff",
        "outcome_class": "network_success",
    }
    packet.update(overrides)
    return packet


def test_corpus_is_versioned_complete_and_valid() -> None:
    corpus = load_corpus()
    assert corpus["schema_version"] == "my-stuff-first-card/v1"
    assert corpus["audited_commit"] == "6614d20a"
    assert len(corpus["scenarios"]) == 14
    errors = {row["id"]: validate_row(row) for row in corpus["scenarios"]}
    assert all(not row_errors for row_errors in errors.values()), errors


def test_optional_futures_never_gate_required_first_card() -> None:
    for row_id in ("optional_futures_hung", "optional_futures_failure"):
        decision = decide(_row(row_id))
        assert decision["publish_required"]
        assert decision["first_card"]
        assert decision["outcome_class"] == "partial_success"


def test_identity_or_generation_change_rejects_late_publication() -> None:
    for row_id in ("account_a_to_b_late_response", "logout_late_response", "superseded_generation"):
        decision = decide(_row(row_id))
        assert not decision["publish_required"]
        assert not decision["first_card"]
        assert not decision["prior_account_visible"]


def test_cross_principal_cache_hit_is_rejected() -> None:
    decision = decide(_row("reject_cross_principal_memory_cache"))
    assert decision["outcome_class"] == "cache_principal_mismatch"
    assert not decision["publish_required"]


def test_empty_success_never_emits_first_card() -> None:
    decision = decide(_row("empty_success"))
    assert decision["publish_required"]
    assert not decision["first_card"]
    assert decision["loading_clears"]


def test_navigation_and_backoff_cancellation_are_quiet() -> None:
    for row_id in ("navigation_away_cancellation", "cancel_during_backoff"):
        decision = decide(_row(row_id))
        assert decision["outcome_class"] == "cancelled"
        assert decision["loading_clears"]
        assert not decision["first_card"]


def test_first_render_is_distinct_from_data_ready() -> None:
    corpus = load_corpus()
    packet = _telemetry(required_data_ready_ms=75.0, first_render_ms=130.0)
    assert validate_telemetry(packet, corpus) == []
    assert packet["first_render_ms"] > packet["required_data_ready_ms"]


def test_telemetry_requires_attribution_fields_and_no_pii() -> None:
    corpus = load_corpus()
    packet = _telemetry()
    del packet["backend_elapsed_ms"]
    packet["email"] = "not-allowed"
    assert set(validate_telemetry(packet, corpus)) == {
        "missing:backend_elapsed_ms", "pii_or_content_in_telemetry"
    }


def test_first_render_telemetry_requires_items() -> None:
    errors = validate_telemetry(_telemetry(item_count=0, first_render_ms=10.0), load_corpus())
    assert errors == ["first_render_without_items"]


def test_model_assignment_is_not_first_render() -> None:
    packet = _telemetry(first_render_ms=-1, item_count=5)
    assert validate_telemetry(packet, load_corpus()) == []


def test_principal_partition_is_required_even_when_generation_matches() -> None:
    row = deepcopy(_row("same_user_memory_cache"))
    row["cache_namespace"] = "user_b"
    decision = decide(row)
    assert decision["outcome_class"] == "cache_principal_mismatch"

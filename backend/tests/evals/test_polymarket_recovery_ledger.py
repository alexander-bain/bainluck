from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.polymarket_recovery_ledger import apply_case, load_ledger, validate_ledger

FIXTURE = Path(__file__).parents[2] / "scripts" / "evals" / "polymarket_recovery_fixtures.json"


@pytest.fixture(scope="module")
def fixture() -> dict:
    return load_ledger(FIXTURE)


def _codes(result: dict) -> set[str]:
    return {row["code"] for row in result["errors"]}


def test_clean_mixed_event_prop_ledger_closes(fixture: dict) -> None:
    result = validate_ledger(fixture["base"])
    assert result["errors"] == []
    assert result["closure_ready"] is True
    assert result["event_count"] == 1
    assert result["prop_count"] == 1
    assert result["event_state_counts"]["poly_main_recovered"] == 1


@pytest.mark.parametrize("case_index", range(20))
def test_adversarial_fixture_cases(fixture: dict, case_index: int) -> None:
    case = fixture["cases"][case_index]
    mutated = apply_case(fixture["base"], case)
    result = validate_ledger(mutated)
    expected = case["expected_code"]
    if expected is None:
        assert result["errors"] == [], case["id"]
        assert result["closure_ready"] is True
    else:
        assert expected in _codes(result), case["id"]
        assert result["closure_ready"] is False


def test_fixture_covers_every_c50_false_green_class(fixture: dict) -> None:
    ids = {case["id"] for case in fixture["cases"]}
    assert {
        "missing-surface",
        "terminal-zero-dropped",
        "prop-token-collision",
        "in-memory-skip",
        "permanent-tombstone",
        "opening-terminal",
        "transient-terminal",
        "duplicate-inflation",
        "prop-local-only",
        "threshold-silently-excluded",
    } <= ids


def test_duplicate_named_event_blocks_even_if_other_event_is_clean(fixture: dict) -> None:
    ledger = copy.deepcopy(fixture["base"])
    ledger["events"].append(copy.deepcopy(ledger["events"][0]))
    result = validate_ledger(ledger)
    assert "EVENT_DUPLICATE" in _codes(result)
    assert result["closure_ready"] is False


def test_one_unknown_named_event_cannot_hide_behind_high_completion(fixture: dict) -> None:
    ledger = copy.deepcopy(fixture["base"])
    for index in range(20):
        event = copy.deepcopy(ledger["events"][0])
        event["canonical_event_id"] = f"NBA:clean:{index}"
        ledger["events"].append(event)
    unknown = ledger["events"][-1]
    unknown["canonical_event_id"] = "MLB:unknown:G2"
    unknown["league"] = "MLB"
    unknown["game_number"] = 2
    unknown["main_state"] = "unknown"
    result = validate_ledger(ledger)
    assert result["event_state_counts"]["poly_main_recovered"] == 20
    assert result["event_state_counts"]["unknown"] == 1
    assert result["closure_ready"] is False


def test_prop_referential_integrity_and_duplicate_condition(fixture: dict) -> None:
    ledger = copy.deepcopy(fixture["base"])
    ledger["props"].append(copy.deepcopy(ledger["props"][0]))
    result = validate_ledger(ledger)
    assert "PROP_DUPLICATE" in _codes(result)


def test_record_versions_are_required(fixture: dict) -> None:
    ledger = copy.deepcopy(fixture["base"])
    ledger["events"][0]["record_version"] = 0
    ledger["props"][0].pop("record_version")
    errors = [row for row in validate_ledger(ledger)["errors"] if row["code"] == "RECORD_VERSION_INVALID"]
    assert len(errors) == 2


def test_explicit_ratified_trade_policy_can_classify_meaningful(fixture: dict) -> None:
    ledger = copy.deepcopy(fixture["base"])
    ledger["policy"]["meaningful_trade"] = {"version": "alex/v1", "threshold": {"min_trades": 2}}
    ledger["props"][0]["trade_classification"] = "meaningful"
    assert validate_ledger(ledger)["closure_ready"] is True


def test_unratified_policy_never_silently_excludes(fixture: dict) -> None:
    ledger = copy.deepcopy(fixture["base"])
    ledger["props"][0]["trade_classification"] = "not_meaningful"
    assert "TRADE_THRESHOLD_UNRATIFIED" in _codes(validate_ledger(ledger))


def test_retryable_failure_with_owned_next_attempt_is_not_tombstone(fixture: dict) -> None:
    ledger = copy.deepcopy(fixture["base"])
    ledger["events"][0]["retry"] = {
        "state": "failed",
        "reason": "alias mismatch",
        "input_fingerprint": "sha256:abc",
        "next_attempt_at": "2026-01-03T00:00:00Z",
    }
    assert "UNQUALIFIED_FAILURE_TOMBSTONE" not in _codes(validate_ledger(ledger))


def test_legitimate_nonlisting_requires_all_three_404s(fixture: dict) -> None:
    ledger = copy.deepcopy(fixture["base"])
    event = ledger["events"][0]
    event["main_state"] = "poly_nonlisting_archivally_proven"
    for attempt in event["attempts"]:
        attempt.update(result="not_found", http_status=404, terminal=True)
    result = validate_ledger(ledger)
    assert "NONLISTING_PROOF_INCOMPLETE" not in _codes(result)
    assert result["closure_ready"] is True


def test_deterministic_output(fixture: dict) -> None:
    ledger = copy.deepcopy(fixture["base"])
    ledger["events"][0]["main_state"] = "unknown"
    assert validate_ledger(ledger) == validate_ledger(copy.deepcopy(ledger))


def test_policy_is_input_not_hidden_constant(fixture: dict) -> None:
    ledger = copy.deepcopy(fixture["base"])
    ledger["policy"]["robustness"]["min_effective_points"] = 8
    assert "TIMELINE_TOO_SPARSE" in _codes(validate_ledger(ledger))


def test_fixture_is_synthetic_and_has_no_identity_fields(fixture: dict) -> None:
    text = json.dumps(fixture).lower()
    assert "email" not in text
    assert "phone" not in text
    assert "child" not in text

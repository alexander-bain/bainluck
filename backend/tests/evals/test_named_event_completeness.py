from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.evals.named_event_completeness import (
    merge_scoreboards,
    validate_scoreboard,
)

FIXTURE = (
    Path(__file__).parents[2]
    / "scripts"
    / "evals"
    / "named_event_completeness_fixtures.json"
)
POLY_FIXTURE = (
    Path(__file__).parents[2]
    / "scripts"
    / "evals"
    / "polymarket_recovery_fixtures.json"
)


@pytest.fixture(scope="module")
def base() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["base"]


def _codes(result: dict) -> set[str]:
    return {row["code"] for row in result["findings"]}


def test_clean_all_source_scoreboard_is_ready(base: dict) -> None:
    result = validate_scoreboard(base)
    assert result["closure_ready"] is True
    assert result["expected_count"] == 3
    assert result["complete_count"] == 3
    assert result["named_blockers"] == []
    assert result["failure_counts"] == {"UPSTREAM_ABSENCE": 1}
    assert all(not finding["blocking"] for finding in result["findings"])


def test_denominator_is_independent_of_observations(base: dict) -> None:
    value = copy.deepcopy(base)
    missing = value["observations"].pop()
    result = validate_scoreboard(value)
    assert result["expected_count"] == 3
    assert result["observed_count"] == 2
    assert missing["expected_event_id"] in result["named_blockers"]
    assert "MISSING_BAINLUCK_EVENT" in _codes(result)


def test_empty_inventory_never_infers_denominator_from_events(base: dict) -> None:
    value = copy.deepcopy(base)
    value["expected_events"] = []
    result = validate_scoreboard(value)
    assert result["expected_count"] == 0
    assert result["closure_ready"] is False
    assert "ABSENT_EXPECTED_INVENTORY" in _codes(result)
    assert "OBSERVATION_OUTSIDE_DENOMINATOR" in _codes(result)


@pytest.mark.parametrize(
    ("state", "code"),
    [
        ("missing", "MISSING_BAINLUCK_EVENT"),
        ("false_merge", "FALSE_MERGE"),
        ("missed_merge", "MISSED_MERGE"),
        ("ambiguous", "IDENTITY_AMBIGUITY"),
    ],
)
def test_identity_failure_classes_are_named(base: dict, state: str, code: str) -> None:
    value = copy.deepcopy(base)
    value["observations"][0]["identity"]["state"] = state
    result = validate_scoreboard(value)
    assert code in _codes(result)
    assert value["observations"][0]["expected_event_id"] in result["named_blockers"]


@pytest.mark.parametrize(
    "result", ["timeout", "rate_limited", "server_error", "parse_error"]
)
def test_errors_remain_retryable_and_cannot_be_terminal(
    base: dict, result: str
) -> None:
    value = copy.deepcopy(base)
    attempt = value["observations"][0]["sources"][0]["attempts"][0]
    attempt.update(result=result, terminal=True)
    validated = validate_scoreboard(value)
    assert "TRANSIENT_MARKED_TERMINAL" in _codes(validated)
    assert "NO_ROBUST_SOURCE" in _codes(validated)


def test_no_data_is_never_a_valid_substitute_for_error(base: dict) -> None:
    value = copy.deepcopy(base)
    value["observations"][0]["sources"][0]["attempts"][0]["result"] = "no_data"
    assert "ERROR_COLLAPSED_TO_NO_DATA" in _codes(validate_scoreboard(value))


def test_settlement_without_history_is_visible(base: dict) -> None:
    value = copy.deepcopy(base)
    history = value["observations"][0]["sources"][0]["history"]
    history.update(raw_points=0, effective_points=0, pregame_points=0, ingame_points=0)
    result = validate_scoreboard(value)
    assert "ZERO_SNAPSHOTS" in _codes(result)
    assert "NBA:2026-01-01:ALPHA:BETA:G1" in result["named_blockers"]


def test_history_without_linkage_is_visible(base: dict) -> None:
    value = copy.deepcopy(base)
    value["observations"][1]["identity"] = {
        "state": "missing",
        "bainluck_event_id": None,
    }
    result = validate_scoreboard(value)
    assert "MISSING_BAINLUCK_EVENT" in _codes(result)
    assert "MLB:2026-04-02:GAMMA:DELTA:G2" in result["named_blockers"]


def test_postponement_and_reschedule_identity_stays_one_expected_event(
    base: dict,
) -> None:
    value = copy.deepcopy(base)
    event = value["expected_events"][2]
    event["scheduled_at"] = "2026-02-04T19:00:00Z"
    event["inventory_attempts"].append(
        {
            "attempt_id": "inv-nhl-reschedule",
            "attempted_at": "2026-02-03T17:00:00Z",
            "request_identity": "NHL/reschedule/event-303",
            "result": "found",
            "terminal": True,
        }
    )
    result = validate_scoreboard(value)
    assert result["expected_count"] == 3
    assert "EXPECTED_EVENT_DUPLICATE" not in _codes(result)


def test_mlb_doubleheader_requires_game_number(base: dict) -> None:
    value = copy.deepcopy(base)
    value["expected_events"][1]["game_number"] = None
    assert "EXPECTED_PROVENANCE_INCOMPLETE" in _codes(validate_scoreboard(value))


def test_high_aggregate_rate_cannot_hide_one_named_gap(base: dict) -> None:
    value = copy.deepcopy(base)
    template_event = value["expected_events"][0]
    template_observation = value["observations"][0]
    for index in range(50):
        event = copy.deepcopy(template_event)
        observation = copy.deepcopy(template_observation)
        event_id = f"NBA:2026-01-{index + 2:02d}:TEAM{index}:OTHER{index}:G1"
        event["expected_event_id"] = event_id
        event["inventory_attempts"][0]["attempt_id"] = f"inventory-{index}"
        observation["expected_event_id"] = event_id
        observation["identity"]["bainluck_event_id"] = 1000 + index
        observation["sources"][0]["attempts"][0]["attempt_id"] = f"source-{index}"
        value["expected_events"].append(event)
        value["observations"].append(observation)
    value["observations"].pop()
    result = validate_scoreboard(value)
    assert result["complete_count"] == 52
    assert result["expected_count"] == 53
    assert result["closure_ready"] is False
    assert len(result["named_blockers"]) == 1


def test_rerun_merge_is_idempotent(base: dict) -> None:
    once = merge_scoreboards(base, base)
    twice = merge_scoreboards(once, base)
    assert once == twice
    assert validate_scoreboard(twice) == validate_scoreboard(once)


def test_rerun_preserves_prior_error_attempt(base: dict) -> None:
    previous = copy.deepcopy(base)
    old_attempt = previous["observations"][0]["sources"][0]["attempts"][0]
    old_attempt.update(attempt_id="espn-timeout", result="timeout", terminal=False)
    merged = merge_scoreboards(previous, base)
    nba = next(
        row
        for row in merged["observations"]
        if row["expected_event_id"].startswith("NBA:")
    )
    attempts = nba["sources"][0]["attempts"]
    assert {row["result"] for row in attempts} == {"timeout", "found"}


def test_duplicate_effective_history_is_a_blocker(base: dict) -> None:
    value = copy.deepcopy(base)
    value["observations"][0]["sources"][0]["history"].update(
        raw_points=3, effective_points=4
    )
    assert "NON_IDEMPOTENT_DUPLICATE_HISTORY" in _codes(validate_scoreboard(value))


def test_polymarket_validator_is_composed_not_reimplemented(base: dict) -> None:
    value = copy.deepcopy(base)
    value["polymarket_ledger"] = {
        "schema_version": "wrong",
        "policy": {},
        "events": [],
        "props": [],
    }
    result = validate_scoreboard(value)
    assert result["polymarket_result"] is not None
    assert any(code.startswith("POLYMARKET_") for code in _codes(result))
    assert result["closure_ready"] is False


def test_meaningful_trade_prop_fixture_composes_from_c51(base: dict) -> None:
    value = copy.deepcopy(base)
    value["polymarket_ledger"] = json.loads(POLY_FIXTURE.read_text(encoding="utf-8"))[
        "base"
    ]
    result = validate_scoreboard(value)
    assert result["polymarket_result"]["prop_count"] == 1
    assert result["polymarket_result"]["closure_ready"] is True
    assert result["closure_ready"] is True


def test_fixture_has_required_leagues_and_no_personal_data(base: dict) -> None:
    assert {row["league"] for row in base["expected_events"]} == {"NBA", "MLB", "NHL"}
    text = json.dumps(base).lower()
    assert "email" not in text
    assert "phone" not in text

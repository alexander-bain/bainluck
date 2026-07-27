import json
from pathlib import Path


FIXTURE_PATH = (
    Path(__file__).parents[2]
    / "scripts"
    / "evals"
    / "observability_blind_spots.json"
)


def _load():
    return json.loads(FIXTURE_PATH.read_text())


def test_blind_spot_contract_is_complete_and_detection_only():
    payload = _load()
    cases = payload["blind_spots"]
    assert payload["schema_version"] == 1
    assert len(cases) >= 9
    assert len({case["id"] for case in cases}) == len(cases)

    required = {
        "id",
        "severity",
        "owner",
        "synthetic_input",
        "current_result",
        "expected_result",
        "repo_evidence",
        "user_surface",
        "detection_only_fix",
        "kill_switch",
    }
    for case in cases:
        assert required <= case.keys()
        assert case["severity"] in {"P1", "P2", "P3"}
        assert case["owner"] in {"flow", "grid", "calibration"}
        assert case["expected_result"].startswith("RED") or "UNKNOWN" in case["expected_result"]
        assert "repair" not in case["detection_only_fix"].lower()
        assert case["kill_switch"]


def test_high_risk_false_green_shapes_are_pinned():
    cases = {case["id"]: case for case in _load()["blind_spots"]}
    expected = {
        "flow_upstream_read_failure_becomes_empty_green",
        "resolved_state_offender_outside_sample",
        "open_future_with_winner_or_resolved_marker",
        "resolved_to_open_resurrection",
        "title_implied_stale_hidden_by_feed_filter",
        "all_zero_open_market_hidden_by_feed_filter",
        "completed_duplicate_outside_flow_statuses",
        "native_concept_decode_contract_regression",
        "post_settlement_calibration_snapshot",
    }
    assert expected <= cases.keys()
    for case_id in expected:
        assert "GREEN" in cases[case_id]["current_result"]


def test_board_work_is_deduped_to_queue_265():
    payload = _load()
    assert all(case["owner"] != "board" for case in payload["blind_spots"])
    controls = {item["id"]: item for item in payload["covered_or_fixed_controls"]}
    assert controls["board_routing_truth"]["verdict"] == "in_flight_queue_265"


def test_fixed_and_explained_cases_are_not_reported_as_blind_spots():
    payload = _load()
    blind_ids = {case["id"] for case in payload["blind_spots"]}
    controls = {item["id"]: item for item in payload["covered_or_fixed_controls"]}
    assert "play_outcome_label_safety" not in blind_ids
    assert controls["play_outcome_label_safety"]["verdict"] == "fixed"
    assert controls["search_world_cup_top1"]["verdict"] == "covered"
    assert controls["grid_source_disagreement"]["verdict"] == "covered_as_watch_not_red"

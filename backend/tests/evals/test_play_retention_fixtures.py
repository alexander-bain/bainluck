import json
from pathlib import Path


FIXTURE_PATH = (
    Path(__file__).parents[2]
    / "scripts"
    / "evals"
    / "play_retention_fixtures.json"
)


def _load():
    return json.loads(FIXTURE_PATH.read_text())


def test_fixture_has_admission_boundary_coverage():
    payload = _load()
    scenarios = payload["scenarios"]
    ids = {scenario["id"] for scenario in scenarios}
    assert len(scenarios) >= 12
    assert {
        "completed_event",
        "past_open_future",
        "resolved_flag_on_open_future",
        "winner_on_open_future",
        "blocked_outcome_label",
        "settled_concept",
        "terminal_tournament",
        "unknown_card_type",
        "editorial_recall_no_bypass",
        "open_extreme_probability",
    } <= ids
    for scenario in scenarios:
        assert scenario["expected_eligible"] is (
            scenario["expected_safe"] and scenario["expected_fresh"]
        )
        assert scenario["visible_text"]


def test_blocked_outcome_is_in_the_safety_corpus():
    scenario = next(
        item for item in _load()["scenarios"] if item["id"] == "blocked_outcome_label"
    )
    assert any("pregnan" in text.lower() for text in scenario["visible_text"])
    assert scenario["expected_safe"] is False


def test_stale_and_result_first_cards_fail_closed():
    scenarios = {item["id"]: item for item in _load()["scenarios"]}
    for scenario_id in (
        "completed_event",
        "past_open_future",
        "resolved_flag_on_open_future",
        "winner_on_open_future",
        "settled_concept",
        "marquee_what_hit",
        "terminal_tournament",
    ):
        assert scenarios[scenario_id]["expected_fresh"] is False
        assert scenarios[scenario_id]["expected_eligible"] is False


def test_empty_states_are_explicitly_nonterminal_today():
    states = {item["id"]: item for item in _load()["empty_states"]}
    assert states["safe_page_events_only"]["has_more"] is True
    assert "forever" in states["safe_page_events_only"]["current_ui"]
    assert "retry" in states["feed_request_failed"]["expected_terminal_state"]

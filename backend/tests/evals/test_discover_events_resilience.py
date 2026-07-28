import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "evals" / "discover_events_resilience.py"
SPEC = importlib.util.spec_from_file_location("discover_events_resilience", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_all_resilience_fixtures_satisfy_contract():
    result = MODULE.evaluate()
    assert result["scenarios"] == 14
    assert result["passed"] == 14, result["failures"]
    assert result["failures"] == []


def test_fixture_inventory_covers_required_failures():
    fixtures = MODULE.load_fixtures()
    names = {fixture["name"] for fixture in fixtures}
    assert names == {
        "normal_multi_sport",
        "slow_odds_source",
        "hung_espn_date",
        "huge_bookmaker_payload",
        "duplicate_payload",
        "db_timeout_before_commit",
        "db_timeout_after_commit",
        "poison_event",
        "hard_kill_mid_unit",
        "hard_kill_between_units",
        "redis_marker_write_failure",
        "redis_marker_ahead_of_rollback",
        "sibling_source_survival",
        "piggyback_failure",
    }


def test_profiles_keep_ack_policy_explicit():
    for fixture in MODULE.load_fixtures():
        assert fixture["current_early_ack"]["redelivered"] is False
        assert fixture["proposed_late_ack"]["redelivered"] is True
        assert fixture["current_early_ack"]["marker_policy"] == "before_commit"
        assert fixture["proposed_late_ack"]["marker_policy"] == "after_commit"


def test_every_successful_unit_has_durable_marker_and_no_loss():
    for fixture in MODULE.load_fixtures():
        result = MODULE.simulate(fixture)
        assert result["cleanup_observed"] is True
        assert result["duplicate_count"] == 0
        assert result["deferred_cursor"] == []
        assert result["terminal_counters"]["committed_units"] == len(fixture["units"])
        assert set(result["redis_complete_sports"]) == set(fixture["input_order"])

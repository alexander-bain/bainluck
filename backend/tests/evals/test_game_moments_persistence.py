from copy import deepcopy
from pathlib import Path

from scripts.evals.game_moments_persistence import (
    evaluate_case,
    evaluate_pack,
    load_pack,
)

FIXTURES = (
    Path(__file__).parents[2] / "scripts/evals/game_moments_persistence_fixtures.json"
)


def pack():
    return load_pack(FIXTURES)


def row(result, case_id):
    return next(item for item in result["results"] if item["id"] == case_id)


def test_required_scenarios_present():
    ids = {case["id"] for case in pack()["cases"]}
    assert {
        "score-correction-readvance",
        "duplicate-source-play",
        "equal-prefix-40",
        "computed-empty-replacement",
        "fetch-failure-nonreplacement",
        "overlap-unserialized",
        "poison-then-healthy-sibling",
        "rollback-expired-orm",
        "task-cancellation",
    } <= ids


def test_clean_rerun_and_cross_event_scope_are_safe():
    result = evaluate_pack(pack())
    for case_id in (
        "clean-first-write",
        "identical-rerun",
        "same-key-different-events",
    ):
        assert row(result, case_id)["findings"] == []


def test_collision_cases_are_individually_named():
    result = evaluate_pack(pack())
    for case_id in (
        "score-correction-readvance",
        "duplicate-source-play",
        "equal-prefix-40",
    ):
        assert "DERIVED_IDENTITY_COLLISION" in row(result, case_id)["findings"]


def test_empty_is_authoritative_but_fetch_failure_preserves_rows():
    result = evaluate_pack(pack())
    assert row(result, "computed-empty-replacement")["terminal_state"] == "empty"
    assert row(result, "fetch-failure-nonreplacement")["findings"] == []


def test_stale_removal_and_insert_update_are_safe():
    result = evaluate_pack(pack())
    assert row(result, "stale-key-removal")["findings"] == []
    assert row(result, "insert-update")["findings"] == []


def test_unserialized_overlap_and_partial_visibility_fail():
    result = evaluate_pack(pack())
    assert "OVERLAP_UNSAFE" in row(result, "overlap-unserialized")["findings"]
    assert (
        "PARTIAL_REPLACEMENT_VISIBLE" in row(result, "retry-after-partial")["findings"]
    )


def test_poison_event_does_not_hide_sibling_abort():
    findings = row(evaluate_pack(pack()), "poison-then-healthy-sibling")["findings"]
    assert "FAILED_EVENT_ABORTED_SIBLING" in findings
    assert "DERIVED_IDENTITY_COLLISION" in findings


def test_rollback_expired_orm_access_is_named():
    findings = row(evaluate_pack(pack()), "rollback-expired-orm")["findings"]
    assert findings == ["ROLLBACK_EXPIRED_ORM_ACCESS"]


def test_missing_terminal_state_cannot_aggregate_away():
    case = deepcopy(pack()["cases"][0])
    case["observations"]["terminal_state"] = ""
    assert "MISSING_TERMINAL_STATE" in evaluate_case(case)["findings"]


def test_all_fixture_expectations_are_deterministic():
    result = evaluate_pack(pack())
    assert all(
        "EXPECTED_FINDINGS_MISMATCH" not in item["findings"]
        for item in result["results"]
    )

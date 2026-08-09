import json
from pathlib import Path

from scripts.evals.calibration_watchdog_evidence_contract import current_query_selection, select_evidence


FIXTURE = Path(__file__).parent / "fixtures" / "calibration_watchdog_evidence_contract.json"


def pack():
    return json.loads(FIXTURE.read_text())


def test_every_fixture_matches_the_oracle():
    for case in pack()["cases"]:
        assert select_evidence(case["payload"], case.get("limit", 10)) == case["expected"], case["id"]


def test_exact_cancelled_build_keeps_cursor_diagnostic():
    case = pack()["cases"][0]
    desired = select_evidence(case["payload"])["selected"]
    current = current_query_selection(case["payload"])
    assert "stage:staged:cursor_invalidate" in desired
    assert "stage:staged:cursor_invalidate" not in current
    assert sum(item.endswith(":pending") for item in current) == 4


def test_malformed_duration_does_not_erase_healthy_siblings():
    case = next(row for row in pack()["cases"] if row["id"] == "one-malformed-stage")
    assert current_query_selection(case["payload"]) == []
    result = select_evidence(case["payload"])
    assert "stage:read:futures_unit" in result["selected"]
    assert result["reasons"] == ["MALFORMED_STAGE_DURATION"]


def test_bounded_output_is_deterministic():
    case = pack()["cases"][0]
    forward = select_evidence(case["payload"], limit=4)
    case["payload"]["stages"] = dict(reversed(list(case["payload"]["stages"].items())))
    assert select_evidence(case["payload"], limit=4) == forward

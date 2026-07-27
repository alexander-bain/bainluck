import json
from pathlib import Path

import pytest

from app.utils.cross_source_matching import (
    _is_conservative_near_match,
    normalize_question,
)


FIXTURE_PATH = (
    Path(__file__).parents[2]
    / "scripts"
    / "evals"
    / "semantic_merge_fixtures.json"
)


@pytest.fixture(scope="module")
def cases():
    return json.loads(FIXTURE_PATH.read_text())["cases"]


def test_fixture_has_required_failure_coverage(cases):
    counts = {}
    for case in cases:
        counts[case["failure_class"]] = counts.get(case["failure_class"], 0) + 1
        assert case["expected_merge"] != case["current_merge"]
        assert case["evidence"].startswith("backend/")
        assert case["left"] and case["right"]

    assert counts["false_merge"] >= 5
    assert counts["missed_merge"] >= 5
    assert counts["unstable_id"] >= 3
    assert counts["source_semantic_loss"] >= 3


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Will the match finish 2-0?", "Will the match finish 20?"),
        ("Will CPI be 3.2%?", "Will CPI be 32%?"),
    ],
)
def test_exact_normalization_collision_is_reproduced(left, right):
    assert normalize_question(left) == normalize_question(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Fed cuts?", "Fed rate cut?"),
        (
            "Will US unemployment exceed 5 percent?",
            "Will United States unemployment be over 5 percent?",
        ),
    ],
)
def test_near_match_false_negative_is_reproduced(left, right):
    assert not _is_conservative_near_match(left, right)


def test_executable_cases_match_recorded_behavior(cases):
    executable = [case for case in cases if case.get("executable_check")]
    assert len(executable) == 4
    for case in executable:
        left = case["left"]["question"]
        right = case["right"]["question"]
        if case["executable_check"] == "normalize_question":
            observed = normalize_question(left) == normalize_question(right)
        else:
            observed = _is_conservative_near_match(left, right)
        assert observed is case["current_merge"]

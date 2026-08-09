import json
from pathlib import Path

from scripts.evals.golf_event_membership_contract import evaluate


FIXTURE = Path(__file__).parent / "fixtures" / "golf_event_membership_contract.json"


def pack():
    return json.loads(FIXTURE.read_text())


def test_every_fixture_matches_the_oracle():
    for case in pack()["cases"]:
        assert evaluate(case["input"]) == case["expected"], case["id"]


def test_named_foreign_examples_are_all_dropped():
    named = {"masters-chess", "masters-rodeo", "masters-pba", "masters-movie", "pga-lpga"}
    cases = {case["id"]: case for case in pack()["cases"]}
    assert named <= cases.keys()
    assert all(evaluate(cases[key]["input"])["verdict"] == "DROP" for key in named)


def test_grade_never_overrides_wrong_membership():
    for case in pack()["cases"]:
        if case["input"].get("graded_winner") and case["expected"]["verdict"] == "DROP":
            assert "GRADE_CANNOT_OVERRIDE_MEMBERSHIP" in evaluate(case["input"])["reasons"]


def test_legitimate_major_variants_survive():
    keep = [case for case in pack()["cases"] if case["expected"]["verdict"] == "KEEP"]
    assert {case["id"] for case in keep} >= {"masters-golfer", "pga-golfer", "womens-pga-golfer", "confirmed-fuzzy-sponsor-name"}

import json
from pathlib import Path

from scripts.evals.rendered_lifecycle_coverage_contract import evaluate


FIXTURE = Path(__file__).parent / "fixtures" / "rendered_lifecycle_coverage_contract.json"


def pack():
    return json.loads(FIXTURE.read_text())


def test_every_fixture_matches_the_oracle():
    for case in pack()["cases"]:
        result = evaluate(case["input"])
        assert result == case["expected"], case["id"]


def test_every_public_card_type_has_a_clean_join_case():
    clean_types = {case["input"]["rendered_type"] for case in pack()["cases"] if case["expected"]["verdict"] == "COUNT_FRESH"}
    assert clean_types == {"event", "futures", "concept", "tournament", "grid", "comparison", "bundle"}


def test_missing_authority_never_counts_fresh():
    for case in pack()["cases"]:
        result = evaluate(case["input"])
        if any(reason.endswith("MISSING") or reason.endswith("UNKNOWN") or "DRIFT" in reason or "MISMATCH" in reason for reason in result["reasons"]):
            assert result["verdict"] != "COUNT_FRESH", case["id"]


def test_known_stale_requires_complete_evidence():
    terminal = next(case for case in pack()["cases"] if case["id"] == "terminal-future")
    assert evaluate(terminal["input"])["verdict"] == "COUNT_STALE"

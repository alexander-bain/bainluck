import json
from pathlib import Path

from scripts.evals.admin_surface_truth_contract import (
    aggregate_headline,
    classification_tone,
    labeling_sufficiency,
    navigation_verdict,
)


FIXTURES = Path(__file__).parent / "fixtures" / "admin_surface_truth_contract.json"


def corpus():
    return json.loads(FIXTURES.read_text())


def test_headline_cases():
    for case in corpus()["headlines"]:
        assert aggregate_headline(case["children"]) == case["expected"], case["id"]


def test_classification_thresholds_are_ordered():
    for case in corpus()["classification"]:
        assert classification_tone(case["rate"]) == case["expected"]


def test_labeling_sufficiency_fails_closed():
    for case in corpus()["labeling"]:
        assert labeling_sufficiency(**case["input"]) == case["expected"]


def test_every_operational_page_must_be_linked():
    pages = {"/admin", "/admin/taxonomy", "/admin/team-clusters"}
    result = navigation_verdict(operational_pages=pages, linked_pages={"/admin", "/admin/taxonomy"})
    assert result == {"verdict": "REFUSE", "missing": ["/admin/team-clusters"]}


def test_complete_navigation_accepts():
    pages = {"/admin", "/admin/taxonomy", "/admin/team-clusters"}
    assert navigation_verdict(operational_pages=pages, linked_pages=pages) == {"verdict": "ACCEPT", "missing": []}

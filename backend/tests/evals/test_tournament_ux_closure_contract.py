from __future__ import annotations

import copy

from scripts.evals.tournament_ux_closure_contract import classify_surface, evaluate_case, evaluate_corpus, load_corpus


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus()["cases"] if row["id"] == case_id))


def test_committed_corpus_matches_oracles() -> None:
    report = evaluate_corpus(load_corpus())
    assert report["total"] == 23
    assert report["passed"] == report["total"], report["cases"]


def test_static_presence_never_proves_rendered_good() -> None:
    assert classify_surface(_case("generic-shell-static-only")) == "SHIPPED_PARTIAL"
    assert classify_surface(_case("generic-shell-rendered-good")) == "SHIPPED_GOOD"


def test_domain_fallback_and_native_gap_stay_open() -> None:
    assert classify_surface(_case("esports-concept-grouping")) == "SHIPPED_PARTIAL"
    assert classify_surface(_case("native-concept-destination")) == "UNSTARTED"


def test_parent_and_child_closure_require_rendered_evidence() -> None:
    assert evaluate_case(_case("poison-close-static-only")) == ["PREMATURE_CHILD_CLOSURE"]
    assert evaluate_case(_case("poison-parent-partial")) == ["PREMATURE_PARENT_CLOSURE"]


def test_promotion_waits_for_latency_or_explicit_release() -> None:
    assert evaluate_case(_case("promotion-latency-green")) == []
    assert evaluate_case(_case("promotion-latency-unknown")) == []
    assert evaluate_case(_case("promotion-alex-release")) == []

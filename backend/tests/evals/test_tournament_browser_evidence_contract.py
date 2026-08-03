from __future__ import annotations

import copy

from scripts.evals.tournament_browser_evidence_contract import classify, evaluate_corpus, load_corpus, refusal_codes


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus()["cases"] if row["id"] == case_id))


def test_committed_corpus_matches_oracle() -> None:
    report = evaluate_corpus(load_corpus())
    assert report["total"] == 24
    assert report["passed"] == report["total"], report["cases"]


def test_clean_serialized_run_is_the_only_green_shape() -> None:
    assert classify(_case("serialized-complete-pass")) == "SHIPPED_GOOD"
    assert refusal_codes(_case("cancelled-by-same-sha-pack")) == ["RUN_NOT_COMPLETE"]
    assert refusal_codes(_case("duplicate-generation-owner")) == ["EVIDENCE_OWNER_INVALID"]


def test_static_or_unknown_routes_cannot_close_a_child() -> None:
    assert classify(_case("generic-shell-static-only")) == "NOT_OBSERVABLE"
    assert refusal_codes(_case("dynamic-golf-route-unknown")) == ["ROUTE_NOT_OBSERVABLE"]


def test_trace_stays_outside_the_privacy_boundary() -> None:
    assert refusal_codes(_case("uncontained-trace-upload")) == ["UNCONTAINED_TRACE_ARTIFACT"]


def test_false_green_failure_shapes_are_named() -> None:
    assert refusal_codes(_case("skeleton-terminal")) == ["TERMINAL_NOT_REAL_CONTENT"]
    assert refusal_codes(_case("mixed-sha-run")) == ["SHA_MISMATCH"]
    assert refusal_codes(_case("zero-selected-tests")) == ["ZERO_JOURNEYS"]

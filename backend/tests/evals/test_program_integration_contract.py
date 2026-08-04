from __future__ import annotations

from scripts.evals.program_integration_contract import (
    evaluate_corpus,
    integration_decision,
    load_corpus,
    pilot_decision,
)


def _integration(case_id: str) -> dict:
    return next(row for row in load_corpus()["integration_cases"] if row["id"] == case_id)


def _pilot(case_id: str) -> dict:
    return next(row for row in load_corpus()["pilot_cases"] if row["id"] == case_id)


def test_committed_corpus_matches_oracles() -> None:
    report = evaluate_corpus(load_corpus())
    assert report["total"] == 38
    assert report["passed"] == report["total"], report["cases"]


def test_every_refusal_is_non_mutating() -> None:
    for case in load_corpus()["integration_cases"]:
        decision = integration_decision(case)
        if decision["verdict"] == "REFUSE":
            assert decision["mutate_master"] is False
            assert decision["reason_codes"]


def test_clean_cycle_is_only_allowed_integration() -> None:
    allowed = [
        case["id"]
        for case in load_corpus()["integration_cases"]
        if integration_decision(case)["verdict"] == "ALLOW"
    ]
    assert allowed == ["clean-cycle"]


def test_program_owner_never_acquires_push_authority() -> None:
    decision = integration_decision(_integration("direct-program-push"))
    assert decision["reason_codes"] == ["PUSH_AUTHORITY_VIOLATION"]
    assert decision["mutate_master"] is False


def test_partial_or_ambiguous_cycle_does_not_count() -> None:
    assert pilot_decision(_pilot("pilot-third-partial"))["valid_cycles"] == 2
    assert pilot_decision(_pilot("pilot-third-ambiguous"))["valid_cycles"] == 2


def test_three_cycles_still_require_explicit_verdict() -> None:
    assert pilot_decision(_pilot("pilot-three-no-ruling"))["verdict"] == "EXTEND_PILOT"
    assert pilot_decision(_pilot("pilot-three-clean"))["verdict"] == "MIGRATE_MORE_PROGRAMS"

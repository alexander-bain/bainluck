from __future__ import annotations

import copy

from scripts.evals.overtaken_premise_authority_contract import decide, evaluate_corpus, load_corpus, closure_status


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus()["cases"] if row["id"] == case_id))


def test_committed_corpus_matches_oracle() -> None:
    report = evaluate_corpus(load_corpus())
    assert report["total"] == 26
    assert report["passed"] == report["total"], report["cases"]


def test_source_open_and_future_date_do_not_override_completed_premise() -> None:
    assert decide(_case("completed-premise-source-still-open")) == ("overtaken", [])


def test_prose_and_advisory_inputs_never_suppress() -> None:
    for case_id in ("title-only-poison", "llm-only-poison", "news-only-poison", "user-report-only-poison", "curator-row-only-poison"):
        assert decide(_case(case_id)) == ("review", ["NO_AUTHORITATIVE_PREMISE_EVIDENCE"])


def test_identity_and_contradictions_fail_closed_to_review() -> None:
    assert decide(_case("wrong-wedding-premise"))[0] == "review"
    assert decide(_case("authoritative-contradiction")) == ("review", ["AUTHORITATIVE_CONTRADICTION"])


def test_propagation_requires_every_owned_surface_and_controls() -> None:
    assert decide(_case("partial-surface-propagation")) == ("review", ["SURFACE_PROPAGATION_INCOMPLETE"])
    assert decide(_case("unrelated-taylor-negative-control")) == ("include", [])


def test_rendered_closure_is_stricter_than_static_action() -> None:
    row = _case("rendered-closure-pass")
    action, refusals = decide(row)
    assert closure_status(row, action, refusals) == "SHIPPED_GOOD"
    row = _case("api-only-premature-closure")
    action, refusals = decide(row)
    assert closure_status(row, action, refusals) == "NOT_OBSERVABLE"

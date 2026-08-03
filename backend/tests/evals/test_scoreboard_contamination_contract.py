from __future__ import annotations

import copy

from scripts.evals.scoreboard_contamination_contract import classify, evaluate_corpus, load_corpus, refusal_codes


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus()["cases"] if row["id"] == case_id))


def test_committed_corpus_matches_oracle() -> None:
    report = evaluate_corpus(load_corpus())
    assert report["total"] == 28
    assert report["passed"] == report["total"], report["cases"]


def test_group_id_alone_cannot_authorize_contamination() -> None:
    assert refusal_codes(_case("women-draw-men-poison")) == ["CROSS_GENDER_MEMBER"]
    assert refusal_codes(_case("nfl-halftime-poison")) == ["CROSS_DOMAIN_MEMBER", "CROSS_EVENT_MEMBER"]
    assert refusal_codes(_case("incompatible-group-id-collision")) == ["CROSS_COMPETITION_MEMBER", "CROSS_EVENT_MEMBER"]


def test_visible_leader_is_derived_after_structural_filtering() -> None:
    assert refusal_codes(_case("mixed-binary-parent-leader-poison")) == ["VISIBLE_LEADER_WRONG"]
    assert refusal_codes(_case("authoritative-leader-omitted")) == ["AUTHORITATIVE_LEADER_MISSING"]


def test_parser_failure_never_becomes_a_zero_ladder() -> None:
    assert refusal_codes(_case("exact-score-default-zero-poison")) == ["COLLAPSED_THRESHOLD_LABEL", "DUPLICATE_THRESHOLD_VALUE", "THRESHOLD_OPERATOR_INVALID", "UNPARSED_THRESHOLD"]


def test_poison_position_preserves_clean_sibling() -> None:
    for case_id in ("poison-first", "poison-middle", "poison-last"):
        assert refusal_codes(_case(case_id)) == []


def test_only_deployed_rendered_evidence_closes() -> None:
    assert classify(_case("rendered-corrected-pass")) == "SHIPPED_GOOD"
    assert refusal_codes(_case("api-only-premature-closure")) == ["RENDERED_CLOSURE_EVIDENCE_MISSING"]

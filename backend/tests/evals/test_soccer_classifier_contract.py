from __future__ import annotations

import copy

from app.utils.game_market_class import classify_game_market_class
from scripts.evals.soccer_classifier_contract import (
    audit_classifier,
    evaluate_case,
    evaluate_corpus,
    load_corpus,
)


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus()["cases"] if row["id"] == case_id))


def test_committed_contract_corpus_matches_oracles() -> None:
    report = evaluate_corpus(load_corpus())
    assert report["total"] == 26
    assert report["passed"] == report["total"], report["cases"]


def test_current_classifier_mismatch_set_is_frozen() -> None:
    corpus = load_corpus()
    actual = [row["id"] for row in audit_classifier(corpus, classify_game_market_class)]
    assert actual == corpus["expected_current_mismatch_ids"]


def test_three_way_draw_and_cross_event_poison_refuse() -> None:
    assert evaluate_case(_case("poison-draw-dropped")) == ["SOCCER_DRAW_CONTRACT_LOST"]
    assert evaluate_case(_case("poison-cross-event")) == ["CROSS_EVENT_IDENTITY_ALLOWED"]


def test_period_winners_never_become_whole_game_moneylines() -> None:
    row = _case("esports-map-two-winner")
    row["expected_class"] = "moneyline"
    assert evaluate_case(row) == ["EXPECTED_CLASS_DRIFT"]


def test_player_outcomes_override_matchup_looking_container() -> None:
    row = _case("soccer-player-container")
    row["expected_class"] = "moneyline"
    assert evaluate_case(row) == ["EXPECTED_CLASS_DRIFT", "PLAYER_CONTAINER_BECAME_WINNER"]

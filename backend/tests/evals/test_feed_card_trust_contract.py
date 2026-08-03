from __future__ import annotations

import copy

from scripts.evals.feed_card_trust_contract import evaluate_case, evaluate_corpus, load_corpus


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus()["cases"] if row["id"] == case_id))


def test_committed_corpus_matches_oracles() -> None:
    report = evaluate_corpus(load_corpus())
    assert report["total"] == 23
    assert report["passed"] == report["total"], report["cases"]


def test_price_and_title_alone_never_settle() -> None:
    assert evaluate_case(_case("poison-title-only-hidden")) == ["LIFECYCLE_ACTION_WRONG", "TITLE_ONLY_SUPPRESSION"]
    assert evaluate_case(_case("poison-price-only-hidden")) == ["LIFECYCLE_ACTION_WRONG", "PRICE_ONLY_SUPPRESSION"]


def test_cross_market_and_missing_leader_refuse() -> None:
    assert evaluate_case(_case("poison-sinner-cross-market")) == ["CROSS_MARKET_OUTCOME"]
    assert evaluate_case(_case("poison-grammy-leader-omitted")) == ["ACTUAL_LEADER_MISSING"]


def test_incomplete_sets_and_ladders_are_not_repaired_by_invention() -> None:
    assert evaluate_case(_case("poison-fed-incomplete-normalized")) == ["INCOMPLETE_SET_NORMALIZED"]
    assert evaluate_case(_case("poison-cpi-contradictory")) == ["LADDER_MONOTONICITY_BROKEN"]


def test_bad_build_and_poison_sibling_preserve_good_truth() -> None:
    assert evaluate_case(_case("poison-partial-replaces-last-good")) == ["BAD_BUILD_REPLACED_LAST_GOOD"]
    assert evaluate_case(_case("poison-sibling-erases-clean")) == ["POISON_SIBLING_ERASED_CLEAN_CARD"]

from __future__ import annotations

import copy

from scripts.evals.first_card_client_contract import (
    evaluate_case,
    evaluate_corpus,
    load_corpus,
)


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus()["cases"] if row["id"] == case_id))


def test_committed_corpus_matches_all_oracles() -> None:
    report = evaluate_corpus(load_corpus())
    assert report["total"] == 24
    assert report["passed"] == report["total"], report["cases"]


def test_budget_authority_does_not_invent_foreground_timeout() -> None:
    authority = load_corpus()["budget_authority"]
    assert authority["first_real_card_target_ms"] == 3000
    assert authority["foreground_failure_terminal_ms"] == "APPROVED_PRODUCT_INPUT_REQUIRED"
    assert evaluate_case(_case("missing-approved-foreground-budget")) == [
        "FOREGROUND_BUDGET_NEEDS_APPROVAL"
    ]


def test_public_feed_starts_before_auth_and_guards_principal_races() -> None:
    assert evaluate_case(_case("signed-out-slow-auth-starts-public")) == []
    assert evaluate_case(_case("wedged-auth-never-blocks-public")) == []
    assert evaluate_case(_case("current-auth-gated-sports")) == [
        "AUTH_BLOCKS_PUBLIC_REQUEST"
    ]
    assert evaluate_case(_case("late-anonymous-overwrites-authenticated")) == [
        "STALE_PRINCIPAL_OVERWRITE"
    ]


def test_only_mounted_stable_real_card_counts() -> None:
    assert evaluate_case(_case("skeleton-is-not-card")) == [
        "NON_CARD_COUNTED_AS_FIRST_CARD"
    ]
    assert evaluate_case(_case("error-is-not-card")) == [
        "NON_CARD_COUNTED_AS_FIRST_CARD"
    ]
    assert evaluate_case(_case("named-empty-is-not-card")) == []


def test_pagination_preserves_identity_order_and_prior_pages() -> None:
    assert evaluate_case(_case("first-page-equivalence-and-complete-pagination")) == []
    assert "FIRST_PAGE_IDENTITY_OR_ORDER_DRIFT" in evaluate_case(
        _case("first-page-order-drift")
    )
    assert evaluate_case(_case("nonmonotonic-offset")) == [
        "PAGINATION_OFFSET_NON_MONOTONIC"
    ]
    assert evaluate_case(_case("premature-exhaustion-truncates")) == [
        "PREMATURE_EXHAUSTION"
    ]
    assert evaluate_case(_case("late-page-failure-preserves-cards")) == []


def test_failure_terminal_does_not_let_retries_own_foreground() -> None:
    assert evaluate_case(_case("current-three-attempt-skeleton-retention")) == [
        "RETRIES_HOLD_SKELETON"
    ]
    assert evaluate_case(_case("short-terminal-background-retry")) == []
    assert evaluate_case(_case("unavailable-preserves-last-good")) == []
    assert evaluate_case(_case("failure-clears-last-good")) == [
        "FAILURE_CLEARED_LAST_GOOD"
    ]
    assert evaluate_case(_case("retry-recovery-replaces-terminal")) == []


def test_product_semantics_are_frozen() -> None:
    assert evaluate_case(_case("product-semantics-drift-refused")) == [
        "PRODUCT_SEMANTICS_DRIFT"
    ]

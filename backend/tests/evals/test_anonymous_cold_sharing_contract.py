from __future__ import annotations

import copy

from scripts.evals.anonymous_cold_sharing_contract import (
    evaluate_case,
    evaluate_corpus,
    load_corpus,
)


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus()["cases"] if row["id"] == case_id))


def test_committed_corpus_matches_all_oracles() -> None:
    report = evaluate_corpus(load_corpus())
    assert report["total"] == 27
    assert report["passed"] == report["total"], report["cases"]


def test_shareability_matrix_keeps_response_principal_scoped() -> None:
    matrix = {row["artifact"]: row for row in load_corpus()["shareability_matrix"]}
    assert matrix["candidate_base"]["authenticated"] == "candidate_only"
    assert matrix["response_payload"]["fresh_session_zero_interactions"] == "never_cross_session"
    assert evaluate_case(_case("new-session-cannot-byte-share-response")) == [
        "CROSS_PRINCIPAL_RESPONSE"
    ]


def test_shared_intermediate_must_reapply_interactions() -> None:
    assert evaluate_case(_case("interacted-session-reapplies-seen-dismissed")) == []
    assert evaluate_case(_case("interaction-arrives-but-filters-not-reapplied")) == [
        "REQUEST_FILTERS_NOT_REAPPLIED",
        "RESPONSE_IDENTITY_OR_ORDER_DRIFT",
        "SEEN_OR_DISMISSED_CARD_RESURRECTED",
    ]
    assert evaluate_case(_case("unknown-interaction-authority-fails-closed")) == [
        "INTERACTION_AUTHORITY_UNKNOWN",
        "REQUEST_FILTERS_NOT_REAPPLIED",
    ]


def test_mode_shape_and_generation_never_cross() -> None:
    assert evaluate_case(_case("discover-sports-base-separated")) == [
        "WRONG_SHARED_BASE_IDENTITY"
    ]
    assert evaluate_case(_case("response-wrong-offset")) == ["WRONG_RESPONSE_SHAPE"]
    assert evaluate_case(_case("mixed-deploy-generation")) == [
        "STALE_GENERATION_APPLIED"
    ]


def test_single_owner_complete_only_and_safe_fallback() -> None:
    assert evaluate_case(_case("simultaneous-visitors-one-shared-owner")) == []
    assert evaluate_case(_case("simultaneous-visitors-duplicate-owner")) == [
        "DUPLICATE_SHARED_BUILD_OWNER"
    ]
    assert evaluate_case(_case("degraded-shared-publish")) == [
        "DEGRADED_ARTIFACT_PUBLISHED"
    ]
    assert evaluate_case(_case("redis-timeout-valid-last-good")) == []
    assert evaluate_case(_case("expired-wrong-fallback")) == [
        "FALLBACK_IDENTITY_MISMATCH",
        "UNSAFE_FALLBACK_ARTIFACT",
    ]


def test_response_identity_order_and_semantics_are_frozen() -> None:
    assert evaluate_case(_case("seen-card-resurrection")) == [
        "RESPONSE_IDENTITY_OR_ORDER_DRIFT",
        "SEEN_OR_DISMISSED_CARD_RESURRECTED",
    ]
    assert evaluate_case(_case("ranking-drift-refused")) == [
        "RESPONSE_IDENTITY_OR_ORDER_DRIFT",
        "SHARING_SEMANTICS_DRIFT",
    ]

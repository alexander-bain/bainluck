from __future__ import annotations

import copy

from scripts.evals.browser_edge_failure_contract import (
    evaluate_case,
    evaluate_corpus,
    load_corpus,
)


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus()["cases"] if row["id"] == case_id))


def test_committed_corpus_matches_all_oracles() -> None:
    report = evaluate_corpus(load_corpus())
    assert report["total"] == 29
    assert report["passed"] == report["total"], report["cases"]


def test_allowed_origin_sees_429_and_disallowed_origin_is_not_reflected() -> None:
    assert evaluate_case(_case("allowed-origin-readable-429")) == []
    assert evaluate_case(_case("current-429-outside-cors")) == [
        "ALLOWED_ORIGIN_RESPONSE_OPAQUE"
    ]
    assert evaluate_case(_case("disallowed-origin-reflected")) == [
        "DISALLOWED_ORIGIN_REFLECTED"
    ]


def test_preflight_does_not_consume_the_application_budget() -> None:
    assert evaluate_case(_case("allowed-preflight-not-counted")) == []
    assert evaluate_case(_case("current-preflight-double-count")) == [
        "LIMIT_ACCOUNTING_DRIFT",
        "PREFLIGHT_CONSUMES_RATE_BUDGET",
    ]


def test_retry_after_and_foreground_ownership_are_bounded() -> None:
    assert evaluate_case(_case("valid-retry-after")) == []
    assert evaluate_case(_case("missing-retry-after")) == ["RETRY_AFTER_INVALID"]
    assert evaluate_case(_case("retry-before-allowed-time")) == [
        "RETRY_BEFORE_ALLOWED_TIME"
    ]
    assert evaluate_case(_case("three-attempt-foreground-amplification")) == [
        "FOREGROUND_RETRY_STORM"
    ]
    assert evaluate_case(_case("cancelled-request-false-green")) == [
        "CANCELLATION_GRADED_SUCCESS"
    ]


def test_unverified_token_cannot_claim_authenticated_bucket() -> None:
    assert evaluate_case(_case("unverified-jwt-cannot-claim-user-bucket")) == [
        "UNVERIFIED_IDENTITY_RATE_BYPASS"
    ]
    assert evaluate_case(_case("verified-user-bucket")) == []


def test_policy_and_internal_identity_fail_closed() -> None:
    assert evaluate_case(_case("missing-policy-authority")) == [
        "POLICY_AUTHORITY_MISSING"
    ]
    assert evaluate_case(_case("internal-identity-leak")) == [
        "INTERNAL_LIMITER_DETAIL_EXPOSED",
        "LIMITER_IDENTITY_EXPOSED",
    ]

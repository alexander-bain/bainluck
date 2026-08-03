from __future__ import annotations

import copy

from scripts.evals.cold_feed_generation_contract import (
    evaluate_case,
    evaluate_corpus,
    load_corpus,
)


def _case(case_id: str) -> dict:
    return copy.deepcopy(next(row for row in load_corpus()["cases"] if row["id"] == case_id))


def test_committed_corpus_matches_all_oracles() -> None:
    report = evaluate_corpus(load_corpus())
    assert report["total"] == 23
    assert report["passed"] == report["total"], report["cases"]


def test_every_phase_declares_owner_budget_generation_scope_and_terminal() -> None:
    matrix = load_corpus()["phase_matrix"]
    required = {"name", "owner", "hard_budget_ms", "generation", "cache_scope", "terminal_state", "code"}
    assert matrix
    assert all(required <= set(row) for row in matrix)


def test_current_cross_response_shapes_duplicate_candidate_work() -> None:
    assert evaluate_case(_case("current-cross-response-race")) == [
        "DUPLICATE_CANDIDATE_BUILD_OWNER"
    ]
    assert evaluate_case(_case("native-web-race")) == [
        "DUPLICATE_CANDIDATE_BUILD_OWNER"
    ]


def test_proposed_owner_releases_and_never_promotes_degraded() -> None:
    assert evaluate_case(_case("clean-miss-one-owner")) == []
    assert evaluate_case(_case("owner-cancel-releases")) == []
    assert evaluate_case(_case("partial-pool-cannot-publish")) == [
        "INCOMPLETE_BUILD_PUBLISHED"
    ]
    assert evaluate_case(_case("degraded-overwrites-last-good")) == [
        "DEGRADED_REPLACED_LAST_GOOD"
    ]


def test_measurement_packet_is_identity_free_and_marks_ops_gate() -> None:
    packet = load_corpus()["measurement_packet"]
    assert packet["status"] == "OPS_MEASUREMENT_REQUIRED"
    assert {"db_pool_checkout_ms", "candidate_queries_ms", "serialization_ms", "client_network_ms"} <= set(packet["durations"])
    assert {"user_id", "session_id", "market_id", "query_text"} <= set(packet["forbidden"])


def test_unavailable_must_survive_the_client_boundary() -> None:
    assert evaluate_case(_case("typed-unavailable")) == []
    assert evaluate_case(_case("current-clients-drop-unavailable")) == [
        "CLIENT_DROPS_UNAVAILABLE_STATE"
    ]

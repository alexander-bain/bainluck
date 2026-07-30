from copy import deepcopy

from scripts.evals.cold_feed_latency_authority import (
    candidate_base_key,
    load_fixture,
    response_cache_key,
    validate,
)


def test_corpus_is_versioned_and_claims_are_decided() -> None:
    corpus = load_fixture()
    assert corpus["schema_version"] == "cold-feed-latency-authority/v1"
    assert corpus["audited_commit"] == "62ccca91"
    assert all(row["verdict"] for row in corpus["claim_matrix"])


def test_scenarios_are_coherent() -> None:
    corpus = load_fixture()
    assert len(corpus["scenarios"]) == 11
    assert all(not validate(row) for row in corpus["scenarios"])


def test_response_cache_fragments_limit_and_offset() -> None:
    rows = {row["id"]: row for row in load_fixture()["scenarios"]}
    page1 = rows["web_cold_page_one"]
    page2 = rows["web_cold_page_two_reuses_base"]
    admin = rows["admin_limit_ten_is_distinct"]
    assert response_cache_key(page1) != response_cache_key(page2)
    assert response_cache_key(page1) != response_cache_key(admin)


def test_candidate_base_reuses_across_pages_and_clients() -> None:
    rows = {row["id"]: row for row in load_fixture()["scenarios"]}
    ids = ["web_cold_page_one", "web_cold_page_two_reuses_base", "native_current_first_page", "native_current_page_two"]
    assert len({candidate_base_key(rows[row_id]) for row_id in ids}) == 1


def test_native_request_shape_is_not_web_request_shape() -> None:
    rows = {row["id"]: row for row in load_fixture()["scenarios"]}
    assert rows["web_cold_page_one"]["limit"] == 20
    assert rows["native_current_first_page"]["limit"] == 50
    assert rows["native_current_page_two"]["limit"] == 200


def test_degraded_build_cannot_publish() -> None:
    corpus = load_fixture()
    row = deepcopy(next(r for r in corpus["scenarios"] if r["id"] == "futures_timeout_truthful"))
    row["publishes_response_cache"] = True
    assert validate(row) == ["degraded_response_published"]


def test_same_async_session_is_not_declared_parallel_safe() -> None:
    corpus = load_fixture()
    row = deepcopy(next(r for r in corpus["scenarios"] if r["id"] == "same_session_queries_remain_serial"))
    row["parallel_safe"] = True
    assert validate(row) == ["same_session_marked_parallel_safe"]


def test_measurement_dimensions_include_page_and_build_identity() -> None:
    dims = set(load_fixture()["measurement_gates"]["required_dimensions"])
    assert {"cache_status", "limit", "offset", "app_build", "degraded_reason"} <= dims


def test_packet_prefers_shared_base_before_native_shape_change() -> None:
    packets = load_fixture()["implementation_packets"]
    assert [p["order"] for p in packets] == [1, 2, 3]
    assert packets[1]["name"] == "shared immutable candidate-id base"
    assert "kill switch" in packets[1]["rollback"]

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path


SCRIPT = Path(__file__).parents[2] / "scripts" / "evals" / "cold_feed_equivalence.py"
SPEC = importlib.util.spec_from_file_location("cold_feed_equivalence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_all_cold_feed_equivalence_fixtures_pass():
    result = MODULE.evaluate()
    assert result["passed"] is True, result
    assert result["golf"]["scenarios"] == 6
    assert result["futures"]["scenarios"] == 3


def test_golf_inventory_covers_freshness_failures_and_ownership():
    names = {fixture["name"] for fixture in MODULE.load_golf_fixtures()}
    assert names == {
        "fresh_precomputed_process_cold",
        "stale_301_not_fresh_uses_bounded_last_good",
        "redis_timeout_inline_provider_success",
        "provider_timeout_without_cache_is_unavailable",
        "two_response_keys_one_shared_fill",
        "cancelled_owner_clean_replacement_rejects_personalized_base",
    }


def test_301_second_payload_is_not_fresh():
    fixture = next(
        f
        for f in MODULE.load_golf_fixtures()
        if f["name"] == "stale_301_not_fresh_uses_bounded_last_good"
    )
    assert MODULE.select_golf_base(fixture)["action"] == "serve_last_good"
    mutated = deepcopy(fixture)
    mutated["primary"]["age_s"] = 300
    assert MODULE.select_golf_base(mutated)["action"] == "serve_primary"


def test_personalized_or_feed_scored_payload_is_rejected_from_shared_base():
    fixture = next(
        f
        for f in MODULE.load_golf_fixtures()
        if f["name"].startswith("cancelled_owner")
    )
    assert MODULE.golf_payload_valid(fixture["primary"]["payload"]) is False
    payload = deepcopy(MODULE.load_golf_fixtures()[0]["primary"]["payload"])
    payload["tournaments"][0]["score"] = 99
    assert MODULE.golf_payload_valid(payload) is False


def test_cross_key_race_launches_one_fill_and_cancel_allows_one_replacement():
    fixtures = {f["name"]: f for f in MODULE.load_golf_fixtures()}
    race = MODULE.simulate_golf_ownership(fixtures["two_response_keys_one_shared_fill"]["ownership_events"])
    assert race["launches"] == ["discover-limit-50"]
    assert race["slot_clean"] is True
    cancel = MODULE.simulate_golf_ownership(
        fixtures["cancelled_owner_clean_replacement_rejects_personalized_base"]["ownership_events"]
    )
    assert cancel["launches"] == ["anon-a", "anon-b"]
    assert cancel["slot_clean"] is True


def test_ordered_pool_dedup_catches_set_or_global_sort_mutants():
    fixture = MODULE.load_futures_fixtures()[0]
    expected = fixture["expected"]["candidate_ids"]
    actual = MODULE.ordered_candidate_ids(fixture)
    assert actual == expected
    assert sorted(set(actual)) != expected


def test_orm_and_side_maps_never_reorder_candidates():
    fixture = MODULE.load_futures_fixtures()[0]
    candidates = MODULE.ordered_candidate_ids(fixture)
    restored = MODULE.restore_orm_order(candidates, fixture["orm_rows"])
    assert restored == fixture["expected"]["restored_ids"]
    assert restored != [row["id"] for row in fixture["orm_rows"]]
    assert [row["id"] for row in MODULE.joined_market_order(fixture, restored)] == restored


def test_thin_merge_preserves_primary_objects_and_timeout_keeps_primary():
    fixtures = {f["name"]: f for f in MODULE.load_futures_fixtures()}
    success = fixtures["thin_merge_preserves_primary_scores_and_namespaces"]
    merged = MODULE.merge_thin_items(success)
    assert merged[:2] == success["primary_items"]
    assert [item["id"] for item in merged] == [1, 2, 7, 8]
    timeout = fixtures["relaxed_timeout_keeps_primary"]
    assert MODULE.merge_thin_items(timeout) == timeout["primary_items"]


def test_relaxed_timing_namespace_is_separate_and_overlap_not_double_counted():
    fixture = next(
        f
        for f in MODULE.load_futures_fixtures()
        if f["name"] == "thin_merge_preserves_primary_scores_and_namespaces"
    )
    contract = MODULE.validate_timing_contract(fixture)
    assert contract["thin_pass"] is True
    assert contract["names_separate"] is True
    assert contract["raw_child_sum"] > contract["non_overlapping_sum"]
    assert contract["parent_covers_non_overlapping"] is True

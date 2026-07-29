from __future__ import annotations

from copy import deepcopy

from scripts.evals.concurrency_lifecycle_contract import (
    FEED_FIXTURES,
    NATIVE_FIXTURES,
    evaluate_corpus,
    load_fixture,
    validate_feed_scenario,
    validate_native_scenario,
)


def test_feed_fixture_schema_and_audited_commit() -> None:
    corpus = load_fixture(FEED_FIXTURES)
    assert corpus["schema_version"] == "singleflight-deadline/v1"
    assert corpus["audited_commit"].startswith("fa42a733")
    assert corpus["policy"]["request_budget_ms"] < corpus["policy"]["router_cutoff_ms"]


def test_all_required_feed_scenarios_satisfy_contract() -> None:
    corpus = load_fixture(FEED_FIXTURES)
    result = evaluate_corpus(corpus, validate_feed_scenario, corpus["policy"])
    assert all(not errors for errors in result["accepted"].values()), result
    assert len(result["accepted"]) == 9


def test_feed_counterexamples_fail_for_declared_reasons() -> None:
    corpus = load_fixture(FEED_FIXTURES)
    for row in corpus["rejected_counterexamples"]:
        assert set(validate_feed_scenario(row, corpus["policy"])) == set(
            row["expected_violations"]
        )


def test_virtual_clock_rejects_22_seconds_times_four_before_compute() -> None:
    corpus = load_fixture(FEED_FIXTURES)
    row = next(
        item
        for item in corpus["rejected_counterexamples"]
        if item["id"] == "legacy_22s_four_rounds_then_compute"
    )
    errors = validate_feed_scenario(row, corpus["policy"])
    assert "request_budget_exceeded" in errors
    assert "router_cutoff_exceeded" in errors
    assert "compute_admitted_after_deadline" in errors


def test_live_owner_overwrite_is_never_a_valid_escape_hatch() -> None:
    corpus = load_fixture(FEED_FIXTURES)
    row = next(
        item
        for item in corpus["rejected_counterexamples"]
        if item["id"] == "unconditional_force_overwrites_live_owner"
    )
    errors = validate_feed_scenario(row, corpus["policy"])
    assert errors == ["multiple_executing_owners", "displaced_owner_orphaned"]


def test_exact_cleanup_history_can_reach_zero_without_multiple_owners() -> None:
    corpus = load_fixture(FEED_FIXTURES)
    for row in corpus["scenarios"]:
        assert max(row["owner_counts"]) <= 1
        if row["terminal"] in {"payload", "last_good"} and row["compute_ms"]:
            assert row["owner_counts"][-1] == 0


def test_native_fixture_schema_and_required_surface_cases() -> None:
    corpus = load_fixture(NATIVE_FIXTURES)
    assert corpus["schema_version"] == "native-sports-lifecycle/v1"
    assert corpus["audited_commit"].startswith("c654dac0")
    ids = {row["id"] for row in corpus["scenarios"]}
    assert {
        "timer_load_disappears",
        "timer_cancellation_ignoring_sibling",
        "pull_refresh_same_id",
        "empty_main",
        "rapid_generations_latest_only",
    } <= ids


def test_all_required_native_scenarios_satisfy_contract() -> None:
    corpus = load_fixture(NATIVE_FIXTURES)
    result = evaluate_corpus(corpus, validate_native_scenario)
    assert all(not errors for errors in result["accepted"].values()), result
    assert len(result["accepted"]) == 10


def test_native_counterexamples_fail_for_declared_reasons() -> None:
    corpus = load_fixture(NATIVE_FIXTURES)
    for row in corpus["rejected_counterexamples"]:
        assert set(validate_native_scenario(row)) == set(row["expected_violations"])


def test_discarded_result_cannot_masquerade_as_cancelled_work() -> None:
    corpus = load_fixture(NATIVE_FIXTURES)
    row = deepcopy(corpus["scenarios"][0])
    row.update(task_terminated=False, termination_policy="discard_result_only")
    assert validate_native_scenario(row)[:2] == [
        "work_not_terminated",
        "discard_is_not_cancellation",
    ]


def test_render_token_is_immutable_and_generation_bound() -> None:
    corpus = load_fixture(NATIVE_FIXTURES)
    row = deepcopy(
        next(item for item in corpus["scenarios"] if item["id"] == "pull_refresh_same_id")
    )
    row["render_token"]["generation"] = 1
    row["reads_live_mutable_count"] = True
    assert validate_native_scenario(row) == [
        "render_generation_mismatch",
        "mutable_render_count",
    ]


def test_same_id_refresh_does_not_depend_on_swiftui_onappear_refiring() -> None:
    corpus = load_fixture(NATIVE_FIXTURES)
    row = deepcopy(
        next(item for item in corpus["scenarios"] if item["id"] == "pull_refresh_same_id")
    )
    row["requires_onappear_refire"] = True
    assert validate_native_scenario(row) == ["onappear_refire_assumption"]

from copy import deepcopy

from scripts.evals.native_parity_inventory import (
    load_inventory,
    summary,
    validate_capability,
    validate_inventory,
)


def _row(row_id: str) -> dict:
    return next(row for row in load_inventory()["capabilities"] if row["id"] == row_id)


def test_inventory_is_versioned_and_valid() -> None:
    corpus = load_inventory()
    assert corpus["schema_version"] == "native-parity-inventory/v1"
    assert corpus["audited_commit"] == "95fdf87f"
    errors = validate_inventory(corpus)
    assert all(not row_errors for row_errors in errors.values()), errors


def test_inventory_covers_required_journeys_and_dimensions() -> None:
    corpus = load_inventory()
    ids = {row["id"] for row in corpus["capabilities"]}
    assert {
        "discover_first_card_latency", "discover_recycling_starvation",
        "sports_first_card_latency", "my_stuff_latency", "event_chart_primary_axis",
        "native_search_race", "team_core_page", "play_and_challenges",
        "hub_surface", "kernels_preview", "watch_app_shipping",
        "widget_and_complication_targets", "native_accessibility_parity",
    } <= ids
    dimensions = {row["dimension"] for row in corpus["capabilities"]}
    assert {
        "core-user-journey", "platform-presentation", "observability-parity",
        "shipping-target-membership", "optional-web-tooling",
    } <= dimensions


def test_only_confirmed_gap_is_immediate_fix() -> None:
    packet = summary(load_inventory())
    assert packet["fix_now"] == ["event_chart_primary_axis"]
    assert packet["new_issue_packet_count"] == 0


def test_missing_web_route_name_cannot_be_native_defect_by_itself() -> None:
    corpus = load_inventory()
    row = deepcopy(_row("kernels_preview"))
    row["status"] = "confirmed"
    row["action"] = "fix-now"
    row["canonical_owner"] = "invented"
    assert "web_tooling_misclassified_as_native_defect" in validate_capability(row, corpus)


def test_fix_now_requires_confirmed_evidence_and_owner() -> None:
    corpus = load_inventory()
    row = deepcopy(_row("my_stuff_latency"))
    row["action"] = "fix-now"
    assert "fix_now_without_confirmed_gap" in validate_capability(row, corpus)


def test_refuted_report_claims_are_not_reintroduced_as_work() -> None:
    assert _row("event_chart_smoothing")["action"] == "not-a-defect"
    assert _row("discover_offline_last_good")["status"] == "already-fixed"
    assert _row("native_search_race")["status"] == "already-fixed"
    assert _row("widget_and_complication_targets")["status"] == "already-fixed"


def test_known_gaps_map_to_existing_canonical_owners() -> None:
    for row_id in (
        "discover_recycling_starvation", "event_chart_primary_axis",
        "team_core_page", "native_card_formats", "watch_app_shipping",
    ):
        assert _row(row_id)["canonical_owner"]


def test_unmeasured_is_measure_first_not_a_bug_claim() -> None:
    for row_id in ("my_stuff_latency", "native_accessibility_parity"):
        row = _row(row_id)
        assert row["status"] == "unmeasured"
        assert row["action"] == "measure-first"

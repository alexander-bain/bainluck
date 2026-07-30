from copy import deepcopy

from scripts.evals.review_verify_closure_authority import (
    FIXTURES,
    assessment_summary,
    authority_action,
    load,
)


def test_corpus_is_versioned_and_records_snapshot_gap() -> None:
    corpus = load(FIXTURES)
    assert corpus["schema_version"] == "review-verify-closure-authority/v1"
    assert corpus["source_snapshot"]["json_rows"] == 72
    assert corpus["source_snapshot"]["reported_live_rows"] == 88
    assert corpus["source_snapshot"]["uncovered_reported_rows"] == 16


def test_authority_scenarios_match_expected_actions() -> None:
    corpus = load(FIXTURES)
    assert len(corpus["scenarios"]) == 17
    for row in corpus["scenarios"]:
        assert authority_action(row) == row["expected_action"], row["id"]


def test_only_complete_current_product_bundle_recommends_manual_close() -> None:
    corpus = load(FIXTURES)
    closable = [row["id"] for row in corpus["scenarios"] if authority_action(row) == "recommend-manual-close"]
    assert closable == ["product_complete_current_bundle"]


def test_creation_age_cannot_substitute_for_column_residence() -> None:
    corpus = load(FIXTURES)
    row = next(r for r in corpus["scenarios"] if r["id"] == "creation_age_not_residence")
    assert row["created_age_hours"] > 168
    assert authority_action(row) == "grace-unknown-residence"


def test_red_resets_continuous_green() -> None:
    corpus = load(FIXTURES)
    row = next(r for r in corpus["scenarios"] if r["id"] == "alert_red_resets_clock")
    assert row["continuous_green_hours"] > 24
    assert authority_action(row) == "red-open"


def test_uncommitted_behavior_never_authorizes_close() -> None:
    corpus = load(FIXTURES)
    row = next(r for r in corpus["scenarios"] if r["id"] == "uncommitted_green_delay")
    assert authority_action(row) == "working-tree-only-no-op"


def test_semantic_duplicate_survives_zero_marker_owners() -> None:
    corpus = load(FIXTURES)
    row = next(r for r in corpus["scenarios"] if r["id"] == "semantic_duplicate_without_marker")
    assert row["declared_marker_owners"] == 0
    assert authority_action(row) == "duplicate-review"


def test_c35_is_recommendations_not_closure_authority() -> None:
    summary = assessment_summary()
    assert summary["rows"] == 72
    assert "recommend-manual-close" not in summary["counts"]
    assert summary["counts"]["evidence-backed-recommendation-revalidate"] == 24
    assert summary["counts"]["unsafe-to-automate-ruling-override"] == 2
    assert summary["assessments"]["802"] == "unsafe-to-automate-ruling-override"
    assert summary["assessments"]["816"] == "unsafe-to-automate-ruling-override"


def test_changed_acceptance_invalidates_old_complete_bundle() -> None:
    corpus = load(FIXTURES)
    row = deepcopy(next(r for r in corpus["scenarios"] if r["id"] == "product_complete_current_bundle"))
    row["acceptance_unchanged"] = False
    assert authority_action(row) == "unsafe-to-automate"


def test_batch_packet_is_bounded_and_draft_only() -> None:
    packet = load(FIXTURES)["batch_packet"]
    assert packet["max_cards"] <= 10
    assert packet["closure_mode"] == "draft-comments-only-until-per-card-revalidation"
    assert "population_incomplete" in packet["stop_conditions"]

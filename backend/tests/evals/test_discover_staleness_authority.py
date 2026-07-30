from copy import deepcopy

import pytest

from scripts.evals.discover_staleness_authority import (
    REQUIRED_METRIC_METADATA,
    classify,
    load_corpus,
    stale_metric,
    validate_row,
)


def _row(row_id: str) -> dict:
    return next(row for row in load_corpus()["scenarios"] if row["id"] == row_id)


def _metadata(**overrides) -> dict:
    values = {
        "deployed_sha": "fixture-only",
        "generated_at": "2026-07-30T14:30:00Z",
        "cache_status": "fixture",
        "build_quality": "complete",
        "limit": 20,
        "offset": 0,
        "surface": "discover",
        "client_shape": "anonymous_web",
        "fixture_version": "discover-staleness-authority/v1",
    }
    values.update(overrides)
    return values


def test_corpus_is_versioned_and_covers_all_four_axes() -> None:
    corpus = load_corpus()
    assert corpus["schema_version"] == "discover-staleness-authority/v1"
    assert corpus["audited_commit"] == "ea04efc4"
    assert len(corpus["scenarios"]) == 20
    for row in corpus["scenarios"]:
        assert {"lifecycle", "content", "user_recency", "cache"} <= set(row)


def test_all_fixture_decisions_are_self_consistent() -> None:
    errors = {row["id"]: validate_row(row) for row in load_corpus()["scenarios"]}
    assert all(not row_errors for row_errors in errors.values()), errors


def test_price_alone_never_settles_an_open_future_market() -> None:
    row = _row("open_ninety_nine_percent_future")
    assert classify(row) == {
        "authoritative_stale": False,
        "surface": True,
        "reason": "eligible",
    }


def test_stale_hit_is_cache_freshness_not_card_lifecycle() -> None:
    row = _row("stale_cache_valid_cards")
    assert classify(row)["authoritative_stale"] is False
    assert classify(row)["surface"] is True


def test_seen_age_is_user_recency_not_content_staleness() -> None:
    row = _row("seen_contested_recycled")
    assert classify(row)["reason"] == "eligible_recycled"
    assert classify(row)["surface"] is True


def test_recycling_and_native_refill_cannot_restore_terminal_rows() -> None:
    for row_id in ("recycled_then_runtime_blocked", "native_refill_must_not_restore_terminal"):
        decision = classify(_row(row_id))
        assert decision["authoritative_stale"] is True
        assert decision["surface"] is False


def test_correction_reopen_invalidates_prior_terminal_state() -> None:
    assert classify(_row("correction_reopens_market"))["surface"] is True


def test_metric_requires_reproducibility_metadata() -> None:
    metadata = _metadata()
    assert set(metadata) == REQUIRED_METRIC_METADATA
    del metadata["deployed_sha"]
    with pytest.raises(ValueError, match="deployed_sha"):
        stale_metric(load_corpus()["scenarios"], metadata)


def test_metric_measures_renderable_impressions_not_candidate_rejections() -> None:
    rows = deepcopy(load_corpus()["scenarios"])
    packet = stale_metric(rows, _metadata(limit=20))
    assert packet["metric"] == "authoritative-stale-rate@20"
    assert packet["numerator"] == 0
    assert packet["rate"] == 0.0
    assert packet["root_causes"] == {}


def test_metric_detects_a_rendered_authoritative_stale_regression() -> None:
    rows = deepcopy(load_corpus()["scenarios"])
    bad = next(row for row in rows if row["id"] == "resolved_market")
    bad["expected"]["surface"] = True
    packet = stale_metric(rows, _metadata(limit=50, client_shape="native_refill_exhausted"))
    assert packet["numerator"] == 1
    assert packet["root_causes"] == {"status_terminal": 1}


def test_top_20_and_top_50_are_distinct_declared_request_shapes() -> None:
    rows = load_corpus()["scenarios"]
    top20 = stale_metric(rows, _metadata(limit=20, offset=0))
    top50 = stale_metric(rows, _metadata(limit=50, offset=0))
    assert top20["metadata"]["limit"] == 20
    assert top50["metadata"]["limit"] == 50

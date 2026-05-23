from types import SimpleNamespace

from app.utils.discover_label_eval_runs import (
    build_category_breakdowns,
    detect_regressions,
    judgment_to_eval_row,
    scalar_metric_values,
)


def test_judgment_to_eval_row_flattens_metadata_and_fixable_interest():
    judgment = SimpleNamespace(
        id=9,
        item_type="futures",
        market_id=123,
        event_id=None,
        market_name="Will this be fixed?",
        label="bad",
        rank_seen=4,
        score_at_review=82.5,
        category_at_review="tech",
        quality_class_at_review="normal",
        reason_tags=["stale"],
        label_metadata={
            "tapworthy_score": 2,
            "clarity": "clear",
            "fixable_interest": {
                "would_be_interesting_if": "It were fresh",
                "fixable_interest_score": 5,
                "fix_type": "staleness",
                "create_issue_candidate": True,
            },
        },
    )

    row = judgment_to_eval_row(judgment)

    assert row["id"] == "futures:123"
    assert row["tapworthy_score"] == 2
    assert row["reason_tags"] == "stale"
    assert row["would_be_interesting_if"] == "It were fresh"
    assert row["fix_type"] == "staleness"
    assert row["create_issue_candidate"] is True


def test_scalar_metric_values_maps_dynamic_top_k_keys():
    metrics = {
        "tapworthy_at_10": 0.8,
        "boring_rate_at_10": 0.1,
        "duplicate_family_rate_at_10": 0.0,
        "unclear_rate_at_10": 0.2,
        "bad_explanation_rate_at_10": 0.3,
        "bad_image_rate_at_10": 0.4,
        "broad_appeal_at_10": 0.7,
        "fixable_interest_rate_at_10": 0.2,
        "tapworthy_recall_at_10": 0.5,
    }

    values = scalar_metric_values(metrics, top_k=10)

    assert values["tapworthy_at_k"] == 0.8
    assert values["boring_rate_at_k"] == 0.1
    assert values["tapworthy_recall_at_k"] == 0.5


def test_detect_regressions_flags_bad_directions_only():
    previous = SimpleNamespace(
        top_k=20,
        tapworthy_at_k=0.8,
        boring_rate_at_k=0.1,
        duplicate_family_rate_at_k=0.0,
        unclear_rate_at_k=0.1,
        bad_explanation_rate_at_k=0.1,
        bad_image_rate_at_k=0.1,
        broad_appeal_at_k=0.8,
        fixable_interest_rate_at_k=0.2,
        tapworthy_recall_at_k=0.8,
    )
    current = {
        "tapworthy_at_20": 0.7,
        "boring_rate_at_20": 0.2,
        "duplicate_family_rate_at_20": 0.0,
        "unclear_rate_at_20": 0.1,
        "bad_explanation_rate_at_20": 0.1,
        "bad_image_rate_at_20": 0.1,
        "broad_appeal_at_20": 0.8,
        "fixable_interest_rate_at_20": 0.3,
        "tapworthy_recall_at_20": 0.8,
    }

    regressions = detect_regressions(current, previous, threshold=0.05)

    assert {item["metric"] for item in regressions} == {
        "tapworthy_at_k",
        "boring_rate_at_k",
    }


def test_build_category_breakdowns_groups_rows():
    rows = [
        {"category": "tech", "label": "love", "tapworthy_score": 5},
        {"category": "tech", "label": "bad", "boring": "true"},
        {"category": "sports", "label": "fine"},
    ]

    breakdowns = build_category_breakdowns(rows)

    assert breakdowns["tech"]["row_count"] == 2
    assert breakdowns["tech"]["label_counts"] == {"bad": 1, "love": 1}
    assert breakdowns["sports"]["row_count"] == 1

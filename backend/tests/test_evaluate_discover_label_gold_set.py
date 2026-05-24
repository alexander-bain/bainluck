import json
from io import StringIO
from pathlib import Path

from scripts.evaluate_discover_label_gold_set import (
    evaluate_gold_set,
    load_rows,
    rank_rows,
    summarize_fixable_interest,
)


def test_rank_rows_prefers_rank_then_score():
    rows = [
        {"id": "low", "rank_seen": "3", "score_at_review": "100"},
        {"id": "top", "rank_seen": "1", "score_at_review": "20"},
        {"id": "score", "rank_seen": "", "score_at_review": "99"},
    ]

    assert [row["id"] for row in rank_rows(rows)] == ["top", "low", "score"]


def test_evaluate_gold_set_computes_top_k_label_metrics():
    rows = [
        {
            "id": "futures:1",
            "name": "Great broad card",
            "rank_seen": 1,
            "score_at_review": 95,
            "label": "love",
            "tapworthy_score": 5,
            "audience_scope": "broad",
            "category": "tech",
        },
        {
            "id": "futures:2",
            "name": "Duplicate bad card",
            "rank_seen": 2,
            "score_at_review": 90,
            "label": "bad",
            "boring": "true",
            "reason_tags": "duplicate,stale",
            "clarity": "needs_context",
            "explanation_quality": "generic",
            "image_fit": "wrong_entity",
            "category": "politics",
            "fix_type": "staleness",
            "would_be_interesting_if": "fresh",
            "fixable_interest_score": 5,
            "create_issue_candidate": "true",
        },
        {
            "id": "futures:3",
            "name": "Fine card",
            "rank_seen": 3,
            "score_at_review": 80,
            "label": "fine",
            "audience_scope": "category_fan",
            "category": "sports",
        },
    ]

    metrics = evaluate_gold_set(rows, top_k=2)

    assert metrics["row_count"] == 3
    assert metrics["tapworthy_at_2"] == 0.5
    assert metrics["boring_rate_at_2"] == 0.5
    assert metrics["duplicate_family_rate_at_2"] == 0.5
    assert metrics["unclear_rate_at_2"] == 0.5
    assert metrics["bad_explanation_rate_at_2"] == 0.5
    assert metrics["bad_image_rate_at_2"] == 0.5
    assert metrics["broad_appeal_at_2"] == 0.5
    assert metrics["fixable_interest_rate_at_2"] == 0.5
    assert metrics["tapworthy_recall_at_2"] == 1.0
    assert metrics["fixable_interest"] == {
        "rows": 1,
        "issue_candidates": 1,
        "high_value_rows": 1,
        "by_fix_type": {"staleness": 1},
    }


def test_summarize_fixable_interest_handles_missing_types():
    summary = summarize_fixable_interest(
        [
            {"would_be_interesting_if": "better entity", "fixable_interest_score": 4},
            {"fix_type": "data_bug", "fixable_interest_score": 3},
            {"label": "love"},
        ]
    )

    assert summary["rows"] == 2
    assert summary["high_value_rows"] == 1
    assert summary["by_fix_type"] == {"data_bug": 1, "unspecified": 1}


def test_evaluate_gold_set_reads_canonical_reason_tag_aliases():
    metrics = evaluate_gold_set(
        [
            {
                "id": "futures:1",
                "rank_seen": 1,
                "label": "bad",
                "reason_tags": "duplicate_family,needs_context",
            }
        ],
        top_k=1,
    )

    assert metrics["duplicate_family_rate_at_1"] == 1.0


def test_load_rows_supports_csv_json_and_jsonl(tmp_path: Path):
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text("id,label\n1,love\n", encoding="utf-8")
    assert load_rows(csv_path) == [{"id": "1", "label": "love"}]

    jsonl_path = tmp_path / "rows.jsonl"
    jsonl_path.write_text(json.dumps({"id": "2", "label": "bad"}) + "\n", encoding="utf-8")
    assert load_rows(jsonl_path) == [{"id": "2", "label": "bad"}]

    json_path = tmp_path / "rows.json"
    json_path.write_text(json.dumps({"rows": [{"id": "3"}]}), encoding="utf-8")
    assert load_rows(json_path) == [{"id": "3"}]

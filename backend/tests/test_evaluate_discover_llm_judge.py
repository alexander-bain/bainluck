import json
from pathlib import Path

from scripts.evaluate_discover_llm_judge import (
    JUDGE_PROMPT_SCHEMA,
    PROMPT_SCHEMA_VERSION,
    build_prompt_row,
    evaluate_judge_outputs,
    load_rows,
)


def test_metric_math_tracks_agreement_precision_recall_and_f1():
    human_rows = [
        _human_row("1", tapworthy_score=5, reason_tags="", clarity="clear"),
        _human_row("2", tapworthy_score=2, reason_tags="", clarity="needs_context"),
        _human_row("3", tapworthy_score=5, reason_tags="duplicate", clarity="clear"),
        _human_row("4", tapworthy_score=2, reason_tags="", clarity="clear"),
    ]
    judge_rows = [
        {"id": "1", "tapworthy": True, "duplicate": False, "clarity": "clear"},
        {"id": "2", "tapworthy": True, "duplicate": False, "clarity": "clear"},
        {"id": "3", "tapworthy": False, "duplicate": True, "clarity": "clear"},
        {"id": "4", "tapworthy": False, "duplicate": True, "clarity": "clear"},
    ]

    results = evaluate_judge_outputs(human_rows, judge_rows)

    tapworthiness = results["metrics"]["tapworthiness"]
    assert tapworthiness["compared"] == 4
    assert tapworthiness["agreement"] == 0.5
    assert tapworthiness["precision"] == 0.5
    assert tapworthiness["recall"] == 0.5
    assert tapworthiness["f1"] == 0.5

    duplicate = results["metrics"]["duplicate"]
    assert duplicate["tp"] == 1
    assert duplicate["fp"] == 1
    assert duplicate["precision"] == 0.5
    assert duplicate["recall"] == 1.0


def test_load_rows_supports_csv_json_and_jsonl(tmp_path: Path):
    csv_path = tmp_path / "rows.csv"
    csv_path.write_text("id,tapworthy_score\n1,5\n", encoding="utf-8")
    assert load_rows(csv_path) == [{"id": "1", "tapworthy_score": "5"}]

    jsonl_path = tmp_path / "rows.jsonl"
    jsonl_path.write_text(json.dumps({"id": "2", "tapworthy": True}) + "\n", encoding="utf-8")
    assert load_rows(jsonl_path) == [{"id": "2", "tapworthy": True}]

    json_path = tmp_path / "rows.json"
    json_path.write_text(json.dumps({"rows": [{"id": "3"}]}), encoding="utf-8")
    assert load_rows(json_path) == [{"id": "3"}]


def test_build_prompt_row_includes_versioned_schema_and_card_fields():
    row = {
        "id": "futures:42",
        "name": "Will a major AI model release this month?",
        "headline": "AI release odds moved",
        "category": "tech",
        "hook_description": "A concrete product-launch market",
        "image_url": "https://example.com/model.jpg",
        "market_id": 42,
    }

    prompt = build_prompt_row(row)
    content = json.loads(prompt["messages"][1]["content"])

    assert prompt["custom_id"] == "futures:42"
    assert prompt["prompt_schema_version"] == PROMPT_SCHEMA_VERSION
    assert JUDGE_PROMPT_SCHEMA["version"] == PROMPT_SCHEMA_VERSION
    assert content["schema"]["required"] == [
        "tapworthy",
        "duplicate",
        "clarity",
        "explanation_quality",
        "audience_scope",
        "image_quality",
        "fixable_interest",
        "rationale",
    ]
    assert content["card"]["name"] == "Will a major AI model release this month?"
    assert content["card"]["hook_description"] == "A concrete product-launch market"


def test_disagreement_bucket_output_groups_false_positive_and_false_negative():
    human_rows = [
        _human_row("false-positive", tapworthy_score=1, reason_tags="", clarity="clear"),
        _human_row("false-negative", tapworthy_score=5, reason_tags="", clarity="clear"),
    ]
    judge_rows = [
        {
            "id": "false-positive",
            "tapworthy": True,
            "duplicate": False,
            "clarity": "clear",
            "rationale": "Looks exciting",
        },
        {
            "id": "false-negative",
            "tapworthy": False,
            "duplicate": False,
            "clarity": "clear",
            "rationale": "Too niche",
        },
    ]

    results = evaluate_judge_outputs(human_rows, judge_rows, disagreement_limit=3)
    buckets = results["disagreement_buckets"]["tapworthiness"]

    assert buckets["false_positive"][0]["id"] == "false-positive"
    assert buckets["false_positive"][0]["judge_rationale"] == "Looks exciting"
    assert buckets["false_negative"][0]["id"] == "false-negative"
    assert buckets["false_negative"][0]["judge_rationale"] == "Too niche"


def _human_row(
    row_id: str,
    *,
    tapworthy_score: int,
    reason_tags: str,
    clarity: str,
) -> dict[str, object]:
    return {
        "id": row_id,
        "name": f"Market {row_id}",
        "label": "love" if tapworthy_score >= 4 else "bad",
        "tapworthy_score": tapworthy_score,
        "reason_tags": reason_tags,
        "clarity": clarity,
        "explanation_quality": "adequate",
        "audience_scope": "broad",
        "image_fit": "good",
        "fixable_interest_score": "",
        "fix_type": "",
        "would_be_interesting_if": "",
    }

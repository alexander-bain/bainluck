"""Tests for the social ground-truth pipeline wrapper."""

import json

from scripts.run_social_ground_truth_pipeline import (
    apply_optional_review,
    build_pipeline_manifest,
)


def test_build_pipeline_manifest_filters_to_approved_target_rows(tmp_path):
    source = tmp_path / "captures.jsonl"
    source.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "account": "kalshi",
                        "caption": "Will Fed cut rates?",
                        "approved": "yes",
                    }
                ),
                json.dumps(
                    {
                        "account": "random",
                        "caption": "Not a target source",
                        "approved": "yes",
                    }
                ),
                json.dumps(
                    {
                        "account": "polymarket",
                        "caption": "Rejected row",
                        "approved": "no",
                    }
                ),
            ]
        )
    )

    rows = build_pipeline_manifest([str(source)])

    assert [row["handle"] for row in rows] == ["@kalshi"]
    assert rows[0]["caption"] == "Will Fed cut rates?"


def test_apply_optional_review_returns_pending_rows_without_decisions():
    rows = apply_optional_review(
        [{"name": "Will Fed cut rates?", "review_status": "pending"}],
        accept_names=[],
        reject_names=[],
        accept_high_confidence=False,
    )

    assert rows == [{"name": "Will Fed cut rates?", "review_status": "pending"}]


def test_apply_optional_review_can_accept_high_confidence():
    rows = apply_optional_review(
        [{"name": "Will Fed cut rates?", "confidence": "high", "review_status": "pending"}],
        accept_names=[],
        reject_names=[],
        accept_high_confidence=True,
    )

    assert rows[0]["review_status"] == "accepted"

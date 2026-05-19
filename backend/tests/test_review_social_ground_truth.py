"""Tests for social ground-truth review/export helper."""

import json

from scripts.review_social_ground_truth import (
    accepted_rows,
    apply_review_decisions,
    load_review_rows,
    summarize,
    write_jsonl,
)


def test_load_review_rows_requires_json_objects(tmp_path):
    source = tmp_path / "review.jsonl"
    source.write_text('{"name":"Will Fed cut rates?","review_status":"pending"}\n')

    assert load_review_rows(source) == [
        {"name": "Will Fed cut rates?", "review_status": "pending"}
    ]


def test_apply_review_decisions_accepts_and_rejects_by_normalized_name():
    rows = [
        {
            "source": "Instagram @kalshi",
            "name": "Will Fed cut rates in June?",
            "confidence": "medium",
            "review_status": "pending",
        },
        {
            "source": "Instagram @polymarket",
            "name": "Will SpaceX launch Starship before July?",
            "confidence": "high",
            "review_status": "pending",
        },
    ]

    reviewed = apply_review_decisions(
        rows,
        accept_names=["Will Fed cut rates in June"],
        reject_names=["Will SpaceX launch Starship before July"],
        accept_high_confidence=True,
    )

    assert reviewed[0]["review_status"] == "accepted"
    assert reviewed[1]["review_status"] == "rejected"


def test_accept_high_confidence_leaves_lower_confidence_pending():
    reviewed = apply_review_decisions(
        [
            {"name": "High confidence market", "confidence": "high"},
            {"name": "Medium confidence market", "confidence": "medium"},
        ],
        accept_high_confidence=True,
    )

    assert reviewed[0]["review_status"] == "accepted"
    assert reviewed[1]["review_status"] == "pending"


def test_accepted_rows_filters_review_gate_statuses():
    rows = [
        {"name": "Accepted", "review_status": "accepted"},
        {"name": "Approved", "review_status": "approved"},
        {"name": "Reviewed", "review_status": "reviewed"},
        {"name": "Pending", "review_status": "pending"},
        {"name": "Rejected", "review_status": "rejected"},
    ]

    assert [row["name"] for row in accepted_rows(rows)] == [
        "Accepted",
        "Approved",
        "Reviewed",
    ]


def test_write_jsonl_preserves_review_fields_and_extra_metadata(tmp_path):
    output = tmp_path / "accepted.jsonl"

    write_jsonl(
        [
            {
                "source": "Instagram @kalshi",
                "category": "economics",
                "name": "Will Fed cut rates?",
                "evidence": "image text",
                "confidence": "high",
                "review_status": "accepted",
                "post_id": "abc123",
            }
        ],
        output,
    )

    payload = json.loads(output.read_text())
    assert list(payload)[:14] == [
        "source",
        "category",
        "name",
        "probability",
        "hook",
        "url",
        "published_at",
        "platform",
        "handle",
        "engagement",
        "evidence",
        "confidence",
        "extraction_notes",
        "review_status",
    ]
    assert payload["evidence"] == "image text"
    assert payload["post_id"] == "abc123"


def test_summarize_counts_statuses():
    assert summarize(
        [
            {"review_status": "accepted"},
            {"review_status": "approved"},
            {"review_status": "pending"},
            {"review_status": "rejected"},
            {"review_status": ""},
        ]
    ) == {
        "rows": 5,
        "accepted": 2,
        "pending": 2,
        "rejected": 1,
        "statuses": {"accepted": 1, "approved": 1, "pending": 2, "rejected": 1},
    }

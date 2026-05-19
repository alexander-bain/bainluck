"""Tests for persisted external-curator ground-truth helpers."""

from datetime import datetime, timezone

from app.utils.persisted_external_curator_ground_truth import (
    build_external_curator_dedupe_key,
    merge_external_curator_ground_truth_reports,
    normalize_persistable_external_curator_rows,
)


def test_build_external_curator_dedupe_key_prefers_url():
    key = build_external_curator_dedupe_key(
        {
            "source": "Instagram @kalshi",
            "name": "Will Fed cut rates?",
            "url": "https://instagram.com/p/abc",
        }
    )

    assert len(key) == 64
    assert key == build_external_curator_dedupe_key(
        {
            "source": "Instagram @different",
            "name": "Will Fed cut rates?",
            "url": "https://instagram.com/p/abc",
        }
    )


def test_build_external_curator_dedupe_key_falls_back_to_source_when_no_url():
    assert build_external_curator_dedupe_key(
        {"source": "Instagram @kalshi", "name": "Will Fed cut rates?"}
    ) != build_external_curator_dedupe_key(
        {"source": "Instagram @polymarket", "name": "Will Fed cut rates?"}
    )


def test_normalize_persistable_rows_keeps_accepted_review_gate_only():
    rows = normalize_persistable_external_curator_rows(
        [
            {
                "source": "Instagram @kalshi",
                "name": "Will Fed cut rates?",
                "review_status": "accepted",
                "url": "https://instagram.com/p/abc",
                "evidence": "caption text",
            },
            {
                "source": "Instagram @kalshi",
                "name": "Will recession happen?",
                "review_status": "pending",
            },
        ]
    )

    assert len(rows) == 1
    assert rows[0]["name"] == "Will Fed cut rates?"
    assert rows[0]["review_status"] == "accepted"
    assert rows[0]["evidence"] == "caption text"


def test_merge_external_curator_reports_dedupes_and_preserves_health_metadata():
    now = datetime(2026, 5, 18, tzinfo=timezone.utc)
    merged = merge_external_curator_ground_truth_reports(
        [
            {
                "items": [
                    {
                        "source": "Instagram @kalshi",
                        "category": "economics",
                        "name": "Will Fed cut rates?",
                        "url": "https://instagram.com/p/abc",
                        "published_at": "2026-05-18",
                        "platform": "instagram",
                        "review_status": "accepted",
                    }
                ],
                "metadata": {
                    "configured": True,
                    "source_paths": ["/tmp/social.accepted.jsonl"],
                    "raw_row_count": 1,
                    "error": None,
                },
            },
            {
                "items": [
                    {
                        "source": "Instagram @kalshi",
                        "category": "economics",
                        "name": "Will Fed cut rates?",
                        "url": "https://instagram.com/p/abc",
                        "published_at": "2026-05-18",
                        "platform": "instagram",
                        "review_status": "accepted",
                    }
                ],
                "metadata": {
                    "configured": True,
                    "source_paths": ["db:external_curator_ground_truth_items"],
                    "raw_row_count": 1,
                    "error": None,
                },
            },
        ],
        now=now,
    )

    assert len(merged["items"]) == 1
    assert merged["metadata"]["configured"] is True
    assert merged["metadata"]["raw_row_count"] == 2
    assert merged["metadata"]["loaded_count"] == 1
    assert merged["metadata"]["source_paths"] == [
        "/tmp/social.accepted.jsonl",
        "db:external_curator_ground_truth_items",
    ]
    assert merged["metadata"]["source_health"] == [
        {
            "source": "Instagram @kalshi",
            "count": 1,
            "latest_date": "2026-05-18",
            "stale": False,
            "platform_counts": {"instagram": 1},
        }
    ]

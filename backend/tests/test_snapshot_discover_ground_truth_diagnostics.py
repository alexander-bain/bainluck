"""Tests for Discover ground-truth diagnostic snapshot extraction."""

from datetime import datetime, timezone

from scripts.snapshot_discover_ground_truth_diagnostics import (
    build_diagnostic_rows_from_debug_payload,
)


def test_build_diagnostic_rows_from_debug_payload_extracts_misses_and_hits():
    captured_at = datetime(2026, 5, 18, tzinfo=timezone.utc)
    payload = {
        "missing_ground_truth": [
            {
                "source": "kalshi",
                "name": "Will the SAVE Act become law?",
                "category": "politics",
                "probability": "Yes 9%",
                "quality_class": "normal",
                "archetype": "political_power",
                "family_key": "save act",
                "story_key": "story:us_federal_power",
                "triage_bucket": "ranking_too_low",
                "recommended_action": "Inspect score inputs.",
                "db_trace": {
                    "trace_status": "eligible_but_not_top_50",
                    "trace_summary": "A similar open market exists.",
                    "matches": [{"id": 123, "name": "Will the SAVE Act become law?"}],
                },
            }
        ],
        "email_ground_truth_misses": [
            {
                "source": "polymarket_email",
                "name": "Will OpenAI release GPT-6?",
                "category": "tech",
                "triage_bucket": "ingestion_gap",
                "db_trace": {"trace_status": "no_db_match", "matches": []},
            }
        ],
        "email_ground_truth": {
            "hits": [
                {
                    "name": "US recession by end of 2026?",
                    "rank": 41,
                    "feed_name": "US recession by end of 2026?",
                    "category": "economics",
                }
            ]
        },
        "external_curator_ground_truth_misses": [
            {
                "source": "Curator",
                "name": "Will AI exports be restricted?",
                "category": "tech",
                "url": "https://example.com/ai",
                "published_at": "2026-05-18",
                "triage_bucket": "candidate_recall_gap",
                "db_trace": {"trace_status": "eligible_but_not_top_50", "matches": []},
            }
        ],
        "external_curator_ground_truth": {
            "hits": [
                {
                    "name": "Will China invade Taiwan by end of 2026?",
                    "rank": 26,
                    "feed_name": "Will China invade Taiwan by end of 2026?",
                    "category": "geopolitics",
                }
            ]
        },
    }

    rows = build_diagnostic_rows_from_debug_payload(
        payload,
        run_id="run-1",
        captured_at=captured_at,
    )

    assert len(rows) == 5
    assert [(row["source_group"], row["status"]) for row in rows] == [
        ("combined", "miss"),
        ("email", "miss"),
        ("external_curator", "miss"),
        ("email", "hit"),
        ("external_curator", "hit"),
    ]
    assert rows[0]["matched_market_id"] == 123
    assert rows[0]["trace_status"] == "eligible_but_not_top_50"
    assert rows[2]["source_url"] == "https://example.com/ai"
    assert rows[3]["rank"] == 41
    assert all(row["run_id"] == "run-1" for row in rows)
    assert all(row["captured_at"] == captured_at for row in rows)

from argparse import Namespace
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO

from sqlalchemy.dialects import postgresql

from scripts.export_discover_labeled_dataset import (
    EXPORT_FIELDS,
    build_labeled_dataset_statement,
    format_labeled_row,
    summarize_fixable_interest,
    write_rows,
)


NOW = datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)


def test_build_labeled_dataset_statement_filters_and_joins():
    statement = build_labeled_dataset_statement(
        since=NOW,
        limit=100,
        surface="discover",
        reviewer="alex",
        labels=("love", "bad"),
    )
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "ranking_judgments" in compiled
    assert "futures_markets" in compiled
    assert "futures_outcomes" in compiled
    assert "discover_interactions" in compiled
    assert "LATERAL" in compiled
    assert "ranking_judgments.surface = 'discover'" in compiled
    assert "ranking_judgments.reviewer = 'alex'" in compiled
    assert "ranking_judgments.label IN ('love', 'bad')" in compiled


def test_format_labeled_row_flattens_metadata_and_fixable_interest():
    row = {
        "judgment_id": 9,
        "created_at": NOW,
        "reviewer": "alex",
        "surface": "discover",
        "rank_seen": 4,
        "item_type": "futures",
        "market_id": 123,
        "event_id": None,
        "name": "Will the #2 Netflix movie stay #2?",
        "label": "bad",
        "reason_tags": ["wrong_variant", "interesting_if_fixed"],
        "notes": "Wrong rank",
        "score_at_review": Decimal("82.5"),
        "category": "entertainment",
        "archetype": "streaming",
        "quality_class": "normal",
        "headline": "A streaming market",
        "label_metadata": {
            "tapworthy_score": 2,
            "boring": False,
            "clarity": "clear",
            "card_snapshot": {
                "schema_version": "discover-card-v1",
                "batch_id": "batch-1",
                "feed_request_id": "feed-1",
                "name": "Will the #2 Netflix movie stay #2?",
                "source": "polymarket",
                "story_key": "story:netflix",
                "family_key": "entertainment:streaming",
                "group_id": "group-netflix",
                "context": "Streaming context",
                "image_url": "https://example.com/snapshot.jpg",
                "hook_description": "Snapshot hook",
                "rendered_probability": Decimal("0.61"),
                "top_outcomes": [{"name": "Yes", "probability": 0.61}],
            },
            "fixable_interest": {
                "would_be_interesting_if": "It were about #1",
                "fixable_interest_score": 5,
                "fix_type": "wrong_entity_rank",
                "desired_entity_or_variant": "#1 Netflix movie",
                "current_entity_or_variant": "#2 Netflix movie",
                "create_issue_candidate": True,
            },
        },
        "source": "polymarket",
        "market_status": "open",
        "group_id": "story:netflix",
        "leader_probability": Decimal("0.61"),
        "movement_24h": Decimal("0.08"),
        "volume_24h": Decimal("12000"),
        "resolution_date": NOW,
        "image_url": "https://example.com/image.jpg",
        "hook_description": "Streaming hook",
        "impressions": 20,
        "positive_engagements": 3,
        "negative_engagements": 5,
        "avg_rank": Decimal("12.5"),
        "avg_feed_score": Decimal("82.5"),
    }

    formatted = format_labeled_row(row)

    assert formatted["id"] == "futures:123"
    assert formatted["label"] == "bad"
    assert formatted["reason_tags"] == "wrong_variant,interesting_if_fixed"
    assert formatted["tapworthy_score"] == 2
    assert formatted["boring"] is False
    assert '"schema_version": "discover-card-v1"' in formatted["card_snapshot"]
    assert formatted["snapshot_batch_id"] == "batch-1"
    assert formatted["snapshot_feed_request_id"] == "feed-1"
    assert formatted["snapshot_story_key"] == "story:netflix"
    assert formatted["snapshot_group_id"] == "group-netflix"
    assert formatted["snapshot_context"] == "Streaming context"
    assert formatted["snapshot_image_url"] == "https://example.com/snapshot.jpg"
    assert formatted["snapshot_hook_description"] == "Snapshot hook"
    assert formatted["snapshot_rendered_probability"] == 0.61
    assert '"name": "Yes"' in formatted["snapshot_top_outcomes"]
    assert formatted["would_be_interesting_if"] == "It were about #1"
    assert formatted["fixable_interest_score"] == 5
    assert formatted["fix_type"] == "wrong_entity_rank"
    assert formatted["create_issue_candidate"] is True
    assert formatted["positive_rate"] == 0.15
    assert formatted["negative_rate"] == 0.25


def test_summarize_fixable_interest_counts_types_and_issue_candidates():
    summary = summarize_fixable_interest(
        [
            {
                "fix_type": "staleness",
                "would_be_interesting_if": "fresh",
                "create_issue_candidate": "true",
            },
            {
                "fix_type": "wrong_entity_rank",
                "would_be_interesting_if": "#1",
                "create_issue_candidate": False,
            },
            {"fix_type": "", "would_be_interesting_if": ""},
        ]
    )

    assert summary == {
        "rows": 3,
        "fixable_rows": 2,
        "issue_candidates": 1,
        "by_fix_type": {"staleness": 1, "wrong_entity_rank": 1},
    }


def test_format_labeled_row_canonicalizes_reason_tag_aliases():
    formatted = format_labeled_row(
        {
            "judgment_id": 10,
            "item_type": "futures",
            "market_id": 456,
            "label": "bad",
            "reason_tags": ["important", "needs_context", "bucket", "important"],
        }
    )

    assert formatted["reason_tags"] == "high_stakes,unclear,repetitive"


def test_write_rows_supports_csv_and_jsonl():
    row = {
        "id": "futures:1",
        "judgment_id": 1,
        "label": "love",
        "fix_type": "staleness",
    }
    csv_handle = StringIO()
    write_rows([row], csv_handle, fmt="csv")
    assert csv_handle.getvalue().splitlines()[0].startswith("id,judgment_id")
    assert "futures:1" in csv_handle.getvalue()

    jsonl_handle = StringIO()
    write_rows([row], jsonl_handle, fmt="jsonl")
    assert '"fix_type": "staleness"' in jsonl_handle.getvalue()

    assert "fix_type" in EXPORT_FIELDS
    assert "card_snapshot" in EXPORT_FIELDS

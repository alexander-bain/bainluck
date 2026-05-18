from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO

from sqlalchemy.dialects import postgresql

from scripts.export_discover_interestingness import (
    build_export_statement,
    format_export_row,
    summarize_rows,
    write_summary,
    write_rows,
)


NOW = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)


def test_build_export_statement_aggregates_and_joins_metadata():
    statement = build_export_statement(
        since=NOW,
        limit=100,
        min_impressions=5,
        surface="web",
    )
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "discover_interactions" in compiled
    assert "futures_markets" in compiled
    assert "futures_outcomes" in compiled
    assert "events" in compiled
    assert "FILTER (WHERE discover_interactions.action = 'impression')" in compiled
    assert "discover_interactions.surface = 'web'" in compiled
    assert "interactions.item_id ~ '^[0-9]+$'" in compiled
    assert "jsonb_object_length(events.win_probability_sources)" in compiled
    assert "HAVING count(*) FILTER" in compiled


def test_format_export_row_derives_positive_label_and_calibration_fields():
    row = {
        "item_type": "futures",
        "item_id": "42",
        "name": "Will rates be cut next week?",
        "category": "economics",
        "surface": "web",
        "source": "kalshi",
        "market_status": "open",
        "event_status": None,
        "probability": Decimal("0.680000"),
        "source_count": 2,
        "updated_at": NOW,
        "movement_24h": Decimal("0.120000"),
        "resolution_date": NOW,
        "category_recent_count": 12,
        "category_feed_share": 0.24,
        "volume_24h": Decimal("1000"),
        "impressions": 20,
        "opens": 2,
        "detail_clicks": 1,
        "likes": 0,
        "shares": 0,
        "context_expands": 0,
        "group_expands": 0,
        "dismisses": 1,
        "unlikes": 0,
        "positive_engagements": 3,
        "negative_engagements": 1,
        "avg_rank": Decimal("4.5"),
        "avg_feed_score": Decimal("71.25"),
        "first_seen_at": NOW,
        "last_seen_at": NOW,
    }

    formatted = format_export_row(row)

    assert formatted["id"] == "futures:42"
    assert formatted["probability"] == 0.68
    assert formatted["movement_24h"] == 0.12
    assert formatted["source_count"] == 2
    assert formatted["label"] == "positive"
    assert formatted["positive_rate"] == 0.15
    assert formatted["negative_rate"] == 0.05
    assert formatted["engagement_score"] == 0.1
    assert formatted["updated_at"] == NOW.isoformat()


def test_format_export_row_derives_negative_label():
    formatted = format_export_row(
        {
            "item_type": "futures",
            "item_id": "99",
            "impressions": 20,
            "positive_engagements": 0,
            "negative_engagements": 9,
            "dismisses": 8,
            "unlikes": 1,
        }
    )

    assert formatted["label"] == "negative"
    assert formatted["positive_rate"] == 0
    assert formatted["negative_rate"] == 0.45


def test_write_rows_supports_csv_and_jsonl():
    rows = [
        {
            "id": "futures:1",
            "item_type": "futures",
            "item_id": "1",
            "name": "Market",
            "label": None,
            "impressions": 3,
        }
    ]

    csv_handle = StringIO()
    write_rows(rows, csv_handle, fmt="csv")
    assert csv_handle.getvalue().splitlines()[0].startswith("id,item_type,item_id")
    assert "futures:1,futures,1,Market" in csv_handle.getvalue()

    jsonl_handle = StringIO()
    write_rows(rows, jsonl_handle, fmt="jsonl")
    assert '"id": "futures:1"' in jsonl_handle.getvalue()
    assert '"label": ""' in jsonl_handle.getvalue()


def test_summarize_rows_groups_by_category_and_score_bucket():
    rows = [
        {
            "category": "tech",
            "impressions": 30,
            "positive_engagements": 6,
            "negative_engagements": 1,
            "avg_rank": 14,
            "avg_feed_score": 86,
            "label": "positive",
        },
        {
            "category": "tech",
            "impressions": 20,
            "positive_engagements": 5,
            "negative_engagements": 0,
            "avg_rank": 13,
            "avg_feed_score": 92,
            "label": "positive",
        },
        {
            "category": "politics",
            "impressions": 40,
            "positive_engagements": 0,
            "negative_engagements": 12,
            "avg_rank": 5,
            "avg_feed_score": 99,
            "label": "negative",
        },
    ]

    summary = summarize_rows(rows)

    assert summary["rows"] == 3
    assert summary["overall"]["impressions"] == 90
    assert summary["labels"] == {"positive": 2, "negative": 1, "unlabeled": 0}
    assert summary["categories"][0]["key"] == "tech"
    assert summary["categories"][0]["positive_rate"] == 0.22
    assert summary["categories"][0]["avg_feed_score"] == 88.4
    assert {row["key"] for row in summary["score_buckets"]} == {"80-89", "90-99"}
    assert any(
        item["kind"] == "under-ranked_category" and item["category"] == "tech"
        for item in summary["opportunities"]
    )
    assert any(
        item["kind"] == "over-ranked_category" and item["category"] == "politics"
        for item in summary["opportunities"]
    )


def test_write_summary_supports_json_and_text():
    summary = summarize_rows(
        [
            {
                "category": "tech",
                "impressions": 20,
                "positive_engagements": 3,
                "negative_engagements": 0,
                "avg_rank": 11,
                "avg_feed_score": 91,
            }
        ]
    )

    text_handle = StringIO()
    write_summary(summary, text_handle, as_json=False)
    assert "Discover engagement calibration summary" in text_handle.getvalue()
    assert "tech" in text_handle.getvalue()

    json_handle = StringIO()
    write_summary(summary, json_handle, as_json=True)
    assert '"score_buckets"' in json_handle.getvalue()

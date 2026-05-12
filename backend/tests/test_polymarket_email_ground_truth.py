"""Tests for Polymarket email-highlight ground truth parsing."""

from datetime import datetime, timezone

from app.utils.polymarket_email_ground_truth import (
    load_polymarket_email_ground_truth_from_csv_text,
    summarize_polymarket_email_ground_truth,
)


CSV_TEXT = """Date,Source,Market Name,Category,Leader,Leader Probability,Resolution Date,Email Subject,LLM Category,Hook,Interestingness,Timeliness,Shareability
2026-05-11,polymarket,Will Donald Trump visit China on May 13?,politics,,,May 13 2026,Email,politics,Hook,9,this_week,8
2026-05-11,polymarket,Will Donald Trump visit China on May 13?,politics,,,May 13 2026,Email,politics,Hook,9,this_week,8
2026-05-10,polymarket,Low-signal market,other,,,,Email,other,Hook,7,ongoing,6
2026-04-01,polymarket,Old but interesting,tech,,,,Email,tech,Hook,9,ongoing,7
2026-05-11,kalshi,Wrong source,politics,,,,Email,politics,Hook,9,this_week,8
"""


def test_load_polymarket_email_ground_truth_filters_and_dedupes():
    items = load_polymarket_email_ground_truth_from_csv_text(
        CSV_TEXT,
        min_interestingness=8,
        lookback_days=21,
        now=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )

    assert len(items) == 1
    assert items[0]["source"] == "polymarket_email"
    assert items[0]["name"] == "Will Donald Trump visit China on May 13?"
    assert items[0]["category"] == "politics"
    assert items[0]["interestingness"] == "9"


def test_summarize_polymarket_email_ground_truth_matches_feed_names():
    email_items = load_polymarket_email_ground_truth_from_csv_text(
        CSV_TEXT,
        min_interestingness=8,
        lookback_days=21,
        now=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )
    diagnosed = [
        {
            "rank": 4,
            "name": "Will Trump visit China on May 13?",
        }
    ]

    summary = summarize_polymarket_email_ground_truth(diagnosed, email_items)

    assert summary["total"] == 1
    assert summary["top20_hits"] == 1
    assert summary["top50_hits"] == 1
    assert summary["missing"] == 0
    assert summary["hits"][0]["rank"] == 4

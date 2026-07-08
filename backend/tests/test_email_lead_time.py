"""Tests for the email lead-time metric (#142/RANK-2, plan addendum item 1)."""

from datetime import datetime, timezone

from app.utils.discover_candidate_snapshot import compute_email_lead_time_rows


def _exact_matcher(a, b):
    return a.strip().lower() == b.strip().lower()


def test_beat_and_missed_email():
    first_surfaced = {
        1: {
            "name": "Fed cuts rates",
            "first_surfaced_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        },
        2: {
            "name": "Russia advances",
            "first_surfaced_at": datetime(2026, 7, 10, tzinfo=timezone.utc),
        },
    }
    email_items = [
        {"name": "Fed cuts rates", "date": "2026-07-05"},  # we beat by 4 days
        {"name": "Russia advances", "date": "2026-07-08"},  # email beat us by 2 days
        {"name": "Unrelated market", "date": "2026-07-01"},  # no snapshot match
        {"name": "No date market", "date": ""},  # skipped (no date)
    ]
    metric = compute_email_lead_time_rows(
        first_surfaced, email_items, name_matcher=_exact_matcher
    )
    assert metric["matched"] == 2
    assert metric["beat_email_count"] == 1
    assert metric["beat_email_rate"] == 0.5
    by_market = {r["market_id"]: r for r in metric["rows"]}
    assert by_market[1]["lead_days"] == 4
    assert by_market[1]["beat_email"] is True
    assert by_market[2]["lead_days"] == -2
    assert by_market[2]["beat_email"] is False


def test_empty_history_returns_note_not_crash():
    metric = compute_email_lead_time_rows(
        {}, [{"name": "x", "date": "2026-07-01"}], name_matcher=_exact_matcher
    )
    assert metric["matched"] == 0
    assert metric["beat_email_rate"] is None
    assert metric["note"]

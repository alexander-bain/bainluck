"""Future play dates cannot earn the live bonus from price discovery (#5105)."""

import asyncio
import json
from pathlib import Path
from datetime import datetime, timezone

import pytest

from app.routes.feed import _score_golf_tournaments, _score_tournament, _tournament_is_live


NOW = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)


def tournament(**overrides):
    return {
        "key": "future-golf",
        "name": "Future tournament",
        "is_tour_event": True,
        "is_major": False,
        "schedule_status": "upcoming",
        "start_date": "2026-10-09T12:00:00+00:00",
        "end_date": "2026-10-12T12:00:00+00:00",
        "market_sources": ["kalshi", "polymarket"],
        "golfers": [{"name": "Leader", "rank": 1, "probability": 0.2, "movement_24h": 0.05, "movement_is_dated": False}],
        **overrides,
    }


@pytest.mark.parametrize("end", [None, "2026-10-12T12:00:00+00:00"])
@pytest.mark.parametrize("start", [
    "2026-10-09T12:00:00+00:00",
    "2026-10-09T12:00:00",
    "2026-10-07T05:30:00-07:00",  # 12:30 UTC, still in the future
])
def test_future_play_date_overrides_movement(start, end):
    assert not _tournament_is_live(tournament(start_date=start, end_date=end), NOW)


def test_only_false_live_bonus_is_removed():
    moving = tournament()
    still = tournament(golfers=[{"name": "Leader", "probability": 0.2, "movement_24h": 0}])
    assert _score_tournament(moving, NOW) == 58
    assert _score_tournament(still, NOW) == 48
    assert _score_tournament(moving, NOW) - _score_tournament(still, NOW) == 10


def test_reported_in_progress_keeps_precedence_over_schedule_date():
    assert _tournament_is_live(tournament(schedule_status="in-progress"), NOW)


def test_champion_keeps_precedence_over_reported_in_progress():
    assert not _tournament_is_live(
        tournament(schedule_status="in-progress", champion="Leader"), NOW
    )


def test_in_window_with_offset_still_live():
    assert _tournament_is_live(tournament(
        start_date="2026-10-07T13:00:00+02:00",
        end_date="2026-10-10T13:00:00+02:00",
        golfers=[],
    ), NOW)


@pytest.mark.parametrize("start", [None, "bad-date"])
def test_unknown_schedule_does_not_infer_live_from_movement(start):
    assert not _tournament_is_live(tournament(start_date=start, end_date=None), NOW)


def test_unknown_schedule_without_movement_is_not_live():
    assert not _tournament_is_live(tournament(start_date=None, end_date=None, golfers=[]), NOW)


def test_future_card_retains_prices_without_live_headline(monkeypatch):
    from app.utils import golf_base

    data = tournament()

    async def base(_db, _now, stages=None):
        return [data], "fresh"

    monkeypatch.setattr(golf_base, "get_golf_base", base)
    cards = asyncio.run(_score_golf_tournaments(None, NOW, None))
    assert len(cards) == 1
    assert cards[0]["score"] == 58
    assert cards[0]["headline"] == "This week"
    assert cards[0]["data"]["golfers"] == data["golfers"]


def test_retained_unscheduled_card_is_not_evidence_of_live_play():
    fixture = json.loads((Path(__file__).parent / "fixtures" / "discover_5105_unscheduled_tournament.json").read_text())
    assert fixture["capture_sha256"] == "e93246d2c2f22b50d6345898b505fee6709947726894c68ffc5cdb5f81888c1a"
    assert fixture["captured_headline"] == "Live"
    assert fixture["captured_score"] == 78
    assert not _tournament_is_live(fixture["data"], datetime.fromisoformat(fixture["scoring_now"]))


def test_unknown_schedule_card_keeps_movement_bonus_but_neutral_headline(monkeypatch):
    from app.utils import golf_base

    data = tournament(start_date=None, end_date=None, schedule_status=None)

    async def base(_db, _now, stages=None):
        return [data], "fresh"

    monkeypatch.setattr(golf_base, "get_golf_base", base)
    cards = asyncio.run(_score_golf_tournaments(None, NOW, None))
    assert len(cards) == 1
    assert cards[0]["score"] == 43  # base30 + movement10 + two-source3
    assert cards[0]["headline"] is None
    assert cards[0]["data"]["golfers"] == data["golfers"]


def test_no_dates_with_explicit_in_progress_still_earns_live_bonus():
    data = tournament(start_date=None, end_date=None, schedule_status="in-progress")
    assert _tournament_is_live(data, NOW)
    assert _score_tournament(data, NOW) == 78


@pytest.mark.parametrize("at, expected", [
    ("2026-10-07T11:59:59+00:00", True),
    ("2026-10-07T12:00:00+00:00", True),
    ("2026-10-07T18:00:00+00:00", True),
    ("2026-10-07T23:59:59+00:00", True),
    ("2026-10-08T00:00:00+00:00", False),
])
def test_calendar_window_covers_entire_last_day_without_price_fallback(at, expected):
    # Same calendar-date contract as web tournamentLive.ts; midnight is the
    # beginning of the final round's day, not the final putt.
    data = tournament(start_date="2026-10-04T00:00:00+00:00",
                      end_date="2026-10-07T00:00:00+00:00")
    assert _tournament_is_live(data, datetime.fromisoformat(at)) is expected

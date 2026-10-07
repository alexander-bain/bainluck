"""Future play dates cannot earn the live bonus from price discovery (#5105)."""

import asyncio
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
def test_unknown_schedule_movement_fallback_is_unchanged(start):
    assert _tournament_is_live(tournament(start_date=start, end_date=None), NOW)


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

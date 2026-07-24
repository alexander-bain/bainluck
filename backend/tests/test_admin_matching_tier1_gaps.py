"""Tests for the Tier-1 prediction market gap admin diagnostic."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_request():
    # Admin auth is header-only now (Queue #252 Item 3).
    return SimpleNamespace(headers={"authorization": "Bearer test-secret"})

from app.routes.admin_matching import (
    _should_exclude_tier1_gap_for_closed_game,
    prediction_market_tier1_gaps,
)


def _result(*, scalars=None, rows=None):
    result = MagicMock()
    result.scalars.return_value.all.return_value = scalars or []
    result.all.return_value = rows or []
    return result


def _event_row(*, status, commence_time, completed_at=None):
    return SimpleNamespace(
        id=123,
        home_team_name="Boston Celtics",
        away_team_name="New York Knicks",
        commence_time=commence_time,
        status=status,
        completed_at=completed_at,
    )


def _market(*, market_id, name="Boston Celtics at New York Knicks"):
    return SimpleNamespace(
        id=market_id,
        external_id=f"KXNBAGAME-26MAY17BOSNYK-{market_id}",
        name=name,
        commence_time=datetime(2026, 5, 17, 23, 0, tzinfo=timezone.utc),
    )


def test_closed_past_events_are_excluded_from_tier1_gap_denominator():
    now = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
    candidates = [
        _event_row(status="completed", commence_time=now - timedelta(hours=12)),
        _event_row(status="closed", commence_time=now - timedelta(hours=11)),
    ]

    assert _should_exclude_tier1_gap_for_closed_game(candidates, now) is True


def test_active_candidate_keeps_tier1_market_in_gap_denominator():
    now = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)
    candidates = [
        _event_row(status="completed", commence_time=now - timedelta(hours=12)),
        _event_row(status="scheduled", commence_time=now + timedelta(hours=2)),
    ]

    assert _should_exclude_tier1_gap_for_closed_game(candidates, now) is False


@pytest.mark.asyncio
async def test_tier1_gaps_endpoint_skips_settlement_open_closed_game(
    monkeypatch,
):
    monkeypatch.setenv("ADMIN_TOKEN", "test-secret")

    matchup = SimpleNamespace(
        team_a="Boston Celtics",
        team_b="New York Knicks",
        format_type="at",
    )
    monkeypatch.setattr(
        "app.utils.prediction_market_matching.extract_matchup_with_ticker_fallback",
        lambda *_args, **_kwargs: matchup,
    )
    monkeypatch.setattr(
        "app.utils.prediction_market_matching.extract_game_date_from_ticker",
        lambda *_args, **_kwargs: None,
    )

    closed_market = _market(market_id=1)
    active_unmatched_market = _market(market_id=2)
    now = datetime.now(timezone.utc)

    db = AsyncMock()
    db.execute.side_effect = [
        _result(),  # SET LOCAL statement_timeout
        _result(scalars=[closed_market, active_unmatched_market]),
        _result(
            rows=[
                _event_row(status="completed", commence_time=now - timedelta(hours=10)),
            ]
        ),
        _result(
            rows=[
                _event_row(status="scheduled", commence_time=now + timedelta(hours=2)),
            ]
        ),
    ]

    response = await prediction_market_tier1_gaps(request=_mock_request(), secret="test-secret", db=db)

    assert response["total_tier1_gaps"] == 1
    assert response["excluded_closed_game_markets"] == 1
    assert response["all_gaps"][0]["id"] == active_unmatched_market.id
    assert response["all_gaps"][0]["failure"] == "event_found_but_scoring_rejected"

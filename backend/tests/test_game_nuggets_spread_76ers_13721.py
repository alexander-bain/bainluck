"""Guard tests for #13721: team names carrying digits never become spread thresholds."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.routes.events import _extract_period_threshold, _extract_threshold
from app.utils.game_nuggets import _parse_spread_threshold, rank_game_nuggets


def _fresh_ts(hours_ago: float = 0.25) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


@pytest.mark.parametrize(
    "text, expected",
    [
        ("76ers", None),
        ("Philadelphia 76ers", None),
        ("San Francisco 49ers", None),
        ("SF 49ers", None),
        ("Over 224.5", 224.5),
        ("Under 218.5", 218.5),
        ("Michigan: 100+", 100.0),
        ("76ers -1.5", 1.5),
        ("76ers wins by over 1.5 points", 1.5),
        ("Paul vs. Alcaraz: Set 1 Games O/U 9.5", 9.5),
    ],
)
def test_extract_threshold_skips_digits_inside_team_names(text: str, expected: float | None):
    assert _extract_threshold(text) == expected


@pytest.mark.parametrize(
    "text, market_type, expected",
    [
        ("Philadelphia 76ers", "quarter_spread", None),
        ("Philadelphia 76ers wins 1st Quarter", "quarter_winner", None),
        ("SF 49ers wins 2H by over 3.5 points", "half_spread", 3.5),
        ("76ers 1st Quarter -1.5", "quarter_spread", 1.5),
    ],
)
def test_extract_period_threshold_with_digit_team_names(
    text: str, market_type: str, expected: float | None
):
    assert _extract_period_threshold(text, market_type) == expected


@pytest.mark.parametrize("injected_threshold", [None, 76.0])
def test_parse_spread_threshold_ignores_76_and_reads_market_spread(
    injected_threshold: float | None,
):
    row_sixers = {
        "market_name": "Spread: 76ers (-1.5)",
        "outcome_name": "Philadelphia 76ers",
        "threshold": injected_threshold,
    }
    assert (
        _parse_spread_threshold(
            row_sixers,
            subj_name="Philadelphia 76ers",
            home_team="Philadelphia 76ers",
            away_team="Miami Heat",
        )
        == -1.5
    )

    row_heat = {
        "market_name": "Spread: 76ers (-1.5)",
        "outcome_name": "Miami Heat",
        "threshold": None,
    }
    assert (
        _parse_spread_threshold(
            row_heat,
            subj_name="Miami Heat",
            home_team="Philadelphia 76ers",
            away_team="Miami Heat",
        )
        == 1.5
    )


def test_rank_game_nuggets_uses_1_5_spread_not_76_for_76ers():
    now = datetime.now(timezone.utc)
    res = rank_game_nuggets(
        event_info={
            "event_id": 15197759,
            "home_team": "Philadelphia 76ers",
            "away_team": "Miami Heat",
            "sport": "basketball_nba",
            "status": "scheduled",
            "commence_time": (now + timedelta(hours=3)).isoformat(),
        },
        game_markets={
            "spreads": [
                {
                    "_market_id": 9901,
                    "market_name": "Spread: 76ers (-1.5)",
                    "outcome_name": "Philadelphia 76ers",
                    "probability": 0.50,
                    "threshold": _extract_threshold("Philadelphia 76ers"),
                    "observed_at": _fresh_ts(),
                },
                {
                    "_market_id": 9901,
                    "market_name": "Spread: 76ers (-1.5)",
                    "outcome_name": "Miami Heat",
                    "probability": 0.50,
                    "threshold": _extract_threshold("Miami Heat"),
                    "observed_at": _fresh_ts(),
                },
            ],
        },
        related_futures={},
        team_progression={},
        now=now,
    )
    claims = [n["claim"] for n in res["nuggets"]]
    assert claims == ["Philadelphia 76ers win by 2 or more"], claims
    assert all("fewer than 76" not in claim for claim in claims), claims


def test_rank_game_nuggets_49ers_spread_also_ignores_team_digits():
    now = datetime.now(timezone.utc)
    res = rank_game_nuggets(
        event_info={
            "event_id": 15197760,
            "home_team": "San Francisco 49ers",
            "away_team": "Arizona Cardinals",
            "sport": "americanfootball_nfl",
            "status": "scheduled",
            "commence_time": (now + timedelta(hours=3)).isoformat(),
        },
        game_markets={
            "spreads": [
                {
                    "_market_id": 9902,
                    "market_name": "Spread: 49ers (-3.5)",
                    "outcome_name": "San Francisco 49ers",
                    "probability": 0.52,
                    "threshold": 49.0,  # Guard even if cached threshold held 49
                    "observed_at": _fresh_ts(),
                },
            ],
        },
        related_futures={},
        team_progression={},
        now=now,
    )
    claims = [n["claim"] for n in res["nuggets"]]
    assert claims == ["San Francisco 49ers win by 4 or more"], claims
    assert all("fewer than 49" not in claim for claim in claims), claims

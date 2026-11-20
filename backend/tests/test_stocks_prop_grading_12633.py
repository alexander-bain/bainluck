"""A combined steals-and-blocks prop must not grade from blocks alone."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.routes.events import (
    _build_game_markets,
    _build_prop_grade_context,
    _grade_settled_prop,
)
from tests.test_event_props_matrix_10236 import _db, _event, _market, _outcome

# Public Boston–Detroit audit: all six rungs resolve Yes at the venue, but
# the reader selected only blocks and published Lost. Both legs are retained.
CASES = [
    ("Jalen Duren", 1, 1, 2),
    ("Cade Cunningham", 1, 1, 2),
    ("Paul George", 5, 0, 2),
    ("Paul George", 5, 0, 3),
    ("Paul George", 5, 0, 4),
    ("Mitchell Robinson", 1, 2, 3),
]


def grade(stats, *, name="Boston vs Detroit: Steals + Blocks", threshold=2, won=None):
    context = _build_prop_grade_context(
        SimpleNamespace(box_score_data={"players": {"Paul George": stats}})
    )
    market = SimpleNamespace(name=name, external_id="KXNBASTOCK-audit")
    outcome = SimpleNamespace(
        name=f"Paul George: {threshold}+",
        is_winner=won,
        resolution_source="api_settlement" if won is not None else None,
        current_probability=float(won) if won is not None else 0.4,
    )
    return _grade_settled_prop(True, context, market, outcome, threshold, False)


@pytest.mark.parametrize("player,steals,blocks,threshold", CASES)
def test_proved_stock_winners_keep_both_stats_on_the_served_row(
    player, steals, blocks, threshold
):
    now = datetime.now(timezone.utc)
    commence = now - timedelta(hours=6)
    event = _event(status="completed", commence=commence)
    event.sport.key = "basketball_nba"
    event.home_team_name, event.away_team_name = "Detroit Pistons", "Boston Celtics"
    event.home_score, event.away_score = 109, 118
    event.period = None
    event.completed_at = now - timedelta(hours=3)
    event.score_source = "espn"
    event.box_score_data = {
        "source": "espn",
        "players": {player: {"steals": steals, "blocks": blocks}},
    }
    market = _market(
        id=67947722,
        name="Boston vs Detroit: Steals + Blocks",
        source="kalshi",
        commence=commence,
    )
    market.external_id = "KXNBASTOCK-audit"
    market.llm_sport_category = "basketball"
    market.status = "resolved"
    outcome = _outcome(
        id=255039331,
        market_id=market.id,
        name=f"{player}: {threshold}+",
        prob=1.0,
    )
    outcome.is_winner = True
    outcome.resolution_source = "api_settlement"
    page, _, _ = asyncio.run(
        _build_game_markets(
            event.id, _db(event, [market], [outcome], {outcome.id: now})
        )
    )
    (row,) = page["player_props"]
    assert row["actual"] == steals + blocks
    assert row["hit"] is True
    assert row["is_winner"] is True
    assert row["source_mark"]["settled"]["result"] == "Won"


@pytest.mark.parametrize(
    "stats", [{"blocks": 1}, {"steals": 1}, {"steals": None, "blocks": 1}]
)
def test_a_missing_leg_does_not_become_a_partial_actual(stats):
    result = grade(stats)
    assert result["actual"] is None
    assert result["hit"] is None


def test_an_incomplete_box_can_keep_a_proved_venue_result_without_an_actual():
    result = grade({"blocks": 1}, won=True)
    assert result["actual"] is None
    assert result["hit"] is True


@pytest.mark.parametrize("stat,expected", [("Steals", 5), ("Blocks", 0)])
def test_single_stat_props_still_grade_their_own_stat(stat, expected):
    result = grade({"steals": 5, "blocks": 0}, name=f"Boston vs Detroit: {stat}")
    assert result["actual"] == expected
    assert result["hit"] is (expected >= 2)


def test_known_zero_legs_make_a_real_zero():
    result = grade({"steals": 0, "blocks": 0})
    assert result["actual"] == 0
    assert result["hit"] is False

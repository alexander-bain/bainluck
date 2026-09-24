"""#8381 — a cup's race/path chart is the two teams, never a golfer field.

Seen on production 2026-09-24 08:20Z: `GET /api/event/presidents-cup` served a
Team USA 0.835 / Team World 0.125 hero with `evolution_market_id = 58728412`,
Kalshi's "Golfers to compete in the Presidents Cup this year" (20 golfers). The
live listing routes the real team market (16757297 "Presidents Cup Winner",
Team USA / Team World / Tie) into `h2h_matchups`, so the cup had no winner group
and the route's last-resort `market_ids[0]` fallback picked the compete field.

After the Sep 27 settle the page's settled hero draws
`SettledPathChart(marketId=evolution_market_id)` — golfer lines under a team
champion. And a completed cup is worse: production also holds a minted DataGolf
"Presidents Cup - Winner" with 132 golfer outcomes, which is exactly the shape
the winner ranking prefers. So the fix is that a cup never enters the golfer
ranking at all, on either road.

The specimens below are the production ids and names, so a reader can check
them against `futures_markets` directly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects import postgresql

from app.routes import golf as golf_route
from app.utils.golf_evolution_market import (
    is_team_side_pair,
    select_team_match_play_evolution_market,
)

COMPETE = (58728412, "Golfers to compete in the Presidents Cup this year")
TEAM = (16757297, "Presidents Cup Winner")
DG_WIN = (61720777, "Presidents Cup - Winner")

TEAM_PAIR = {
    "market_id": TEAM[0],
    "source": "kalshi",
    "golfer_a": {"name": "Team USA", "probability": 0.835},
    "golfer_b": {"name": "Team World", "probability": 0.125},
}
# During a cup the same list carries the singles, and the route sorts h2h by
# closeness — so the tight singles pair sorts FIRST, ahead of the team market.
SINGLES_PAIR = {
    "market_id": 70000001,
    "source": "kalshi",
    "golfer_a": {"name": "Scottie Scheffler", "probability": 0.51},
    "golfer_b": {"name": "Sungjae Im", "probability": 0.49},
}

GOLFERS_20 = [f"Golfer {i}" for i in range(20)]
GOLFERS_132 = [f"Player {i}" for i in range(132)]


# ---------------------------------------------------------------------------
# The pure pick.
# ---------------------------------------------------------------------------


class TestTheCupPick:
    def test_live_cup_picks_the_team_market_from_h2h_behind_a_closer_singles_pair(self):
        assert select_team_match_play_evolution_market(
            [SINGLES_PAIR, TEAM_PAIR], [COMPETE[0]], {}
        ) == TEAM[0]

    def test_cup_with_no_team_market_is_none_not_the_compete_field(self):
        assert select_team_match_play_evolution_market(
            [SINGLES_PAIR], [COMPETE[0]], {COMPETE[0]: GOLFERS_20}
        ) is None

    def test_completed_cup_reads_the_team_market_off_its_outcomes(self):
        names = {
            DG_WIN[0]: GOLFERS_132,
            COMPETE[0]: GOLFERS_20,
            TEAM[0]: ["Team USA", "Team World", "Tie"],
        }
        assert select_team_match_play_evolution_market(
            [], [DG_WIN[0], COMPETE[0], TEAM[0]], names
        ) == TEAM[0]

    @pytest.mark.parametrize(
        "names, expected",
        [
            (["Team USA", "Team World", "Tie"], True),
            (["Team USA", "Team World"], True),
            (["Team Europe", "Team USA"], True),
            (["Team USA", "USA"], False),  # one side against itself
            (["Team USA", "Scottie Scheffler"], False),  # a person is never a side
            (["Scottie Scheffler", "Sungjae Im"], False),
            (["Team USA", "Team World", "Team Europe"], False),
            (["Yes", "No"], False),
            ([], False),
        ],
    )
    def test_team_side_pair(self, names, expected):
        assert is_team_side_pair(names) is expected


# ---------------------------------------------------------------------------
# The route, end to end over a mocked session.
# ---------------------------------------------------------------------------


def _tournament(key, slug, markets, h2h):
    return {
        "name": slug.replace("-", " ").title(),
        "slug": slug,
        "key": key,
        "is_major": False,
        "is_womens": False,
        "start_date": "2026-09-24T00:00:00+00:00",
        "end_date": "2026-09-27T00:00:00+00:00",
        "venue": None,
        "location": None,
        "schedule_status": "upcoming",
        "commence_time": "2026-09-24T00:00:00+00:00",
        "resolution_date": "2026-09-27T00:00:00+00:00",
        "golfers": [],
        "market_ids": [mid for mid, _ in markets],
        "market_names": [name for _, name in markets],
        "market_sources": ["kalshi"],
        "h2h_matchups": list(h2h),
    }


def _listing(tournament):
    return {
        "tournaments": [tournament],
        "biggest_movers": [],
        "upcoming_events": [],
        "current_event": None,
        "total_tournaments": 1,
        "total_golfers": 0,
        "pga_schedule": [],
    }


def _is_outcome_name_select(statement) -> bool:
    try:
        sql = " ".join(str(statement.compile(dialect=postgresql.dialect())).split())
    except Exception:  # pragma: no cover
        return False
    return sql.startswith(
        "SELECT futures_outcomes.market_id, futures_outcomes.name FROM futures_outcomes"
    )


async def _evolution_id(client, mock_db, monkeypatch, tournament, outcome_rows=()):
    empty = mock_db.execute.return_value

    def _result_for(statement, *a, **kw):
        if outcome_rows and _is_outcome_name_select(statement):
            r = MagicMock()
            r.all.return_value = list(outcome_rows)
            return r
        return empty

    mock_db.execute.side_effect = _result_for

    async def _build(db):
        return _listing(tournament)

    monkeypatch.setattr(golf_route, "get_golf", _build)
    resp = await client.get(f"/api/golf/tournaments/{tournament['slug']}")
    assert resp.status_code == 200, resp.text
    return resp.json()["evolution_market_id"]


class TestTheRoute:
    async def test_live_presidents_cup_charts_the_team_market(self, client, mock_db, monkeypatch):
        t = _tournament("presidents_cup", "presidents-cup", [COMPETE], [SINGLES_PAIR, TEAM_PAIR])
        assert await _evolution_id(client, mock_db, monkeypatch, t) == TEAM[0]

    async def test_cup_without_a_team_market_charts_nothing(self, client, mock_db, monkeypatch):
        t = _tournament("presidents_cup", "presidents-cup", [COMPETE], [SINGLES_PAIR])
        rows = [(COMPETE[0], n) for n in GOLFERS_20]
        assert await _evolution_id(client, mock_db, monkeypatch, t, rows) is None

    async def test_completed_cup_charts_the_team_market_not_the_132_golfer_winner(
        self, client, mock_db, monkeypatch
    ):
        t = _tournament("presidents_cup", "presidents-cup", [DG_WIN, COMPETE, TEAM], [])
        rows = (
            [(DG_WIN[0], n) for n in GOLFERS_132]
            + [(COMPETE[0], n) for n in GOLFERS_20]
            + [(TEAM[0], n) for n in ("Team USA", "Team World", "Tie")]
        )
        assert await _evolution_id(client, mock_db, monkeypatch, t, rows) == TEAM[0]

    async def test_stroke_play_keeps_its_fallback(self, client, mock_db, monkeypatch):
        """Control: a stroke-play event with no ranked winner still falls back to
        `market_ids[0]`, and never pays the cup's outcome read."""
        t = _tournament(
            "tour_championship", "tour-championship",
            [(900001, "Tour Championship Winner"), (900002, "Tour Championship Top 5")],
            [SINGLES_PAIR],
        )
        assert await _evolution_id(client, mock_db, monkeypatch, t) == 900001
        assert not any(
            c.args and _is_outcome_name_select(c.args[0])
            for c in mock_db.execute.call_args_list
        )

"""#10590 — a Polymarket TEAM total is never graded against the GAME total.

`_resolve_polymarket_total_from_scores` (#140) grades "{A} vs. {B}: O/U N"
against ``home_score + away_score``. Its old regex, ``:\\s*o/u\\s*N$``, refused a
qualifier after the colon and nothing before it, so "San Diego Padres Team
Total: O/U 4.5" on a 3–4 final was stored Over-won (7 > 4.5) while the venue
priced Under at 0.9995. Production names in the same hole (2026-10-06):
team totals, NCAAF/NFL team stat totals, esports "Games Total", cricket
over-lines. The names below are verbatim from production.
"""

from unittest.mock import MagicMock

import pytest

import app.tasks.backfill_winners as bw
from app.tasks.backfill_winners import _poly_total_line


@pytest.mark.parametrize("name", [
    # the specimen (event 15323985, markets 64157611/12/16/17)
    "San Diego Padres Team Total: O/U 3.5",
    "San Diego Padres Team Total: O/U 4.5",
    "Milwaukee Brewers Team Total: O/U 4.5",
    "Milwaukee Brewers Team Total: O/U 5.5",
    # the same hole, other shapes
    "Alabama Total Rushing Yards: O/U 125.5",
    "Bears Total Touchdowns: O/U 1.5",
    "Washington State Field Goals Made: O/U 0.5",
    "Games Total: O/U 2.5",
    "T20 1st Innings 6 Overs Line: O/U 0.5",
    # both sides named, still not the game total
    "Padres vs. Brewers Team Total: O/U 4.5",
    "Bears vs. Packers Total Touchdowns: O/U 4.5",
    # a second colon is a scope the grader must not guess
    "MLB: Padres vs. Brewers: O/U 7.5",
])
def test_a_scoped_total_is_refused_not_graded_on_the_game_score(name):
    assert _poly_total_line(name) is None, name


@pytest.mark.parametrize("name,line", [
    ("Stars vs. Maple Leafs: O/U 6.5", 6.5),
    ("Bowling Green vs. Miami (OH): O/U 53.5", 53.5),
    ("Mattersburger SV 2020 vs. First Vienna FC 1894: O/U 3.5", 3.5),
    ("AIK vs. IF Brommapojkarna: O/U 1.5", 1.5),
    ("San Diego Padres vs. Milwaukee Brewers: O/U 6.5", 6.5),
    ("Yankees vs Red Sox: O/U 8", 8.0),
])
def test_the_full_game_total_still_parses(name, line):
    assert _poly_total_line(name) == line


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


def _row(**kw):
    m = MagicMock()
    for k, v in kw.items():
        setattr(m, k, v)
    return m


async def test_a_three_four_final_grades_the_game_total_and_leaves_the_team_total(
        monkeypatch):
    """SD 3 – MIL 4. The full-game O/U 6.5 must grade Over (7 > 6.5); the
    Padres team total O/U 4.5 must not be written at all — the old code wrote
    Over-won on it. A refused market is left for the venue's settlement."""
    candidates = [
        _row(market_id=1, market_name="San Diego Padres vs. Milwaukee Brewers: O/U 6.5",
             home_score=4, away_score=3),
        _row(market_id=2, market_name="San Diego Padres Team Total: O/U 4.5",
             home_score=4, away_score=3),
    ]
    legs = {
        1: [_row(id=11, name="Over"), _row(id=12, name="Under")],
        2: [_row(id=21, name="Over"), _row(id=22, name="Under")],
    }
    writes = {}

    class _Session:
        async def execute(self, stmt, params=None):
            sql = str(getattr(stmt, "text", stmt))
            if "source = 'polymarket'" in sql:
                return _Result(candidates)
            if "FROM futures_outcomes WHERE market_id = :mid" in sql:
                return _Result(legs[params["mid"]])
            if sql.lstrip().startswith("UPDATE futures_outcomes"):
                writes[params["oid"]] = params["won"]
            return MagicMock(rowcount=1)

        async def commit(self):
            return None

    class _CM:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(bw, "get_task_session", lambda: _CM())
    stats = await bw._resolve_polymarket_total_from_scores()

    assert writes == {11: True, 12: False}, writes
    assert stats["graded"] == 1
    assert stats["no_parse"] == 1

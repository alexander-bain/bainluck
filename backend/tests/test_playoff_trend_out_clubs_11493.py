"""#11493 — a club the grid has put out is not drawn on the trend chart.

Production specimen, ``/api/playoffs/mlb`` 2026-10-23 06:13Z (main v5886): the
grid marked 28 clubs ``championship.state = "eliminated"`` and printed ✕ for
each, while ``trend_chart.outcomes`` carried ten rows — Milwaukee 0.6375,
Tampa Bay 0.3665, then eight eliminated clubs at the venue's leftover 0.001. The
legend printed the Reds, Orioles, White Sox, Athletics, Braves and Red Sox at
"0%" beside the two live clubs; the Reds, Orioles and Athletics never made the
playoffs. The WNBA legend, built on the same path, listed only its 2 finalists.
"""

from app.routes.playoffs import _GRID_OUT_STATES, _collect_trend_outcomes


def _team(name: str, state: str | None) -> dict:
    cells = {} if state is None else {"championship": {"state": state}}
    return {"name": name, "cells": cells}


#: The order ``sort_teams_by_championship`` served on 2026-10-23: the two live
#: clubs, then eight eliminated ones inside the top-10 window.
_MLB_SPECIMEN = [
    _team("Milwaukee Brewers", "live"),
    _team("Tampa Bay Rays", "live"),
    _team("Cincinnati Reds", "eliminated"),
    _team("Baltimore Orioles", "eliminated"),
    _team("Chicago White Sox", "eliminated"),
    _team("Athletics", "eliminated"),
    _team("Atlanta Braves", "eliminated"),
    _team("Boston Red Sox", "eliminated"),
    _team("Arizona Diamondbacks", "eliminated"),
    _team("Chicago Cubs", "eliminated"),
]


def _grid_for(teams: list[dict]) -> dict:
    """One championship leg per club, outcome ids 1..N in team order."""
    return {
        t["name"].lower(): {"championship": [{"outcome_id": i, "source": "polymarket"}]}
        for i, t in enumerate(teams, start=1)
    }


def test_the_mlb_specimen_draws_only_the_two_live_clubs():
    ids, names = _collect_trend_outcomes(
        _MLB_SPECIMEN, _grid_for(_MLB_SPECIMEN), "championship", top=10
    )

    assert sorted(names.values()) == ["Milwaukee Brewers", "Tampa Bay Rays"], (
        "an eliminated club's leftover 0.1% quote was drawn as a 0% series "
        "beside the ✕ its own grid row prints"
    )
    assert ids == [1, 2]


def test_a_seat_an_out_club_would_take_goes_to_the_next_club_still_in_it():
    teams = [
        _team("Cincinnati Reds", "eliminated"),
        _team("Milwaukee Brewers", "live"),
        _team("Tampa Bay Rays", "live"),
    ]

    _, names = _collect_trend_outcomes(teams, _grid_for(teams), "championship", top=2)

    assert sorted(names.values()) == ["Milwaukee Brewers", "Tampa Bay Rays"], (
        "skipping an out club must not shrink the chart below top when a live "
        "club is waiting behind it"
    )


def test_top_still_caps_the_clubs_drawn():
    teams = [_team(f"Club {i}", "live") for i in range(5)]

    _, names = _collect_trend_outcomes(teams, _grid_for(teams), "championship", top=3)

    assert sorted(names.values()) == ["Club 0", "Club 1", "Club 2"]


def test_a_tournament_lost_cell_is_out_too():
    teams = [_team("Loser", "lost"), _team("Survivor", "live")]

    _, names = _collect_trend_outcomes(teams, _grid_for(teams), "championship", top=10)

    assert set(names.values()) == {"Survivor"}


def test_the_champion_keeps_its_series():
    """A won cell is decided but not OUT: the winner's journey is the chart."""
    teams = [_team("Champion", "won"), _team("Runner-up", "eliminated")]

    _, names = _collect_trend_outcomes(teams, _grid_for(teams), "championship", top=10)

    assert set(names.values()) == {"Champion"}
    assert "won" not in _GRID_OUT_STATES


def test_a_missing_or_absent_cell_is_not_read_as_out():
    """Only a decided result removes a club; an empty state is not a verdict."""
    teams = [
        _team("Source went dark", "missing"),
        _team("No championship cell", None),
        {"name": "Legacy row without cells"},
    ]

    _, names = _collect_trend_outcomes(teams, _grid_for(teams), "championship", top=10)

    assert set(names.values()) == {
        "Source went dark",
        "No championship cell",
        "Legacy row without cells",
    }


def test_only_the_championship_cell_decides():
    """Eliminated from the division is not eliminated from the title."""
    teams = [{"name": "Wild Card", "cells": {"division": {"state": "eliminated"},
                                             "championship": {"state": "live"}}}]

    _, names = _collect_trend_outcomes(teams, _grid_for(teams), "championship", top=10)

    assert set(names.values()) == {"Wild Card"}

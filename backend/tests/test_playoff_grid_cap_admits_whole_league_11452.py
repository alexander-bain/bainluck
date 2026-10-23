"""#11452 — a grid cap below the league's own membership drops real clubs.

`sort_teams_by_championship` sorts by champion price, then team_id presence,
then NAME, and cuts at `config.max_teams`. Once the champion column is decided
every eliminated club ties at the bottom, so a cap one seat short silently
removes the alphabetically-last club — whatever it did in the season. WNBA kept
its 2025 cap of 13 into the 15-club 2026 season and served /playoffs/wnba with
Toronto and Washington missing; Washington made the playoffs, so the decided
Make Playoffs column ticked 7 of the 8 teams that got in.

For a fixed-membership league the cap must admit every club. The sizes below
are the 2026 memberships; an expansion that outgrows a cap reddens here
instead of on a reader's screen.
"""

from app.config.league_configs import get_league_config
from app.utils.playoff_grid import sort_teams_by_championship

# slug -> clubs in the 2026 season (the configs' `season_pattern`).
LEAGUE_SIZES_2026 = {
    "nba": 30,
    "wnba": 15,
    "nhl": 32,
    "nfl": 32,
    "mlb": 30,
    "mls": 30,
    "epl": 20,
    "la-liga": 20,
    "bundesliga": 18,
    "champions-league": 36,
}


def test_every_fixed_membership_cap_admits_the_whole_league():
    short = {
        slug: (get_league_config(slug).max_teams, size)
        for slug, size in LEAGUE_SIZES_2026.items()
        if get_league_config(slug).max_teams < size
    }
    assert short == {}, f"max_teams below league size (cap, clubs): {short}"


def _decided_row(name: str, team_id: int) -> dict:
    return {
        "name": name,
        "team_id": team_id,
        "cells": {
            "make_playoffs": {"merged_probability": None, "state": "eliminated"},
            "championship": {"merged_probability": None, "state": "eliminated"},
        },
    }


def test_wnba_cap_keeps_toronto_and_washington_among_tied_eliminated_rows():
    # The production shape at 2026-10-22 18:30Z: two clubs still priced, the
    # other thirteen decided and tied, Toronto and Washington last by name.
    names = [
        "Chicago Sky", "Connecticut Sun", "Dallas Wings", "Indiana Fever",
        "Las Vegas Aces", "Los Angeles Sparks", "Minnesota Lynx",
        "New York Liberty", "Phoenix Mercury", "Portland Fire",
        "Seattle Storm", "Toronto Tempo", "Washington Mystics",
    ]
    teams = [_decided_row(n, 100 + i) for i, n in enumerate(names)]
    for name, p in (("Atlanta Dream", 0.78), ("Golden State Valkyries", 0.2253)):
        teams.append({
            "name": name,
            "team_id": 1 if name.startswith("A") else 2,
            "cells": {"championship": {"merged_probability": p, "state": "live"}},
        })

    cap = get_league_config("wnba").max_teams
    kept = [t["name"] for t in sort_teams_by_championship(teams, "championship", cap)]

    assert len(kept) == 15
    assert kept[:2] == ["Atlanta Dream", "Golden State Valkyries"]
    assert {"Toronto Tempo", "Washington Mystics"} <= set(kept)

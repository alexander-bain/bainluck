"""#10252 — an NHL overtime loss is a played game, and the hero says so.

Production, 2026-10-02 23:38Z, `/events/15322853` (Capitals @ Hurricanes) at
390px: the hero printed "Hurricanes 0-0, 1 pts". Carolina's row was right —
`current_record` `0-0-1`, the board `wins 0, losses 0, points 1,
home_record "0-0-1"` after a 1-0 overtime loss on 9/29 — but the board stores no
overtime-loss key, so `standings_show_no_games_played` called the team unplayed.
`record_text` then took the rollover branch and printed the board's `0-0`, and
the points clause added a plural to a single point.

Both rows below are the production values, verbatim, read the same minute.
Washington (0-0-0, its opener) is the control: it must stay unplayed and
unranked, or this fix has become #5377's blanket rank leak in reverse.
"""

from types import SimpleNamespace

from app.routes.events import _compute_standings_context
from app.utils.standings_shape import (
    public_standings,
    reconciled_record_and_standings,
    record_text,
    standings_show_no_games_played,
)

CAROLINA_STANDINGS = {
    "wins": 0,
    "losses": 0,
    "points": 1,
    "streak": "L1",
    "div_rank": 5,
    "division": "Metropolitan Division",
    "goals_for": 0,
    "conference": "Eastern Conference",
    "home_record": "0-0-1",
    "road_record": "0-0-0",
    "goals_against": 1,
}
CAROLINA_CURRENT_RECORD = "0-0-1"

WASHINGTON_STANDINGS = {
    "wins": 0,
    "losses": 0,
    "points": 0,
    "streak": "-",
    "div_rank": 7,
    "division": "Metropolitan Division",
    "goals_for": 0,
    "conference": "Eastern Conference",
    "home_record": "0-0-0",
    "road_record": "0-0-0",
    "goals_against": 0,
}
WASHINGTON_CURRENT_RECORD = "0-0-0"


def _team(standings, current_record):
    return SimpleNamespace(standings_data=standings, current_record=current_record)


class TestAnOvertimeLossIsAPlayedGame:
    def test_the_specimen_has_played_and_the_control_has_not(self):
        assert standings_show_no_games_played(CAROLINA_STANDINGS) is False
        assert standings_show_no_games_played(WASHINGTON_STANDINGS) is True

    def test_each_signal_proves_a_game_on_its_own(self):
        bare = {"wins": 0, "losses": 0}
        assert standings_show_no_games_played({**bare, "points": 1}) is False
        assert standings_show_no_games_played({**bare, "points": "2"}) is False
        assert standings_show_no_games_played({**bare, "home_record": "0-0-1"}) is False
        assert standings_show_no_games_played({**bare, "road_record": "0-0-2"}) is False
        # Siblings: zeros prove nothing, and a deduction is not a game.
        assert standings_show_no_games_played({**bare, "points": 0}) is True
        assert standings_show_no_games_played({**bare, "points": -3}) is True
        assert standings_show_no_games_played({**bare, "home_record": "0-0-0"}) is True
        assert standings_show_no_games_played({**bare, "road_record": "0-0"}) is True

    def test_an_unreadable_point_is_never_called_fresh(self):
        # Same contract as the record keys (#5377): what cannot be read is not
        # proof of freshness.
        assert standings_show_no_games_played({"wins": 0, "losses": 0, "points": "x"}) is False


class TestTheRecordKeepsItsOvertimeLoss:
    def test_record_text_serves_current_record_for_the_specimen(self):
        assert record_text(CAROLINA_CURRENT_RECORD, CAROLINA_STANDINGS) == "0-0-1"
        assert record_text(WASHINGTON_CURRENT_RECORD, WASHINGTON_STANDINGS) == "0-0"

    def test_the_team_card_composes_the_same_record(self):
        record, aligned = reconciled_record_and_standings(
            CAROLINA_CURRENT_RECORD, CAROLINA_STANDINGS
        )
        assert record == "0-0-1"
        assert (aligned["wins"], aligned["losses"], aligned["draws"]) == (0, 0, 1)

    def test_the_rank_is_served_once_a_game_is_played(self):
        assert public_standings(CAROLINA_STANDINGS).get("div_rank") == 5
        assert "div_rank" not in public_standings(WASHINGTON_STANDINGS)


class TestTheHeroLine:
    def test_the_hero_reads_the_specimen_whole(self):
        ctx = _compute_standings_context(
            _team(CAROLINA_STANDINGS, CAROLINA_CURRENT_RECORD),
            _team(WASHINGTON_STANDINGS, WASHINGTON_CURRENT_RECORD),
            "Carolina Hurricanes",
            "Washington Capitals",
        )
        assert ctx["home"] == "0-0-1, #5 Metropolitan, 1 pt"
        assert ctx["away"] == "0-0, 0 pts"

    def test_more_than_one_point_stays_plural(self):
        later = {**CAROLINA_STANDINGS, "wins": 3, "losses": 2, "points": 7}
        ctx = _compute_standings_context(
            _team(later, "3-2-1"), None, "Carolina Hurricanes", "Washington Capitals"
        )
        assert ctx["home"] == "3-2-1, #5 Metropolitan, 7 pts"


class TestTheHeroDivisionFitsItsColumn:
    def test_only_the_nhl_suffix_is_dropped(self):
        # The other leagues' boards already spell the bare name; they must be
        # served exactly as before.
        for division, shown in (
            ("Metropolitan Division", "Metropolitan"),
            ("AFC South", "AFC South"),
            ("West", "West"),
            ("Southeast", "Southeast"),
        ):
            row = {**CAROLINA_STANDINGS, "wins": 3, "losses": 2, "division": division}
            row.pop("points")
            ctx = _compute_standings_context(_team(row, "3-2"), None, "A", "B")
            assert ctx["home"] == f"3-2, #5 {shown}"

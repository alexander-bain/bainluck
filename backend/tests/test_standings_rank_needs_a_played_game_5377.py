"""#5377 — a rank is not claimed for a team that has not played.

Measured on production 2026-09-11, the morning before NFL week 1: 30 of the 32
teams were 0-0 and ALL 30 carried a `div_rank` 1-4. The AFC South's four
identical 0-0 records were served as Titans #1, Colts #2, Jaguars #3, Texans
#4, so the Sunday hero read "Texans 0-0, #4 AFC South" and the team page read
"#4 in AFC South". Both were LOOK-verified at 390px. The only two teams with an
earned rank were the two who had played Thursday (NE 0-1, SEA 1-0).

Neither the writer nor the label was wrong — `statpal_sync` stores StatPal's
real division `position` and #4811 pairs it with `division`. What was wrong was
the ASSERTION: at zero games played every team in the division is tied, and a
tie is not a ranking.

EVERY TEST HERE DRIVES BOTH DIRECTIONS. A suite that only asserted "no rank at
0-0" would pass against a blanket rank suppression, which would be a much worse
bug than the one being fixed — the rank is correct and wanted for all but the
first week of a season. So each case that asserts a rank is withheld has a
sibling asserting an earned rank survives.
"""

from types import SimpleNamespace

from app.routes.events import _compute_standings_context
from app.utils.standings_shape import public_standings, standings_show_no_games_played


# The 30 NFL rows as production held them the morning before week 1.
FRESH_SEASON_ROW = {
    "conference": "American Football Conference",
    "division": "AFC South",
    "div_rank": 4,
    "wins": 0,
    "losses": 0,
}

# New England after Thursday's opener — the control. Same shape, one game.
PLAYED_ONE_ROW = {
    "conference": "American Football Conference",
    "division": "AFC East",
    "div_rank": 4,
    "wins": 0,
    "losses": 1,
}


def _team(standings):
    return SimpleNamespace(standings_data=standings)


class TestStandingsShowNoGamesPlayed:
    def test_true_only_on_a_record_that_proves_it(self):
        assert standings_show_no_games_played(FRESH_SEASON_ROW) is True
        # The control: one loss is a played game.
        assert standings_show_no_games_played(PLAYED_ONE_ROW) is False

    def test_a_draw_is_a_played_game_in_both_spellings(self):
        for key in ("draws", "ties"):
            assert standings_show_no_games_played(
                {"wins": 0, "losses": 0, key: 1}
            ) is False
            # Sibling: the key present and zero does NOT disprove freshness.
            assert standings_show_no_games_played(
                {"wins": 0, "losses": 0, key: 0}
            ) is True

    def test_an_unreadable_record_is_never_called_fresh(self):
        # Each of these could only be called "0 games played" by assuming it.
        # The rule suppresses what it can demonstrate, never what it failed to
        # measure — so every one of them is False, not True.
        for row in (
            {"div_rank": 4},                                # no record at all
            {"wins": 0},                                    # half a record
            {"losses": 0},
            {"wins": "", "losses": ""},                     # will not coerce
            {"wins": None, "losses": None},
            {"wins": 0, "losses": 0, "draws": "x"},
            "not a dict",
            None,
        ):
            assert standings_show_no_games_played(row) is False

    def test_string_zeroes_still_prove_it(self):
        # JSONB has handed us both; the rule is about the value, not its type.
        assert standings_show_no_games_played({"wins": "0", "losses": "0"}) is True


class TestPublicStandings:
    def test_withholds_the_rank_before_a_game_and_serves_it_after(self):
        assert "div_rank" not in public_standings(FRESH_SEASON_ROW)
        # Not vacuous: the rest of the blob is still served.
        assert public_standings(FRESH_SEASON_ROW)["division"] == "AFC South"
        assert public_standings(FRESH_SEASON_ROW)["wins"] == 0
        # The control — one played game and the SAME key comes back.
        assert public_standings(PLAYED_ONE_ROW)["div_rank"] == 4

    def test_league_rank_follows_the_same_rule(self):
        fresh = {"wins": 0, "losses": 0, "league_rank": 7}
        assert "league_rank" not in public_standings(fresh)
        assert public_standings({**fresh, "wins": 1})["league_rank"] == 7

    def test_does_not_mutate_the_caller_s_dict(self):
        # A live SQLAlchemy JSONB value; mutating one in place is gotcha #4.
        row = dict(FRESH_SEASON_ROW)
        public_standings(row)
        assert row["div_rank"] == 4

    def test_a_played_row_is_returned_untouched_and_uncopied(self):
        # The allocation-free common path must survive the new rule.
        assert public_standings(PLAYED_ONE_ROW) is PLAYED_ONE_ROW


class TestStandingsContext:
    def test_the_hero_line_drops_the_rank_before_a_game(self):
        out = _compute_standings_context(
            _team(FRESH_SEASON_ROW), _team(PLAYED_ONE_ROW), "Texans", "Patriots"
        )
        # The exact string production served on 2026-09-11.
        assert out["home"] == "0-0"
        assert "#" not in out["home"]
        # The control, in the SAME call: the team that played keeps its rank,
        # so this cannot pass by suppressing every rank.
        assert out["away"] == "0-1, #4 AFC East"

    def test_division_rivals_stakes_is_not_claimed_from_a_preseason_rank(self):
        # Two 0-0 teams in one division: the ranks are adjacent, so the old
        # `abs(hr - ar) <= 2` rule fired and badged an arbitrary ordering as a
        # standings story.
        home = {**FRESH_SEASON_ROW, "div_rank": 1}
        away = {**FRESH_SEASON_ROW, "div_rank": 2}
        out = _compute_standings_context(_team(home), _team(away), "T", "C")
        assert "stakes" not in out
        # Sibling: once both have played, the badge is earned and returns.
        played_home = {**home, "wins": 1}
        played_away = {**away, "losses": 1}
        out = _compute_standings_context(
            _team(played_home), _team(played_away), "T", "C"
        )
        assert out["stakes"] == "Division rivals"

"""#5520 — the event hero prints the team's CURRENT record, not yesterday's.

Two columns on `teams` answer "what is this team's record", and they disagree
constantly. `current_record` is stamped when a game completes; `standings_data`
carries the once-daily StatPal board. `_compute_standings_context` read the
snapshot, so every event hero served a record its own row already knew was out
of date.

Measured in production 2026-09-19 03:45Z, mid-pennant-race:

  * all 30 MLB rows carried ONE `standings_updated_at` — 2026-09-18 08:00:00Z,
    19.7 hours old;
  * 25 of the 30 disagreed with `current_record`;
  * `current_record` was ahead in 25 of 25 — never behind, never a different
    split at the same game count. A lag is monotone like that; corruption would
    scatter. #5520 checked two rows against ESPN's own `Overall Record`
    independently and `current_record` won both.

The photographed specimen is the Dodgers/Giants game (event 15314181,
`/events/15314181` at 390px): the hero read "Dodgers 92-60, #1 West" while the
same row's `current_record` said 93-60.

EVERY CASE HERE DRIVES BOTH DIRECTIONS. A suite that only asserted "prefer
`current_record`" would pass against a change that ignored `standings_data`
entirely — which would blank the record on every row that has no
`current_record`, a worse bug than the one being fixed. So each case asserting
the fresh column wins has a sibling asserting the snapshot still serves when
the fresh column cannot.
"""

from types import SimpleNamespace

from app.routes.events import _compute_standings_context
from app.utils.standings_shape import public_standings, record_text

# The Dodgers row exactly as production held it at 03:45Z.
DODGERS_SNAPSHOT = {"wins": 92, "losses": 60, "div_rank": 1, "division": "West"}
DODGERS_CURRENT = "93-60"

# The Giants — one of the five MLB rows that AGREED. The control that proves
# the change is a no-op wherever the two columns already match.
GIANTS_SNAPSHOT = {"wins": 64, "losses": 89, "div_rank": 4, "division": "West"}
GIANTS_CURRENT = "64-89"


def _team(standings, current_record=None):
    return SimpleNamespace(standings_data=standings, current_record=current_record)


class TestRecordText:
    def test_the_fresh_column_wins_and_the_stale_one_is_not_printed(self):
        out = record_text(DODGERS_CURRENT, DODGERS_SNAPSHOT)
        assert out == "93-60"
        # Non-vacuous: the value the hero actually served must be GONE, not
        # merely "not asserted". This is the byte that was wrong on production.
        assert out != "92-60"

    def test_the_snapshot_still_serves_when_there_is_no_current_record(self):
        # The sibling. Without this, blanking the column would pass above.
        assert record_text(None, DODGERS_SNAPSHOT) == "92-60"
        assert record_text(None, {"wins": 0, "losses": 0}) == "0-0"

    def test_a_draws_sport_keeps_its_third_number_from_either_column(self):
        assert record_text(None, {"wins": 3, "losses": 1, "draws": 2}) == "3-1-2"
        assert record_text(None, {"wins": 3, "losses": 1, "ties": 2}) == "3-1-2"
        # And a three-part `current_record` is passed through, not truncated.
        assert record_text("4-1-2", {"wins": 3, "losses": 1, "draws": 2}) == "4-1-2"

    def test_an_unreadable_current_record_falls_back_instead_of_printing_junk(self):
        # Empty beats wrong (notice 34): none of these may reach a reader.
        for junk in (
            "",
            "   ",
            "TBD",
            "9-",
            "-9",
            "1-2-3-4",
            "1.5-2",
            "W2-L1",
            93,
            [],
            {},
        ):
            assert record_text(junk, DODGERS_SNAPSHOT) == "92-60"

    def test_no_record_at_all_returns_none_rather_than_a_hyphen(self):
        assert record_text(None, {}) is None
        assert record_text(None, {"div_rank": 1}) is None
        assert record_text(None, None) is None
        # Sibling: a usable `current_record` still serves with no snapshot.
        assert record_text("93-60", None) == "93-60"

    def test_a_rolled_over_board_keeps_its_zeros_instead_of_last_season(self):
        """NHL, between seasons — where "prefer current_record" is WRONG.

        The board has started the new season at 0-0 while `current_record`
        still holds last season's finished 82 games. Anaheim exactly as
        production held it, 2026-09-19 03:45Z. Printing 43-33-6 for a league
        that has played no games is #6266's defect; 34 of the 42 NHL rows are
        in this state.
        """
        anaheim = {"wins": 0, "losses": 0, "div_rank": 6, "division": "Pacific"}
        assert record_text("43-33-6", anaheim) == "0-0"
        # Sibling, so this is not "always distrust a 3-part record": the same
        # shape wins once the board itself shows the season under way.
        under_way = {"wins": 2, "losses": 1, "division": "Pacific"}
        assert record_text("3-1-1", under_way) == "3-1-1"

    def test_a_current_record_behind_the_board_loses_to_the_board(self):
        """NBA, after the season — where the lag runs the OTHER way.

        Brooklyn as production held it: `current_record` stopped at 77 games,
        the board has the complete 82. Twelve of the 33 NBA rows are behind
        like this, so a blanket preference would take the stale half in every
        one of them.
        """
        brooklyn = {"wins": 20, "losses": 62, "div_rank": 5, "division": "Atlantic"}
        assert record_text("18-59", brooklyn) == "20-62"
        # Sibling: equal game counts are not "behind" — a pure correction to
        # the win/loss split at the same total is taken.
        assert record_text("21-61", brooklyn) == "21-61"

    def test_it_never_mutates_the_live_jsonb_argument(self):
        # These dicts are live SQLAlchemy JSONB values (gotcha #4).
        before = dict(DODGERS_SNAPSHOT)
        record_text(DODGERS_CURRENT, DODGERS_SNAPSHOT)
        assert DODGERS_SNAPSHOT == before


class TestHeroStandingsContext:
    def test_the_photographed_specimen_now_reads_the_fresh_record(self):
        out = _compute_standings_context(
            _team(DODGERS_SNAPSHOT, DODGERS_CURRENT),
            _team(GIANTS_SNAPSHOT, GIANTS_CURRENT),
            "Dodgers",
            "Giants",
        )
        # What production served at 03:45Z was "92-60, #1 West".
        assert out["home"] == "93-60, #1 West"
        assert "92-60" not in out["home"]
        # The control, in the SAME call: the row whose columns agreed is
        # untouched, so this is not a blanket rewrite of the hero.
        assert out["away"] == "64-89, #4 West"

    def test_the_rank_still_comes_from_the_snapshot_and_keeps_its_vintage(self):
        # The fresh record must not drag the rank along with it or drop it.
        out = _compute_standings_context(
            _team(DODGERS_SNAPSHOT, DODGERS_CURRENT), None, "Dodgers", "Giants"
        )
        assert out["home"] == "93-60, #1 West"
        assert public_standings(DODGERS_SNAPSHOT)["div_rank"] == 1

    def test_the_5377_guard_still_fires_on_the_column_it_always_read(self):
        # A no-games-played board earns no rank, and taking the record from
        # the other column must not smuggle one back in.
        fresh_season = {"wins": 0, "losses": 0, "div_rank": 4, "division": "NFC West"}
        out = _compute_standings_context(
            _team(fresh_season, "0-1"), None, "Rams", "Seahawks"
        )
        assert "#" not in out["home"]
        # Sibling: once the board itself shows a played game the rank returns,
        # and the fresher record is taken alongside it.
        played = {"wins": 1, "losses": 1, "div_rank": 4, "division": "NFC West"}
        out = _compute_standings_context(_team(played, "2-1"), None, "Rams", "Seahawks")
        assert out["home"] == "2-1, #4 NFC West"

    def test_the_fresh_column_survives_the_cache_the_hero_actually_reads(self):
        """DOES THE FIX REACH THE READER (#2107).

        The event route does not hand `_compute_standings_context` a live ORM
        row — it hands it a `TeamSnapshot`, the frozen plain-data copy the
        process-global team cache holds. A snapshot that dropped
        `current_record` would make this whole change silently inert: the
        hero would fall back to the snapshot record and keep printing 92-60,
        with every unit test above still green.
        """
        from app.routes.events import TeamSnapshot, _snapshot_team

        live_row = SimpleNamespace(
            id=1,
            sport_id=10,
            name="Los Angeles Dodgers",
            slug="los-angeles-dodgers",
            abbreviation="LAD",
            primary_color=None,
            secondary_color=None,
            logo_url_small=None,
            logo_url_large=None,
            current_record=DODGERS_CURRENT,
            alternate_names=None,
            standings_data=DODGERS_SNAPSHOT,
            season_stats=None,
        )
        snap = _snapshot_team(live_row, sport_key="baseball_mlb")
        assert isinstance(snap, TeamSnapshot)
        assert snap.current_record == "93-60"

        out = _compute_standings_context(snap, None, "Dodgers", "Giants")
        assert out["home"] == "93-60, #1 West"
        assert "92-60" not in out["home"]

    def test_a_team_row_without_the_column_at_all_is_unchanged(self):
        # #5377's own fixtures build teams with no `current_record` attribute.
        # `_compute_standings_context` must not require it.
        bare = SimpleNamespace(standings_data=DODGERS_SNAPSHOT)
        out = _compute_standings_context(bare, None, "Dodgers", "Giants")
        assert out["home"] == "92-60, #1 West"

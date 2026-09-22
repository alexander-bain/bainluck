"""#6266 — a team page may not print a record for a season that has played no games.

THE SPECIMEN, production 2026-09-22, `/api/teams/montreal-canadiens` at 390px
(`artifacts-lane1-584/BEFORE-canadiens-390.png`):

    Montreal Canadiens
    2-0-0   Eastern Conference

`2-0-0` is the two games in the club's own `recent_events` on the same payload —
Sep 19 at Toronto and Sep 21 vs Ottawa — September dates the 2026-27 season has
not reached. `espn_helpers.py:921` stamps `team.current_record` from ESPN when a
game completes, and in preseason ESPN's record is the preseason one. Ten NHL
clubs carried one that day; 34 NBA rows carried a completed 82-game season
instead. The StatPal board read `wins 0, losses 0` for every one of them.

THE CONTRACT IS TWO-SIDED, and the admitted half is the half that can rot. A
withhold-only guard passes just as well against a serializer that returns None
for everything, so every refusal below is paired with a case that must still be
SERVED: the same league in season, the same league mid-break, an in-season
league on the same day as the refusal, and an unmodelled league. Both halves of
"refuse X unless Y".

Clocks are injected explicitly and never branch on the real date (gotcha #44):
each anchor is a fixed `datetime`, chosen from `season_windows._LEAGUE_BANDS`,
and the test asserts the same thing whenever it runs.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes.teams import _format_team, _record_for_declared_season
from app.utils import season_windows

# Anchors, all UTC, all fixed. Named for what the calendar says, not for a date
# arithmetic a reader would have to redo.
SEP_22 = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)   # NHL/NBA offseason, MLB+NFL in season
DEC_01 = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)   # NHL and NBA regular season
FEB_03 = datetime(2027, 2, 3, 12, 0, tzinfo=timezone.utc)    # NHL All-Star break
MAY_01 = datetime(2027, 5, 1, 12, 0, tzinfo=timezone.utc)    # NHL postseason
JUN_15 = datetime(2027, 6, 15, 12, 0, tzinfo=timezone.utc)   # NFL offseason


def _team(sport_key, record, *, team_id=568, name="Montreal Canadiens"):
    """A Team as `_format_team` reads it. `SimpleNamespace` for the same reason
    `test_standings_conf_rank_write_dead_4811` uses one: the serializer touches
    columns, never the session."""
    return SimpleNamespace(
        id=team_id,
        slug="montreal-canadiens",
        name=name,
        abbreviation="MTL",
        location="Montreal",
        primary_color="af1e2d",
        secondary_color="192168",
        logo_url_small="s.png",
        logo_url_large="l.png",
        current_record=record,
        standings_data={"wins": 0, "losses": 0, "conference": "Eastern Conference"},
        season_stats=None,
        roster_players=None,
        sport=SimpleNamespace(key=sport_key, name=sport_key),
    )


class TestTheAnchorsAreWhatTheCalendarSays:
    """If these drift, every assertion below is testing a different question.

    Read off `season_windows` rather than restated, so a band edit that moves a
    league's season fails HERE with the league named, instead of silently
    turning a refusal case into an admission case somewhere below.
    """

    @pytest.mark.parametrize(
        "league,anchor,phase",
        [
            ("nhl", SEP_22, "offseason"),
            ("nba", SEP_22, "offseason"),
            ("mlb", SEP_22, "in_season"),
            ("nfl", SEP_22, "in_season"),
            ("nhl", DEC_01, "in_season"),
            ("nba", DEC_01, "in_season"),
            ("nhl", FEB_03, "break"),
            ("nhl", MAY_01, "postseason"),
            ("nfl", JUN_15, "offseason"),
        ],
    )
    def test_phase(self, league, anchor, phase):
        assert season_windows.league_phase(league, anchor) == phase


class TestTheSpecimen:
    def test_the_canadiens_exhibition_record_is_withheld(self):
        """The one the screenshot caught."""
        out = _format_team(_team("icehockey_nhl", "2-0-0"), now=SEP_22)
        assert out["record"] is None

    def test_the_rest_of_the_hero_still_renders(self):
        """Empty beats wrong, but empty must not spread. The conference the hero
        prints beside the record comes from `standings` and is untouched."""
        out = _format_team(_team("icehockey_nhl", "2-0-0"), now=SEP_22)
        assert out["name"] == "Montreal Canadiens"
        assert out["standings"]["conference"] == "Eastern Conference"
        assert out["logo_large"] == "l.png"

    def test_the_nba_completed_season_is_withheld(self):
        """`brooklyn-nets 18-59`, 34 rows like it on the same day."""
        out = _format_team(
            _team("basketball_nba", "18-59", team_id=1, name="Brooklyn Nets"), now=SEP_22
        )
        assert out["record"] is None

    def test_a_duplicate_club_row_holding_last_season_is_withheld_too(self):
        """`montreal-nhl 41-21-10` — the other row for the same club (D35/#2693,
        not fixed here). The rule keys on the calendar, not on which row won the
        slug, so it cannot serve one club two seasons on two URLs."""
        out = _format_team(
            _team("icehockey_nhl", "41-21-10", team_id=4001, name="Montreal"), now=SEP_22
        )
        assert out["record"] is None


class TestTheAdmittedHalf:
    """Without these the guard is satisfied by a serializer that returns None."""

    def test_the_same_league_in_season_is_served(self):
        out = _format_team(_team("icehockey_nhl", "12-4-2"), now=DEC_01)
        assert out["record"] == "12-4-2"

    def test_a_mid_season_break_is_not_an_offseason(self):
        """February NHL games HAVE been played. A break is inside the regular
        season — `is_offseason` is deliberately narrower than `is_active`, and
        using the latter here would blank the record every All-Star weekend."""
        out = _format_team(_team("icehockey_nhl", "30-18-6"), now=FEB_03)
        assert out["record"] == "30-18-6"

    def test_the_postseason_is_served(self):
        out = _format_team(_team("icehockey_nhl", "52-22-8"), now=MAY_01)
        assert out["record"] == "52-22-8"

    def test_an_in_season_league_on_the_refusal_day_is_untouched(self):
        """The control that proves the rule is per-league and not a date cutoff:
        the same instant that withholds Montreal serves the Red Sox."""
        out = _format_team(
            _team("baseball_mlb", "88-67", team_id=2, name="Boston Red Sox"), now=SEP_22
        )
        assert out["record"] == "88-67"
        nfl = _format_team(
            _team("americanfootball_nfl", "2-1", team_id=3, name="Chicago Bears"), now=SEP_22
        )
        assert nfl["record"] == "2-1"

    def test_an_unmodelled_league_falls_through(self):
        """Only mlb/nba/nhl/nfl have bands. Everything else keeps whatever it had
        — this withholds what it can demonstrate, never what it failed to
        measure. `icehockey_nhl_preseason` is not in the map either."""
        for key in ("basketball_ncaab", "soccer_epl", "icehockey_nhl_preseason", "tennis_atp"):
            out = _format_team(_team(key, "9-3"), now=SEP_22)
            assert out["record"] == "9-3", key

    def test_a_team_with_no_sport_row_falls_through(self):
        team = _team("icehockey_nhl", "9-3")
        team.sport = None
        assert _format_team(team, now=SEP_22)["record"] == "9-3"

    def test_the_nfl_offseason_withholds_and_june_is_not_a_special_case(self):
        """The rule is the calendar, not a hardcoded pair of leagues: NFL in June
        is the same refusal, and it is the league that was a CONTROL in
        September."""
        out = _format_team(
            _team("americanfootball_nfl", "13-4", team_id=3, name="Chicago Bears"), now=JUN_15
        )
        assert out["record"] is None


class TestTheEdges:
    def test_an_absent_record_stays_absent(self):
        assert _format_team(_team("icehockey_nhl", None), now=DEC_01)["record"] is None
        assert _format_team(_team("icehockey_nhl", ""), now=DEC_01)["record"] is None

    def test_a_broken_calendar_costs_the_record_not_the_page(self, monkeypatch):
        """Priority #3: the route's standing rule is that an optional gate never
        takes the hero with it. A raising `is_offseason` must serve the record
        and log, not 500."""
        def _boom(*_a, **_k):
            raise RuntimeError("bands corrupt")

        monkeypatch.setattr(season_windows, "is_offseason", _boom)
        out = _format_team(_team("icehockey_nhl", "2-0-0"), now=SEP_22)
        assert out["record"] == "2-0-0"

    def test_the_default_clock_is_the_real_one_not_a_frozen_constant(self):
        """`now=None` must reach `datetime.now`, not a module-level anchor. A
        frozen default would make every production page read one date forever.
        Asserted by agreement with an explicit read of the same instant, which
        is true whenever this runs."""
        team = _team("icehockey_nhl", "2-0-0")
        live = datetime.now(timezone.utc)
        assert _record_for_declared_season(team) == _record_for_declared_season(team, live)


class TestTheRouteSpendsIt:
    """A serializer that is right and a route that does not call it is the
    #7929 shape of failure. The payload key must come from the gate."""

    def test_the_route_passes_its_own_clock_to_the_serializer(self):
        import inspect

        from app.routes import teams as teams_module

        source = inspect.getsource(teams_module.get_team)
        assert "_format_team(team, now=now)" in source, (
            "the route must hand the serializer the clock it already read, or "
            "the record and the season descriptor beside it can disagree"
        )

    def test_the_serializer_reads_the_gate_and_not_the_column(self):
        import inspect

        from app.routes import teams as teams_module

        source = inspect.getsource(teams_module._format_team)
        assert "_record_for_declared_season(team, now)" in source
        assert "team.current_record" not in source

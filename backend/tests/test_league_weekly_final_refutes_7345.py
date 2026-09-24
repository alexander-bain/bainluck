"""#7345 — a football card says "No result reported" for a game ESPN has as 28–26.

THE SPECIMEN, MEASURED ON PRODUCTION 2026-09-24 03:4xZ
══════════════════════════════════════════════════════
`GET /api/leagues/americanfootball_ncaaf` → `unreported_games`, and the same three
cards at 390px under OTHER GAMES on `/sport/football/ncaaf`::

    15300206  Texas Tech / Houston  suspended  odds_api  stored 09-20 00:00Z
      -> 14627221  completed 28-26  espn 401856811        at 09-19 00:00Z  (24h)
    15306765  Arkansas State / South Alabama  suspended  odds_api  09-12 23:00Z
      -> no Final anywhere; ESPN has the fixture on 2026-10-08
    15304466  San Jose State / Cal Poly  suspended  odds_api  09-12 00:00Z
      -> 15306772  completed 30-20  espn 401864504        at 09-13 01:00Z  (25h)

The first card tells a reader a finished game has no result. `_folded_past_rails`
was written for exactly that, but its key is exact-minute (`twin_fold_key`), and
these rows are an Odds API listing stamped a day off the real kickoff. So the
Final is never at the ghost's minute and the fold never sees the pair.

WHY A CLOCK BOUND IS SAFE HERE AND NOWHERE ELSE
═══════════════════════════════════════════════
A football pairing never plays twice inside six days. A baseball pairing plays on
consecutive days, and those are different games. So the bound applies to
NFL and NCAAF pages only (`weekly_fixture_final_window`), and
`test_mlb_never_gets_a_window` is the guard that keeps it there.

`15306765` is the negative control. It has the same status, age and scorelessness
as the specimen, and no Final exists for it. It must keep its card, and this
change does not repair it (it stays open on #7345).
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.dialects import postgresql

from app.models.models import Event, Sport
from app.routes import league_futures
from app.routes.league_futures import (
    WEEKLY_FIXTURE_FINAL_WINDOW,
    refuted_by_a_weekly_final,
    weekly_finals_near_unreported_query,
    weekly_fixture_final_window,
)

GHOST_AT = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)
FINAL_AT = datetime(2026, 9, 19, 0, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 9, 24, 3, 45, tzinfo=timezone.utc)
NCAAF = Sport(id=7, key="americanfootball_ncaaf", name="NCAAF")


def _row(id, home, away, when, *, status="suspended", sport=NCAAF, **cols):
    """A real, unattached `Event`, with its sport relationship set.

    The relationship is SET, not left unloaded, so `twin_fold_key`'s element 0
    is the league identity production reads (`football/college-football`)
    rather than the `sport_id` fallback.
    """
    e = Event(
        id=id,
        home_team_name=home,
        away_team_name=away,
        commence_time=when,
        sport_id=sport.id,
        status=status,
        win_probability_sources={},
        **cols,
    )
    e.sport = sport
    return e


def _ghost(id=15300206, when=GHOST_AT, home="Texas Tech Red Raiders",
           away="Houston Cougars", **cols):
    return _row(id, home, away, when, **cols)


def _final(id=14627221, when=FINAL_AT, home="Texas Tech Red Raiders",
           away="Houston Cougars", espn_id="401856811", home_score=28,
           away_score=26):
    return _row(id, home, away, when, status="completed", espn_id=espn_id,
                home_score=home_score, away_score=away_score)


def _ids(rows):
    return [e.id for e in rows]


class TestTheProductionSpecimen:
    def test_the_texas_tech_card_leaves_the_rail(self):
        assert _ids(refuted_by_a_weekly_final(
            [_ghost()], [_final()], WEEKLY_FIXTURE_FINAL_WINDOW)) == []

    def test_the_san_jose_state_card_leaves_too_at_25_hours(self):
        ghost = _ghost(15304466, datetime(2026, 9, 12, 0, 0, tzinfo=timezone.utc),
                       "San Jose State Spartans", "Cal Poly Mustangs")
        final = _final(15306772, datetime(2026, 9, 13, 1, 0, tzinfo=timezone.utc),
                       "San Jose State Spartans", "Cal Poly Mustangs",
                       espn_id="401864504", home_score=30, away_score=20)
        assert _ids(refuted_by_a_weekly_final(
            [ghost], [final], WEEKLY_FIXTURE_FINAL_WINDOW)) == []

    def test_the_arkansas_state_control_keeps_its_card(self):
        """No Final exists, so nothing refutes it, beside a row that IS refuted."""
        control = _ghost(15306765, datetime(2026, 9, 12, 23, 0, tzinfo=timezone.utc),
                         "Arkansas State Red Wolves", "South Alabama Jaguars")
        kept = refuted_by_a_weekly_final(
            [_ghost(), control], [_final()], WEEKLY_FIXTURE_FINAL_WINDOW)
        assert _ids(kept) == [15306765]

    def test_the_exact_minute_fold_alone_misses_this_pair(self):
        """Read this first: why the #5746/#5802 fold leaves the specimen on the page."""
        _r, unreported, _g = league_futures._folded_past_rails(
            [], [_ghost()], [], [_final()])
        assert _ids(unreported) == [15300206]


class TestWhatMayNotBeSuppressed:
    def test_a_final_outside_the_window_refutes_nothing(self):
        far = _final(when=GHOST_AT - WEEKLY_FIXTURE_FINAL_WINDOW - timedelta(minutes=1))
        assert _ids(refuted_by_a_weekly_final(
            [_ghost()], [far], WEEKLY_FIXTURE_FINAL_WINDOW)) == [15300206]

    def test_the_window_is_inclusive_at_its_edge(self):
        edge = _final(when=GHOST_AT - WEEKLY_FIXTURE_FINAL_WINDOW)
        assert _ids(refuted_by_a_weekly_final(
            [_ghost()], [edge], WEEKLY_FIXTURE_FINAL_WINDOW)) == []

    def test_a_subject_with_its_own_espn_id_is_its_own_game(self):
        ghost = _ghost(espn_id="401999999")
        assert _ids(refuted_by_a_weekly_final(
            [ghost], [_final()], WEEKLY_FIXTURE_FINAL_WINDOW)) == [15300206]

    def test_a_subject_with_a_statpal_id_is_its_own_game(self):
        ghost = _ghost(statpal_fixture_id="998877")
        assert _ids(refuted_by_a_weekly_final(
            [ghost], [_final()], WEEKLY_FIXTURE_FINAL_WINDOW)) == [15300206]

    def test_a_subject_with_a_score_is_never_suppressed(self):
        ghost = _ghost(home_score=0, away_score=0)
        assert _ids(refuted_by_a_weekly_final(
            [ghost], [_final()], WEEKLY_FIXTURE_FINAL_WINDOW)) == [15300206]

    def test_a_final_without_an_espn_id_is_not_evidence(self):
        assert _ids(refuted_by_a_weekly_final(
            [_ghost()], [_final(espn_id=None)], WEEKLY_FIXTURE_FINAL_WINDOW)
        ) == [15300206]

    @pytest.mark.parametrize("side", ["home_score", "away_score"])
    def test_a_final_missing_a_score_is_not_evidence(self, side):
        final = _final(**{side: None})
        assert _ids(refuted_by_a_weekly_final(
            [_ghost()], [final], WEEKLY_FIXTURE_FINAL_WINDOW)) == [15300206]

    def test_the_reversed_orientation_is_a_different_fixture(self):
        final = _final(home="Houston Cougars", away="Texas Tech Red Raiders")
        assert _ids(refuted_by_a_weekly_final(
            [_ghost()], [final], WEEKLY_FIXTURE_FINAL_WINDOW)) == [15300206]

    def test_a_different_opponent_refutes_nothing(self):
        final = _final(away="Houston Christian Huskies")
        assert _ids(refuted_by_a_weekly_final(
            [_ghost()], [final], WEEKLY_FIXTURE_FINAL_WINDOW)) == [15300206]

    def test_a_final_in_another_league_refutes_nothing(self):
        nfl = Sport(id=8, key="americanfootball_nfl", name="NFL")
        final = _final()
        final.sport_id = nfl.id
        final.sport = nfl
        assert _ids(refuted_by_a_weekly_final(
            [_ghost()], [final], WEEKLY_FIXTURE_FINAL_WINDOW)) == [15300206]

    def test_the_squash_bridges_a_spelling_the_sql_would_already_have_matched(self):
        """Python compares squashed names, so punctuation alone cannot split a pair."""
        final = _final(home="Texas Tech Red-Raiders")
        assert _ids(refuted_by_a_weekly_final(
            [_ghost()], [final], WEEKLY_FIXTURE_FINAL_WINDOW)) == []

    def test_a_raising_row_serves_the_rail_unfiltered(self):
        class Boom:
            espn_id = "1"
            home_score = 1
            away_score = 1

            @property
            def home_team_name(self):
                raise RuntimeError("unreadable")

        # `_twin_key_or_none` absorbs a row that cannot key; this proves the
        # outer guard too, with a finals list that is not iterable at all.
        assert _ids(refuted_by_a_weekly_final(
            [_ghost()], [Boom()], WEEKLY_FIXTURE_FINAL_WINDOW)) == [15300206]

        class NotIterable:
            def __bool__(self):
                return True

        assert _ids(refuted_by_a_weekly_final(
            [_ghost()], NotIterable(), WEEKLY_FIXTURE_FINAL_WINDOW)) == [15300206]


class TestTheLeagueGate:
    @pytest.mark.parametrize("key", [
        "americanfootball_ncaaf", "americanfootball_nfl",
        "americanfootball_nfl_preseason",
    ])
    def test_football_gets_the_window(self, key):
        assert weekly_fixture_final_window(key) == timedelta(hours=72)

    @pytest.mark.parametrize("key", [
        "baseball_mlb", "basketball_nba", "icehockey_nhl", "soccer_epl",
        "basketball_ncaab", "tennis_atp", None,
    ])
    def test_mlb_never_gets_a_window(self, key):
        """A series plays the same pairing on consecutive days: different games."""
        assert weekly_fixture_final_window(key) is None

    def test_the_window_is_under_the_six_days_between_two_meetings(self):
        assert WEEKLY_FIXTURE_FINAL_WINDOW < timedelta(days=6)


class TestTheQuery:
    def _sql(self, subjects):
        stmt = weekly_finals_near_unreported_query(
            "americanfootball_ncaaf", NOW, subjects, WEEKLY_FIXTURE_FINAL_WINDOW)
        return str(stmt.compile(dialect=postgresql.dialect(),
                                compile_kwargs={"literal_binds": True}))

    def test_it_asks_for_evidence_and_the_subjects_own_pair(self):
        sql = self._sql([_ghost()])
        assert "events.espn_id IS NOT NULL" in sql
        assert "events.home_score IS NOT NULL" in sql
        assert "events.away_score IS NOT NULL" in sql
        assert "events.home_team_name = 'Texas Tech Red Raiders'" in sql
        assert "events.away_team_name = 'Houston Cougars'" in sql
        assert "BETWEEN '2026-09-17 00:00:00+00:00' AND '2026-09-23 00:00:00+00:00'" in sql
        assert "duplicate-of" in sql  # not_a_proven_duplicate, #5802's reason

    def test_one_pair_clause_per_subject(self):
        second = _ghost(15306765, datetime(2026, 9, 12, 23, 0, tzinfo=timezone.utc),
                        "Arkansas State Red Wolves", "South Alabama Jaguars")
        assert self._sql([_ghost(), second]).count(" BETWEEN ") == 2

    def test_it_is_bounded(self):
        assert " LIMIT " in self._sql([_ghost()])


class TestTheRouteWiring:
    """The helper is inert unless the route calls it in the right place."""

    SRC = inspect.getsource(league_futures)

    def test_it_runs_after_the_past_rail_fold_and_before_the_formatter(self):
        fold = self.SRC.index("_r_events, _u_events, _g_events = _folded_past_rails(")
        call = self.SRC.index("_u_events = refuted_by_a_weekly_final(")
        drain = self.SRC.index("market_born_duplicates_on_page(db, _page_rows)")
        fmt = self.SRC.index("_urows = _format_all(_u_events)")
        assert fold < call < drain < fmt

    def test_the_route_gates_on_the_league_and_the_subjects(self):
        assert "_weekly_window = weekly_fixture_final_window(sport_key)" in self.SRC
        assert "if _is_id_less_and_scoreless(e) and e.commence_time" in self.SRC

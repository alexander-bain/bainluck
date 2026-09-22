"""#7051 — a team page's results rail may not carry a game from another season.

THE SPECIMEN, production 2026-09-22, `/api/teams/denver-broncos`:

    Denver Broncos
    1-1

    RECENT RESULTS
      Sep 20  Jacksonville Jaguars @ Denver Broncos   13-20   completed
      Sep 15  Denver Broncos @ Kansas City Chiefs     10-31   completed
      Aug 29  Minnesota Vikings @ Denver Broncos       6-34   completed   <-
      Aug 28  Minnesota Vikings @ Denver Broncos    no score  suspended   <-

The record is right: the NFL regular season opened on Sep 10 and the Broncos
have played two of them. The two August rows are exhibitions, and the second is
the score-less twin of the first, 21 hours apart, so no fold bound reaches it
(#3601). A reader is told 1-1 and shown, in the same screen, four results.

MEASURED over all 32 NFL team payloads that morning
(`artifacts-lane1-585/BEFORE-nfl-rails.txt`): 32 of 32 pages print a record, and
36 of their 100 recent cards were played before the season started. Every NFL
team page contradicted itself. After the floor: 64 cards, and NO page is left
with an empty rail.

THE ROWS ARE NOT TAGGED AND CANNOT BE. All four above carry
`sport_key = americanfootball_nfl`; the whole 2026 preseason is filed under the
regular-season key (and duplicated under `americanfootball_nfl_preseason`), so
every filter keyed on the sport key passes them through. The floor is the
calendar instead.

THE CONTRACT IS TWO-SIDED, and the admitted half is the half that rots. A
drop-only guard passes just as well against a filter that empties every rail, so
every exclusion below is paired with a row that must still be SERVED: the same
club's real results, the same August rows read at an August clock, a league
whose season has not started yet (NHL today — its exhibitions STAY), and an
unmodelled league.

Clocks are injected and never branch on the real date (gotcha #44): each anchor
is a fixed `datetime` checked back against `season_windows._LEAGUE_BANDS`, so a
band edit fails with the league named rather than silently turning an exclusion
case into an admission case.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.routes.teams import (
    _played_before_season_start,
    _rail_within_declared_season,
)
from app.utils import season_windows

# Anchors, all UTC, all fixed.
SEP_22 = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)  # NFL week 3; NHL/NBA not started
AUG_25 = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)  # NFL preseason; no season started
OCT_10 = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)  # NHL season under way
JAN_15 = datetime(2027, 1, 15, 12, 0, tzinfo=timezone.utc)  # every wrap league past new year


def _row(commence, *, sport_key="americanfootball_nfl", event_id=1, status="completed"):
    """An Event as the rail filter reads it — it touches two columns, never the
    session, so a namespace is the honest fake."""
    return SimpleNamespace(
        id=event_id, commence_time=commence, sport_key=sport_key, status=status
    )


# The Broncos rail exactly as production served it, oldest last.
BRONCOS_RAIL = [
    _row(datetime(2026, 9, 20, 20, 5, tzinfo=timezone.utc), event_id=14782705),
    _row(datetime(2026, 9, 15, 0, 15, tzinfo=timezone.utc), event_id=14638896),
    _row(datetime(2026, 8, 29, 1, 0, tzinfo=timezone.utc), event_id=15292755),
    _row(
        datetime(2026, 8, 28, 4, 0, tzinfo=timezone.utc),
        event_id=15291332,
        sport_key="americanfootball_nfl_preseason",
        status="suspended",
    ),
]
BRONCOS_REAL = {14782705, 14638896}
BRONCOS_EXHIBITIONS = {15292755, 15291332}


def _ids(rows):
    return {r.id for r in rows}


class TestTheAnchorsAreWhatTheCalendarSays:
    """If these drift, every assertion below is testing a different question."""

    @pytest.mark.parametrize(
        "league,anchor,expected_year",
        [
            ("nfl", SEP_22, 2026),  # Sep 4 has passed: this season
            ("nfl", AUG_25, 2025),  # Sep 4 has not: last season's floor
            ("nfl", JAN_15, 2026),  # the wrap — still the season that began in September
            ("nhl", SEP_22, 2025),  # Oct 4 has not arrived; the floor is last October's
            ("nhl", OCT_10, 2026),
            ("nhl", JAN_15, 2026),  # the wrap the naive month/day compare gets wrong
            ("nba", SEP_22, 2025),
            ("nba", JAN_15, 2026),
            ("mlb", SEP_22, 2026),
        ],
    )
    def test_the_floor_is_the_latest_start_already_passed(
        self, league, anchor, expected_year
    ):
        floor = season_windows.season_start(league, anchor)
        band_start = next(
            md for phase, md, _ in season_windows._LEAGUE_BANDS[league] if phase == "in_season"
        )
        assert floor == datetime(
            expected_year, band_start[0], band_start[1], tzinfo=timezone.utc
        ), f"{league} floor moved: band start is now {band_start}"
        assert floor <= anchor, "a floor in the future would empty the rail"

    def test_the_floor_is_midnight_so_opening_night_clears_it(self):
        """The NBA's first 2026-27 game is `2026-10-20 19:00Z` against a
        `(10, 20)` band. A floor carrying any clock at all would delete opening
        night from every rail for a month."""
        floor = season_windows.season_start("nba", datetime(2026, 11, 1, tzinfo=timezone.utc))
        assert (floor.hour, floor.minute, floor.second, floor.microsecond) == (0, 0, 0, 0)
        assert floor.tzinfo is not None
        assert floor < datetime(2026, 10, 20, 19, 0, tzinfo=timezone.utc)

    @pytest.mark.parametrize("league", ["epl", "golf", "tennis", "", None, "nfl_preseason"])
    def test_an_unmodelled_or_continuous_league_has_no_floor(self, league):
        assert season_windows.season_start(league, SEP_22) is None

    def test_the_default_clock_is_the_real_one_not_a_frozen_constant(self):
        live = datetime.now(timezone.utc)
        assert season_windows.season_start("nfl") == season_windows.season_start("nfl", live)


class TestTheSpecimen:
    """The four Broncos cards, at the clock they were photographed on."""

    def test_the_two_august_exhibitions_leave_the_rail(self):
        kept = _rail_within_declared_season(BRONCOS_RAIL, "americanfootball_nfl", SEP_22)
        assert _ids(kept) == BRONCOS_REAL

    def test_the_two_real_results_are_still_served(self):
        kept = _rail_within_declared_season(BRONCOS_RAIL, "americanfootball_nfl", SEP_22)
        assert len(kept) == 2, "the rail must not be emptied to be made honest"
        assert BRONCOS_EXHIBITIONS.isdisjoint(_ids(kept))

    def test_the_score_less_twin_goes_with_it(self):
        """#3601's row: an exhibition with no result, 21 hours from its scored
        copy, which no fold reaches. Its own sport_key is the preseason one and
        it is still the TEAM's league that decides — keyed on the club's page,
        not on the row's key, or the misfiled 51 would survive."""
        twin = [r for r in BRONCOS_RAIL if r.id == 15291332]
        assert _rail_within_declared_season(twin, "americanfootball_nfl", SEP_22) == []

    def test_order_is_preserved_for_what_survives(self):
        kept = _rail_within_declared_season(BRONCOS_RAIL, "americanfootball_nfl", SEP_22)
        assert [r.id for r in kept] == [14782705, 14638896]


class TestTheAdmittedHalf:
    """Everything the floor must NOT take."""

    def test_the_same_august_rows_are_served_at_an_august_clock(self):
        """The rule is not "drop August". In August the NFL season has not
        started, the page prints no record (#6266), and these exhibitions are
        the only football the club has played — the floor is last September's
        and admits all four."""
        kept = _rail_within_declared_season(BRONCOS_RAIL, "americanfootball_nfl", AUG_25)
        assert _ids(kept) == BRONCOS_REAL | BRONCOS_EXHIBITIONS

    def test_a_league_whose_season_has_not_started_keeps_its_exhibitions(self):
        """NHL, 2026-09-22: 55 September games sit under `icehockey_nhl` itself.
        The floor is 2025-10-04, so they stay — an empty rail under a withheld
        record is the worse answer, and nothing on that page contradicts them."""
        nhl = [
            _row(datetime(2026, 9, 26, 23, 0, tzinfo=timezone.utc), sport_key="icehockey_nhl", event_id=91),
            _row(datetime(2026, 10, 1, 23, 0, tzinfo=timezone.utc), sport_key="icehockey_nhl", event_id=92),
        ]
        assert _ids(_rail_within_declared_season(nhl, "icehockey_nhl", SEP_22)) == {91, 92}

    def test_and_loses_them_the_moment_its_own_season_opens(self):
        """The other direction of the same clock — without this arm the arm
        above passes against a filter that never fires for the NHL at all."""
        nhl = [
            _row(datetime(2026, 9, 26, 23, 0, tzinfo=timezone.utc), sport_key="icehockey_nhl", event_id=91),
            _row(datetime(2026, 10, 7, 23, 0, tzinfo=timezone.utc), sport_key="icehockey_nhl", event_id=93),
        ]
        assert _ids(_rail_within_declared_season(nhl, "icehockey_nhl", OCT_10)) == {93}

    def test_an_in_season_league_on_the_same_day_is_untouched(self):
        """MLB on the day the NFL rows are cut: floor 2026-03-20, nothing moves."""
        mlb = [
            _row(datetime(2026, 4, 2, 23, 0, tzinfo=timezone.utc), sport_key="baseball_mlb", event_id=81),
            _row(datetime(2026, 9, 21, 23, 0, tzinfo=timezone.utc), sport_key="baseball_mlb", event_id=82),
        ]
        assert _ids(_rail_within_declared_season(mlb, "baseball_mlb", SEP_22)) == {81, 82}

    @pytest.mark.parametrize(
        "sport_key", ["soccer_epl", "tennis_atp", "americanfootball_nfl_preseason", None, ""]
    )
    def test_an_unmodelled_league_falls_through_untouched(self, sport_key):
        rows = [_row(datetime(2020, 1, 1, tzinfo=timezone.utc), event_id=7)]
        assert _ids(_rail_within_declared_season(rows, sport_key, SEP_22)) == {7}

    def test_an_empty_rail_stays_an_empty_rail(self):
        assert _rail_within_declared_season([], "americanfootball_nfl", SEP_22) == []


class TestTheRowTest:
    """`_played_before_season_start` on its own, including the shapes a row can
    arrive in that the comprehension above never shows."""

    FLOOR = datetime(2026, 9, 4, tzinfo=timezone.utc)

    def test_before_the_floor_is_excluded(self):
        assert _played_before_season_start(
            _row(datetime(2026, 8, 29, 1, 0, tzinfo=timezone.utc)), self.FLOOR
        )

    def test_after_the_floor_is_kept(self):
        assert not _played_before_season_start(
            _row(datetime(2026, 9, 15, 0, 15, tzinfo=timezone.utc)), self.FLOOR
        )

    def test_the_boundary_belongs_to_the_new_season(self):
        """Midnight on the floor itself is the season's first instant, not the
        last of the old one — a `<=` here would delete an opening-day game."""
        assert not _played_before_season_start(_row(self.FLOOR), self.FLOOR)

    def test_a_naive_timestamp_is_read_as_utc_not_raised_on(self):
        """`Event.commence_time` is `DateTime(timezone=True)` and a row can
        still arrive naive — the same normalisation
        `commence_time_was_never_a_kickoff` makes one gate above."""
        assert _played_before_season_start(_row(datetime(2026, 8, 29, 1, 0)), self.FLOOR)
        assert not _played_before_season_start(_row(datetime(2026, 9, 15, 0, 15)), self.FLOOR)

    def test_a_row_with_no_kickoff_is_kept(self):
        """This gate can only ever remove a card, so the unreadable case serves
        it."""
        assert not _played_before_season_start(_row(None), self.FLOOR)
        assert not _played_before_season_start(SimpleNamespace(id=1), self.FLOOR)


class TestTheRouteSpendsIt:
    """A filter that is right and a route that does not call it is the #7929
    shape of failure."""

    def test_the_route_hands_the_filter_its_own_clock_and_the_clubs_league(self):
        """Parsed, not grepped. The naive form of this assertion — `"now" in
        <the call text>` — is satisfied by `datetime.now(timezone.utc)`, which
        is the exact regression it exists to catch: the route reads its clock
        ONCE at the top so the record, the season descriptor and the rail cannot
        disagree about the date, and a second read inside the call re-opens
        that. Measured: the substring form survived the mutation."""
        import ast
        import inspect
        import textwrap

        from app.routes import teams as teams_module

        tree = ast.parse(textwrap.dedent(inspect.getsource(teams_module.get_team)))
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "_rail_within_declared_season"
        ]
        assert len(calls) == 1, "the recent rail is filtered exactly once"
        args = calls[0].args
        assert len(args) == 3
        # The clock is the route's own `now`, a bare name — not a fresh read.
        assert isinstance(args[2], ast.Name) and args[2].id == "now"
        # And the league comes from the club's sport row, not the path parameter.
        assert "team.sport.key" in ast.unparse(args[1])

    def test_a_broken_calendar_costs_the_gate_not_the_page(self, monkeypatch):
        """Priority #3: an optional gate never takes the reader's rail with it.
        The route wraps this call, so the raise must reach it rather than being
        swallowed into an empty list here."""
        monkeypatch.setattr(
            season_windows, "season_start", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        with pytest.raises(RuntimeError):
            _rail_within_declared_season(BRONCOS_RAIL, "americanfootball_nfl", SEP_22)

        import inspect

        from app.routes import teams as teams_module

        source = inspect.getsource(teams_module.get_team)
        after = source.split("_rail_within_declared_season(", 1)[1][:600]
        assert "except Exception" in after and "serving" in after

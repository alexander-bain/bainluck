"""A tour page shows the tournament being played on it — #3677.

── WHAT WAS WRONG ──

`/sport/tennis/atp` and `/sport/tennis/wta` are declared in `SPORT_HIERARCHY` as
exactly one sport key each (`tennis_atp`, `tennis_wta`), and all three games rails
in `league_futures` scope themselves with `Sport.key == sport_key`. That predicate
is correct, present, and indexed — which is why three separate LOOK passes read
the page as fine and nobody suspected the query.

The rows it cannot see are the ones a reader came for. A tour's TOURNAMENTS are
registered as their own sport keys, minted from Kalshi tickers as the tournament
appears, so on 2026-09-06 — US Open men's finals weekend — production held:

    tennis_atp_us_open            123 events (14d)   on NO league page
    tennis_wta_us_open            122               on NO league page
    tennis_wta_monterrey_open      33               on NO league page

while the two tour pages filled instead with the midnight-stamped, surname-only
duplicate rows of #2878 — 191 under `tennis_atp` and 115 under `tennis_wta` in
seven days — which DO carry the bare tour key. So the page looked populated and
was wrong: `/sport/tennis/atp` linked `M Michelsen / E Etcheverry — No result
reported` while `/sports` linked the same match's real row at 27%/73%.

── WHY THE OPT-IN IS DECLARED AND NOT INFERRED ──

Ten sport keys with recent events are the sport-key child of a declared league.
Four belong on their parent's page (above); the rest do not, and merging them
would be a fresh bug rather than a fix:

    soccer_germany_bundesliga_women   is not the men's Bundesliga
    soccer_uefa_champs_league_women   is not the men's UCL
    americanfootball_ncaaf_fcs        FCS is not FBS
    americanfootball_nfl_preseason

"A child key belongs to its parent league" is therefore true of a TOUR and false
of a competition. D55: membership is declared, never inferred from the shape of a
string. The declaration sits at the LEAGUE level
(`TOUR_LEAGUES_INCLUDING_TOURNAMENTS`) and the enumeration at the TOURNAMENT level
(whatever keys actually exist), because that is the only split that does not go
stale — a hand-listed set of tournaments is wrong by the next Slam, and being
wrong by the next Slam is precisely this bug.

── WHAT IS NOT FIXED HERE ──

The duplicate rows themselves. They are #2878/#2693 and lane1's under D39; this
changes no event row and merges nothing. After this fix both copies can appear —
the real match on the upcoming/results rails where its kickoff and score put it,
the duplicate on #3211's NO RESULT REPORTED rail where its midnight stamp and
`scheduled` status put it. That is strictly better than only the duplicate, and
it is the honest state until the write side is repaired.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

import pytest
from sqlalchemy.dialects import postgresql

from app.routes.league_futures import (
    build_league,
    recent_results_query,
    unreported_games_query,
    upcoming_games_query,
)
from app.utils.sport_keys import (
    SPORT_HIERARCHY,
    TOUR_LEAGUES_INCLUDING_TOURNAMENTS,
    tour_scope_sport_keys,
)

NOW = datetime(2026, 9, 6, 19, 0, tzinfo=timezone.utc)

#: The three rails, by the name a failure should print.
_RAILS = (
    ("upcoming", upcoming_games_query),
    ("results", recent_results_query),
    ("unreported", unreported_games_query),
)

#: Registered keys as production actually had them on 2026-09-06, trimmed to the
#: ones that make each distinction. `tennis_atpx_bogus` is not a typo: it is the
#: row that proves the prefix test is `<parent>_` and not `<parent>`, and
#: `soccer_germany_bundesliga_women` is the row that proves the opt-in is real.
_REGISTERED = (
    "tennis_atp",
    "tennis_atp_us_open",
    "tennis_atp_wimbledon",
    "tennis_atpx_bogus",
    "tennis_wta",
    "tennis_wta_us_open",
    "tennis_wta_monterrey_open",
    "tennis_other",
    "soccer_germany_bundesliga",
    "soccer_germany_bundesliga_women",
    "basketball_nba",
)


def _sql(query) -> str:
    return str(query.compile(dialect=postgresql.dialect()))


# ---------------------------------------------------------------------------
# the pure rule
# ---------------------------------------------------------------------------


def test_an_opted_in_tour_gathers_its_registered_tournaments():
    assert tour_scope_sport_keys("tennis_atp", _REGISTERED) == [
        "tennis_atp",
        "tennis_atp_us_open",
        "tennis_atp_wimbledon",
    ]


def test_the_tour_key_leads_and_the_rest_are_sorted():
    """Deterministic order, because this list reaches a cache key and a compiled
    statement — a set would make both flap between builds for no reason."""
    scope = tour_scope_sport_keys("tennis_wta", _REGISTERED)
    assert scope[0] == "tennis_wta"
    assert scope[1:] == sorted(scope[1:])
    assert scope == ["tennis_wta", "tennis_wta_monterrey_open", "tennis_wta_us_open"]


def test_a_league_that_has_not_opted_in_is_unchanged():
    """The other direction, and the whole reason the opt-in exists: the women's
    Bundesliga is its own competition and a prefix rule would have swallowed it
    into the men's page."""
    assert tour_scope_sport_keys("soccer_germany_bundesliga", _REGISTERED) == [
        "soccer_germany_bundesliga"
    ]
    assert tour_scope_sport_keys("basketball_nba", _REGISTERED) == ["basketball_nba"]


def test_the_prefix_boundary_is_the_underscore():
    """`tennis_atpx_bogus` starts with `tennis_atp` and is not an ATP tournament.
    Membership is `<parent>_`, so a key that merely shares a prefix stays out."""
    assert "tennis_atpx_bogus" not in tour_scope_sport_keys("tennis_atp", _REGISTERED)


def test_a_tournament_that_does_not_exist_cannot_widen_the_scope():
    """The scope is resolved from the keys that are actually registered, so it can
    never name a sport row that is not there."""
    assert tour_scope_sport_keys("tennis_atp", ["tennis_atp"]) == ["tennis_atp"]


def test_every_opted_in_key_is_a_league_the_hierarchy_declares():
    """An opt-in for a key no page renders would be dead config that reads as
    coverage."""
    declared = {
        key
        for hierarchy in SPORT_HIERARCHY.values()
        for league in hierarchy.get("leagues", [])
        for key in league.get("sport_keys", [])
    }
    assert TOUR_LEAGUES_INCLUDING_TOURNAMENTS <= declared, (
        "opted-in keys that no league declares: "
        f"{sorted(TOUR_LEAGUES_INCLUDING_TOURNAMENTS - declared)}"
    )


# ---------------------------------------------------------------------------
# the SQL each rail compiles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rail,builder", _RAILS)
def test_a_rail_given_nothing_compiles_the_measured_equality(rail, builder):
    """🔴 Byte-for-byte `sports.key = :key` when no tournament is added.

    `recent_results_query`'s `OFFSET 0` fence and the upcoming rail's deliberate
    ABSENCE of one are both claims about the exact statement LAT-P110 measured
    (its block table: 230,256 blocks flat vs 2,313 fenced). `IN (:key)` is a
    different statement. 27 of the 29 declared leagues add nothing, so they must
    keep the statement those numbers were taken from — only an opted-in tour gets
    a shape that has to be re-measured."""
    sql = _sql(builder("americanfootball_cfl", NOW))
    assert re.search(r"sports\.key = %\(key_\d+\)s", sql), (
        f"the {rail} rail no longer compiles a plain equality for a league with "
        f"no tournaments; the measured plan does not apply to it any more:\n{sql}"
    )
    assert "sports.key IN" not in sql


@pytest.mark.parametrize("rail,builder", _RAILS)
def test_a_rail_given_tournaments_widens_to_them_and_nothing_else(rail, builder):
    sql = _sql(
        builder(
            "tennis_atp",
            NOW,
            also_sport_keys=["tennis_atp_us_open", "tennis_atp_wimbledon"],
        )
    )
    assert "sports.key IN" in sql, (
        f"the {rail} rail dropped its added tournaments — the US Open would be "
        f"back on no page:\n{sql}"
    )
    literal = str(
        builder(
            "tennis_atp",
            NOW,
            also_sport_keys=["tennis_atp_us_open", "tennis_atp_wimbledon"],
        ).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "'tennis_atp_us_open'" in literal
    assert "'tennis_atp'" in literal
    assert "'tennis_wta'" not in literal


@pytest.mark.parametrize("rail,builder", _RAILS)
def test_widening_the_league_changes_nothing_else_about_a_rail(rail, builder):
    """Both directions (gotcha #43). The scope clause is the ONLY difference —
    a widening that also relaxed a status filter or a lookback would put settled
    rows on the upcoming rail and read, from the page, exactly like this fix
    working."""
    narrow = _sql(builder("tennis_atp", NOW))
    wide = _sql(builder("tennis_atp", NOW, also_sport_keys=["tennis_atp_us_open"]))
    normalise = lambda s: re.sub(  # noqa: E731
        r"sports\.key (?:= %\(key_\d+\)s|IN \(__\[POSTCOMPILE_key_\d+\]\))",
        "<SCOPE>",
        s,
    )
    assert normalise(narrow) == normalise(wide), (
        f"the {rail} rail changed something other than its league scope:\n"
        f"--- narrow ---\n{normalise(narrow)}\n--- wide ---\n{normalise(wide)}"
    )
    assert "<SCOPE>" in normalise(narrow), "the scope clause stopped being matched"


@pytest.mark.parametrize("rail,builder", _RAILS)
def test_the_fence_survives_a_widened_scope(rail, builder):
    """The two fenced rails keep their fence when the scope widens. The fence is
    what stands between a quiet league and a 4.9-second cold read, and it lives
    in the same `.where()` this change edited."""
    sql = _sql(builder("tennis_atp", NOW, also_sport_keys=["tennis_atp_us_open"]))
    if rail == "upcoming":
        assert "OFFSET" not in sql.upper()
    else:
        assert "LIMIT ALL OFFSET 0" in sql


# ---------------------------------------------------------------------------
# the route actually does it
# ---------------------------------------------------------------------------


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def unique(self):
        return self

    def all(self):
        return list(self._rows)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


class _RecordingSession:
    """Records every statement `build_league` executes. Answers the sport-key
    lookup with production's real key list and everything else with nothing —
    the rails are what this file is about, and a league with no games still has
    to ASK for them with the right scope."""

    def __init__(self):
        self.statements: list[str] = []

    async def execute(self, statement, *args, **kwargs):
        sql = str(statement.compile(dialect=postgresql.dialect()))
        self.statements.append(sql)
        if sql.strip().startswith("SELECT sports.key \nFROM sports"):
            return _Result(_REGISTERED)
        return _Result([])


def _build(sport_key: str) -> _RecordingSession:
    session = _RecordingSession()
    payload = asyncio.run(build_league(sport_key, session))
    assert isinstance(payload, dict)
    return session


def test_the_atp_page_asks_for_the_us_open():
    """The wiring proof, and the one that would have caught the bug. Every
    assertion above can be green while the route keeps calling the rails with the
    bare tour key."""
    session = _build("tennis_atp")
    widened = [s for s in session.statements if "sports.key IN" in s]
    assert len(widened) == 3, (
        "expected all three games rails to be scoped across the tour's "
        f"tournaments, got {len(widened)} of {len(session.statements)} statements"
    )


def test_a_non_tour_league_pays_no_extra_round_trip():
    """`test_build_league_issues_exactly_four_statements` pins the CFL at four and
    argues that a fifth has to be argued for. This is that argument, scoped: the
    lookup fires only for the two leagues that need it, so 27 of 29 leagues are
    untouched — same statements, same count, same plan."""
    session = _build("americanfootball_cfl")
    assert len(session.statements) == 4, session.statements
    assert not any("sports.key IN" in s for s in session.statements)


def test_the_lookup_prunes_tournaments_with_no_rows_in_the_window():
    """🔴 The scope is a nested loop over the matching `sports` rows, and the
    BitmapOr over `ix_events_status_commence` (~409k index rows, ~584 blocks) is
    rebuilt on EVERY loop. `tennis_atp` has 20 registered tournament keys and 19
    are last season's, so without this filter each dead key costs ~600 blocks to
    contribute nothing and the rails go linear in the size of the tour's history
    instead of additive in what is being played.

    Measured on production 2026-09-06: the filter takes `tennis_atp` from 20
    candidate keys to 1 (`tennis_atp_us_open`) for 2,219 blocks and 9 ms."""
    session = _build("tennis_atp")
    lookups = [s for s in session.statements if s.strip().startswith("SELECT sports.key")]
    assert len(lookups) == 1, session.statements
    sql = lookups[0]
    assert "EXISTS" in sql and "events.commence_time >" in sql, (
        "the tournament lookup stopped bounding itself to the rails' window — "
        f"every dead tournament key is now a wasted loop:\n{sql}"
    )


def test_the_lookup_prefix_escapes_the_underscore():
    """`_` is a single-character wildcard in LIKE and every sport key is full of
    them (gotcha #45's shape). Unescaped, `tennis_atp_%` also matches
    `tennisXatpY…`; the pure function would still reject those, but the SQL would
    quietly read wider than it looks."""
    session = _build("tennis_atp")
    sql = next(s for s in session.statements if s.strip().startswith("SELECT sports.key"))
    assert "ESCAPE" in sql, f"the LIKE prefix lost its escape clause:\n{sql}"


def test_a_tour_league_pays_exactly_one_extra_round_trip():
    """Priced, not assumed. One `SELECT sports.key` over a ~101-row table, once
    per league BUILD (which is cached), to avoid hard-coding a tournament list
    that would be stale by the next Slam."""
    session = _build("tennis_atp")
    assert len(session.statements) == 5, session.statements
    lookups = [s for s in session.statements if s.strip().startswith("SELECT sports.key \nFROM sports")]
    assert len(lookups) == 1, session.statements

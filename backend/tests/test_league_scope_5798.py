"""#5798 — an NFL future must not reach a college game's page, or the reverse.

The specimen these tests are built from, measured on production 2026-09-21
22:54Z: `/api/events/15315931/related-futures` is Kentucky Wildcats @ **South
Alabama Jaguars**, a college game, and ten of South Alabama's forty-nine season
markets were the **Jacksonville Jaguars** — `Pro Football: 2027 AFC Champion`,
`NFL Super Bowl Winner`, `Will the Jacksonville Jaguars make the 2027 NFL
Playoffs?` and seven more. The LA Rams page carried `NCAAF Championship Winner —
Colorado State Rams` the other way.

`league_scope_football_pool_5798.json` is the population that decision was taken
on, captured whole from production (392 rows; the query limit was 1000, so it is
a complete population and not a sample). These tests REPLAY it rather than
asserting against a hand-written shape, so that anyone editing the marker tables
gets the measured answer instead of an opinion.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from sqlalchemy import Column, String

from app.utils import league_scope

NCAAF = "americanfootball_ncaaf"
NFL = "americanfootball_nfl"

_FIXTURE = Path(__file__).parent / "fixtures" / "league_scope_football_pool_5798.json"


@pytest.fixture(scope="module")
def pool() -> list[dict]:
    data = json.loads(_FIXTURE.read_text())
    assert data["row_count"] == 392, "fixture truncated"
    return data["markets"]


# --------------------------------------------------------------------------
# The specimens. These are the rows a reader actually saw.
# --------------------------------------------------------------------------

JACKSONVILLE_ROWS_ON_SOUTH_ALABAMAS_PAGE = [
    ("Pro Football: AFC Team to advance to Divisional Round", "0xeb4633c8"),
    ("Will the Jacksonville Jaguars make the 2027 NFL Playoffs?", "0xa4407ce2"),
    (
        "Will Jacksonville Jaguars advance to the AFC Championship Game in the "
        "2027 NFL Playoffs?",
        "0xea20df3e",
    ),
    ("Pro Football: 2027 AFC Champion ", "203722"),
    ("NFL Super Bowl Winner", "americanfootball_nfl_super_bowl_winner"),
    ("Pro Football: 2027 Champion", "202857"),
    ("Pro Football: Team to Make Postseason", "448179"),
]


@pytest.mark.parametrize("name,ext", JACKSONVILLE_ROWS_ON_SOUTH_ALABAMAS_PAGE)
def test_the_jacksonville_rows_leave_the_college_page(name, ext):
    assert league_scope.is_refused(NCAAF, name, ext) is True


@pytest.mark.parametrize("name,ext", JACKSONVILLE_ROWS_ON_SOUTH_ALABAMAS_PAGE)
def test_the_same_rows_are_kept_on_the_nfl_page(name, ext):
    """The other half of the bar: this is a scope fix, not a deletion."""
    assert league_scope.is_refused(NFL, name, ext) is False


def test_colorado_state_rams_leaves_the_la_rams_page():
    assert (
        league_scope.is_refused(NFL, "NCAAF Championship Winner", "cfb_champ") is True
    )
    assert (
        league_scope.is_refused(NCAAF, "NCAAF Championship Winner", "cfb_champ")
        is False
    )


def test_kentuckys_own_playoff_market_is_never_refused_from_a_college_page():
    """The row the per-tier cap hides today, and which must APPEAR afterwards."""
    assert (
        league_scope.is_refused(
            NCAAF, "Will Kentucky Make the 2026-27 CFB Playoffs?", "0x76938a3a"
        )
        is False
    )


# --------------------------------------------------------------------------
# The second clause. "Refuse the sibling's mark UNLESS this league's own mark is
# also present" is two clauses, and a one-clause implementation is a capability
# regression that no count would show.
# --------------------------------------------------------------------------

DUAL_MARKED = (
    "Will a team from Texas win the 2027 Pro Football Championship or the "
    "2027 College Football National Championship?"
)


def test_a_market_naming_both_leagues_survives_on_both_pages():
    assert league_scope.is_marked(NFL, DUAL_MARKED, "965601") is True
    assert league_scope.is_marked(NCAAF, DUAL_MARKED, "965601") is True
    assert league_scope.is_refused(NFL, DUAL_MARKED, "965601") is False
    assert league_scope.is_refused(NCAAF, DUAL_MARKED, "965601") is False


def test_the_dual_marked_row_is_the_only_one_in_the_population(pool):
    """If this count ever moves, the clause above is being exercised by more
    rows than the one it was written for and the census wants re-reading."""
    both = [
        m
        for m in pool
        if league_scope.is_marked(NFL, m["name"], m["external_id"])
        and league_scope.is_marked(NCAAF, m["name"], m["external_id"])
    ]
    assert [m["name"] for m in both] == [DUAL_MARKED]


# --------------------------------------------------------------------------
# The ADMITTED control. A refusal rule is only safe because it fails open, so
# the unrecognised rows must be pinned as explicitly untouched.
# --------------------------------------------------------------------------

UNMARKED_SIX = [
    "2026 CFL Grey Cup Champion",
    "2027 Steel Bridge National Champion",
    "Big Ten Regular Season Champion",
    "Notre Dame Football to Join a Conference before the 2027-28 Season",
    "Titled Tuesday Winner: September 15",
    "Titled Tuesday Winner: September 22",
]


@pytest.mark.parametrize("name", UNMARKED_SIX)
def test_an_unrecognised_market_keeps_exactly_the_reach_it_has_today(name):
    """These six are an upstream CLASSIFICATION defect (chess and a student
    bridge contest are not football). This module must NOT guess at them —
    guessing would hide the real bug. They keep both pages, as today."""
    assert league_scope.is_refused(NCAAF, name, "KXWHATEVER") is False
    assert league_scope.is_refused(NFL, name, "KXWHATEVER") is False


def test_big_ten_regular_season_is_not_claimed_as_college_football():
    """A bare `Big Ten` marker would swallow this basketball market. The
    conference phrases are anchored on "Championship Game" precisely so they
    do not."""
    assert (
        league_scope.is_marked(
            NCAAF, "Big Ten Regular Season Champion", "KXNCAAMBBIGTENREG-27"
        )
        is False
    )
    assert (
        league_scope.is_marked(
            NCAAF,
            "NCAA Football: Team to Qualify for 2026 Big Ten Championship Game",
            "956320",
        )
        is True
    )


# --------------------------------------------------------------------------
# The census, replayed. These are the numbers #5798 was decided on.
# --------------------------------------------------------------------------


def test_the_population_splits_as_measured(pool):
    counts = {"pro": 0, "college": 0, "both": 0, "neither": 0}
    for m in pool:
        p = league_scope.is_marked(NFL, m["name"], m["external_id"])
        c = league_scope.is_marked(NCAAF, m["name"], m["external_id"])
        counts[
            "both" if (p and c) else "pro" if p else "college" if c else "neither"
        ] += 1
    assert counts == {"pro": 166, "college": 219, "both": 1, "neither": 6}


def test_every_refused_row_is_kept_on_its_own_page(pool):
    """The invariant that makes this a scope fix rather than a loss: nothing the
    population contains is refused from BOTH football pages."""
    orphans = [
        m["name"]
        for m in pool
        if league_scope.is_refused(NCAAF, m["name"], m["external_id"])
        and league_scope.is_refused(NFL, m["name"], m["external_id"])
    ]
    assert orphans == []


def test_the_refusals_are_symmetric_and_substantial(pool):
    """Both directions leak, so a fix that only cleans one page is half a fix."""
    off_college = sum(
        league_scope.is_refused(NCAAF, m["name"], m["external_id"]) for m in pool
    )
    off_nfl = sum(
        league_scope.is_refused(NFL, m["name"], m["external_id"]) for m in pool
    )
    assert (off_college, off_nfl) == (166, 219)


#: Measured on production 2026-09-21, the same pass that produced the fixture.
#: Tiers 1 and 4 are OVER the route's cap today, which is why 38 markets are
#: silently cut and 34 of them are college.
TIER_SIZES_BEFORE = {1: 107, 2: 100, 3: 54, 4: 131}
TIER_SIZES_AFTER_NCAAF = {1: 96, 2: 40, 3: 29, 4: 61}
TIER_SIZES_AFTER_NFL = {1: 17, 2: 61, 3: 25, 4: 70}


def test_the_split_pulls_every_tier_back_under_the_routes_own_cap():
    """The second half of the ship, and the reason this filter runs in SQL rather
    than as a post-filter: it has to act BEFORE the cap to give those rows back.

    Reads the route's real constant, so raising or lowering the cap makes this
    test speak rather than silently agree."""
    from app.routes.events import SEASON_TIER_CAP

    assert max(TIER_SIZES_BEFORE.values()) > SEASON_TIER_CAP, (
        "the census says tier 4 held 131 rows against the cap — if that is no "
        "longer true the 38 cut markets need re-counting before trusting this"
    )
    cut_before = sum(max(0, n - SEASON_TIER_CAP) for n in TIER_SIZES_BEFORE.values())
    assert cut_before == 38

    for league, tiers in (
        ("ncaaf", TIER_SIZES_AFTER_NCAAF),
        ("nfl", TIER_SIZES_AFTER_NFL),
    ):
        assert max(tiers.values()) <= SEASON_TIER_CAP, f"{league} still capped"


def test_the_measured_tier_sizes_add_up_to_the_fixture(pool):
    """Keeps the three tables above honest against the population they came
    from — a transcribed number that no longer sums is a stale census."""
    assert sum(TIER_SIZES_BEFORE.values()) == len(pool) == 392
    # every row lands on at least one league's page, and the dual/unmarked rows
    # land on both, so the two post-split totals overcount the pool by exactly
    # the 7 rows that are served twice.
    served_twice = 1 + len(UNMARKED_SIX)
    assert (
        sum(TIER_SIZES_AFTER_NCAAF.values()) + sum(TIER_SIZES_AFTER_NFL.values())
        == len(pool) + served_twice
    )


# --------------------------------------------------------------------------
# Rig guards.
# --------------------------------------------------------------------------


def test_a_sport_with_no_sibling_gets_no_condition_at_all():
    """Returning None rather than a tautology is what keeps every other sport's
    query byte-identical, so this change cannot cost baseball a row."""
    for key in ("baseball_mlb", "soccer_epl", "basketball_nba", "", None):
        assert (
            league_scope.exclusion_condition(
                key, Column("name", String), Column("external_id", String)
            )
            is None
        )


def test_the_football_pair_does_get_a_condition():
    for key in (NFL, NCAAF):
        cond = league_scope.exclusion_condition(
            key, Column("name", String), Column("external_id", String)
        )
        assert cond is not None
        assert "~*" in str(cond.compile(compile_kwargs={"literal_binds": True}))


def test_a_null_column_cannot_make_the_predicate_fail_closed():
    r"""`NULL ~* 'x'` is NULL and `NOT NULL` is NULL, so an un-COALESCEd predicate
    would silently DROP any market with a NULL name or external_id — the exact
    opposite of a rule that is supposed to fail open."""
    for key in (NFL, NCAAF):
        sql = str(
            league_scope.exclusion_condition(
                key, Column("name", String), Column("external_id", String)
            ).compile(compile_kwargs={"literal_binds": True})
        )
        assert sql.count("coalesce") == 6, sql
        assert "~*" in sql
    # and the pure side agrees that None is simply unmarked, never refused
    assert league_scope.is_marked(NFL, None, None) is False
    assert league_scope.is_refused(NFL, None, None) is False
    assert league_scope.is_refused(NCAAF, None, None) is False


def test_the_sql_and_python_regex_dialects_cannot_drift():
    r"""`\y` is Postgres's word boundary and `\b` is Python's, and the SQL runs on
    production while the tests run on the Python form. Anything beyond that one
    substitution — a `\b`, a `\d`, a lookahead — means the two dialects are no
    longer the same rule and the census above stops describing production."""
    allowed = re.compile(r"^[a-z0-9 |()\\y.\-]+$")
    for key, mark in league_scope.LEAGUE_MARKS.items():
        assert allowed.match(mark.name_pattern), f"{key}: unportable regex construct"
        assert r"\b" not in mark.name_pattern, f"{key}: \\b is not Postgres syntax"
        assert mark.python_pattern == mark.name_pattern.replace(r"\y", r"\b")
        re.compile(mark.python_pattern)  # must be a valid Python regex too


def test_the_sibling_table_is_symmetric():
    for key, sibling in league_scope.SIBLING_LEAGUES.items():
        assert league_scope.SIBLING_LEAGUES[sibling] == key
        assert key in league_scope.LEAGUE_MARKS
        assert sibling in league_scope.LEAGUE_MARKS

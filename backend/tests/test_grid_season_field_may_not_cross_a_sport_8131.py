"""#8131 — a college football grid printed a women's basketball record.

`https://bainluck.com/playoffs/ncaa-football`, production 2026-09-23, row 21:

    BYU Cougars  22-10

A college football team cannot be 22-10; that is 32 games. The value is unique
to `teams` row 2408, `basketball_wncaab`, so the served row identifies itself
rather than being inferred from the picture.

THE OBVIOUS FIX IS THE WRONG ONE. There is no BYU row in
`americanfootball_ncaaf` at all — verified, along with Arizona's and Kentucky's
— so this is not "the grid picked the wrong row among several" and preferring
the in-scope row repairs nothing: an out-of-scope row wins the key because it
is the ONLY claimant, and it brings its own season with it.

So the rule is the mirror of `_VISUAL_IDENTITY_FIELDS` (#8084 arm B), which
already says this in one direction and is only honoured for INHERITANCE:

    A CLUB'S CREST AND COLOURS BELONG TO THE CLUB; ITS RECORD BELONGS TO A
    SEASON.

A crest crosses a sport boundary correctly — BYU's crest is BYU's whichever
team wears it — and a record does not. Nothing honoured that when the WINNING
row was itself out of sport.

WHY THE TEST IS THE SPORT AND NOT THE SCOPE, WHICH IS THE HALF THAT NEEDS
GUARDING IN BOTH DIRECTIONS. Censused over all 398 rows the 13 warm grids serve
on 2026-09-23: five rows win a key from outside their grid's scope. THREE cross
a sport boundary, all on `/playoffs/ncaa-football`, all carrying nothing but an
impossible record —

    BYU Cougars       <- 2408  basketball_wncaab  22-10  (32 games)
    Arizona Wildcats  <- 14625 baseball_ncaa      19-32  (51 games)
    Kentucky Wildcats <- 3615  baseball_ncaa      33-23  (56 games)

— and TWO are out of scope WITHIN their sport: `Manchester United` (11861,
`soccer_uefa_champs_league_women`) and `Real Betis` (5670,
`soccer_uefa_europa_league`) on the Champions League grid. A club's domestic
record is what a reader expects on a European grid, so a rule keyed on SCOPE
would blank a correct record the moment such a row carries one. Both carry none
today, which is exactly why a census of today's surface alone cannot see the
hazard and why the second test below is not decoration: an implementation that
suppresses on scope passes the first test and fails that one.

Three-way diff of the shipped predicate against production: LOST 3 (the three
records above), GAINED 0, REDIRECTED 0 — purely subtractive, so it cannot
introduce a new wrong answer.
"""

import pytest

from app.routes.playoffs import _get_team_metadata

BYU_CREST = "https://a.espncdn.com/i/teamlogos/ncaa/500/252.png"
BETIS_CREST = "https://a.espncdn.com/i/teamlogos/soccer/500/244.png"


class _FakeSport:
    def __init__(self, key):
        self.key = key


class _FakeTeam:
    """Only the attributes `_get_team_metadata` reads."""

    def __init__(
        self,
        team_id,
        name,
        sport_key,
        espn_id=None,
        abbreviation=None,
        alternate_names=None,
        record=None,
        logo=None,
        primary_color=None,
        secondary_color=None,
        standings_data=None,
    ):
        self.id = team_id
        self.name = name
        self.sport = _FakeSport(sport_key)
        self.espn_id = espn_id
        self.abbreviation = abbreviation
        self.alternate_names = list(alternate_names or [])
        self.current_record = record
        self.logo_url_small = logo
        self.logo_url_large = None
        self.primary_color = primary_color
        self.secondary_color = secondary_color
        self.standings_data = standings_data


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)


async def _lookup(rows, league_slug, names):
    return await _get_team_metadata(
        _FakeSession(rows), set(names), league_slug=league_slug
    )


# --- The production specimens, as production holds them ---------------------


def _byu_womens_hoops():
    """Row 2408 — the only BYU claimant the football grid has."""
    return _FakeTeam(
        2408,
        "BYU Cougars",
        "basketball_wncaab",
        abbreviation="BYU",
        record="22-10",
        logo=BYU_CREST,
        primary_color="#002E5D",
        standings_data={"conference": "West Coast", "position": 4},
    )


def _arizona_baseball():
    """Row 14625 — named `Arizona`, and it takes the key `arizona wildcats`
    through its `alternate_names`. The suppression has to reach the ALIAS keys
    a row writes, not just its own name, because one `meta` serves them all."""
    return _FakeTeam(
        14625,
        "Arizona",
        "baseball_ncaa",
        espn_id="60",
        abbreviation="ARIZ",
        alternate_names=["Wildcats", "Arizona Wildcats"],
        record="19-32",
    )


def _betis_la_liga():
    """A La Liga row on the Champions League grid: out of scope, same sport,
    and carrying the club's real domestic record."""
    return _FakeTeam(
        2194,
        "Real Betis",
        "soccer_spain_la_liga",
        espn_id="244",
        record="4-2-1",
        logo=BETIS_CREST,
    )


# --- The ship ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_basketball_record_is_not_served_on_the_football_grid():
    """THE SPECIMEN. Revert the suppression and `record` reads `22-10`."""
    meta = await _lookup([_byu_womens_hoops()], "ncaa-football", {"BYU Cougars"})
    row = meta["byu cougars"]

    assert row["record"] is None, (
        "the College Football Playoff grid is printing 22-10 for BYU — a "
        "women's basketball season (32 games) served because no "
        "americanfootball_ncaaf row exists to beat it"
    )


@pytest.mark.asyncio
async def test_a_domestic_record_survives_on_a_european_grid():
    """THE DIRECTION A SCOPE-KEYED IMPLEMENTATION FAILS.

    Real Betis' La Liga row is out of scope for `champions-league` and is the
    only claimant, so it wins the key and serves `4-2-1`. That is the club's
    real record and a reader expects it on a European grid. Suppressing on
    scope rather than on SPORT blanks it; the coarse family test cannot reach
    it, because `soccer_spain_la_liga` and `soccer_uefa_champs_league` are one
    sport.
    """
    meta = await _lookup([_betis_la_liga()], "champions-league", {"Real Betis"})
    row = meta["real betis"]

    assert row["record"] == "4-2-1", (
        "a correct domestic record has been blanked on the Champions League "
        "grid — the rule is keyed on scope, not on sport"
    )
    assert row["team_id"] == 2194


@pytest.mark.asyncio
async def test_the_crest_still_crosses_the_boundary_the_record_may_not():
    """The mirror of `_VISUAL_IDENTITY_FIELDS`, held in one assertion.

    BYU's crest is BYU's whichever team wears it, so suppressing the season
    must not take the visual identity down with it. A bare row is a far smaller
    harm than a wrong number, and a crestless row is a harm for nothing.
    """
    meta = await _lookup([_byu_womens_hoops()], "ncaa-football", {"BYU Cougars"})
    row = meta["byu cougars"]

    assert row["logo_url"] == BYU_CREST, "the suppression took the crest with it"
    assert row["primary_color"] == "#002E5D"
    assert row["team_id"] == 2408, "the suppression is not a re-rank"


@pytest.mark.asyncio
async def test_every_season_field_crosses_or_none_of_them_do():
    """`record` is the one a reader caught; the other three ride the same row.

    `standings_data` gives this row a West Coast Conference and a position, both
    true of a basketball season. A fix that dropped only `record` would leave a
    basketball conference and seed on a football grid.
    """
    meta = await _lookup([_byu_womens_hoops()], "ncaa-football", {"BYU Cougars"})
    row = meta["byu cougars"]

    assert row["record"] is None
    assert row["conference"] is None, "a basketball conference on a football grid"
    assert row["division"] is None
    assert row["seed"] is None, "a basketball seed on a football grid"


@pytest.mark.asyncio
async def test_the_suppression_reaches_the_alias_keys_a_row_writes():
    """One `meta` object serves a row's own name AND every alias it claims.

    Row 14625 is named `Arizona` and reaches the football grid only as
    `Arizona Wildcats`, through `alternate_names` — so a suppression applied at
    the write of the row's own name and not to the shared `meta` would miss the
    key the reader actually sees.
    """
    meta = await _lookup(
        [_arizona_baseball()], "ncaa-football", {"Arizona", "Arizona Wildcats"}
    )

    assert meta["arizona wildcats"]["record"] is None, (
        "19-32 (51 games) is a baseball season, served under the alias key the "
        "football grid renders"
    )
    assert meta["arizona"]["record"] is None


@pytest.mark.asyncio
async def test_an_in_scope_row_keeps_its_own_season():
    """The overwhelming majority — 386 of 398 served rows. The predicate cannot
    fire on them, and this pins that it does not."""
    row = _FakeTeam(
        15936,
        "Arizona State Sun Devils",
        "americanfootball_ncaaf",
        record="1-1",
        standings_data={"conference": "Big 12", "position": 7},
    )
    meta = await _lookup([row], "ncaa-football", {"Arizona State Sun Devils"})

    assert meta["arizona state sun devils"]["record"] == "1-1"
    assert meta["arizona state sun devils"]["conference"] == "Big 12"


@pytest.mark.asyncio
async def test_no_league_config_suppresses_nothing():
    """FAIL CLOSED. `_get_team_metadata` is also called with no slug, which
    means no scope and so no opinion about which sport the caller is about. An
    empty scope must change nothing rather than blanking every record."""
    meta = await _lookup([_byu_womens_hoops()], "", {"BYU Cougars"})

    assert meta["byu cougars"]["record"] == "22-10", (
        "with no league config there is no sport to be out of, so the "
        "suppression must not fire"
    )

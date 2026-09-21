"""#7727 — an alias may not claim another club's own name.

A reader on `/sport/basketball/ncaab` saw a "Biggest Movers (24h)" chip reading
**Texas Tech Red Raiders** beside **Auburn's** crest, and the grid row below it
carried `AUB` and Auburn's `22-16`. Auburn had no row at all on a 68-row grid.

The cause is one row claiming another club's name. Measured on production
2026-09-21:

    271  Auburn Tigers  AUB  espn 2     alternate_names [... 'Texas Tech Red Raiders' ...]
    200  Texas Tech Red Raiders  TTU  espn 2641

`_get_team_metadata` indexes a row under its name, its abbreviation and every
alternate name, last-one-wins by `id` within a scope tier. `271 > 200`, so
Auburn's *alias* overwrote Texas Tech's *own name* and the grid's second merge
pass — which folds rows sharing a `team_id` — then merged the two schools into
one row. Same shape: `Akron Zips` claims `Michigan Wolverines`;
`Oklahoma St Cowgirls` claims `Oklahoma Sooners`; `Inter Miami CF` claims
`Atlanta United FC`.

THE DISCRIMINATOR IS THE ANCHOR, NOT THE NAME. Most keys where an alias beats a
name are one club holding two rows — `Bournemouth`/`AFC Bournemouth` share
`espn_id` 349 and alias each other — and there the alias winning is the
behaviour #7675 and #6230 are built on. Measured over ten league scopes, the
anchored rule rebinds 7 keys (every one to the correct club) and leaves 41
byte-identical; a blanket "name beats alias" rule would have disturbed all 48,
including the three EPL rows #7675 had just repaired.

Every specimen here is a PAIR, because a guard whose job is to stop one row
taking another's key cannot be tested with one row: delete the guard and a lone
row still resolves to itself.
"""

import pytest

from app.routes.playoffs import _get_team_metadata


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
    ):
        self.id = team_id
        self.name = name
        self.sport = _FakeSport(sport_key)
        self.espn_id = espn_id
        self.abbreviation = abbreviation
        self.alternate_names = list(alternate_names or [])
        self.current_record = record
        self.logo_url_small = None
        self.logo_url_large = None
        self.primary_color = None
        self.secondary_color = None
        self.standings_data = None


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


async def _lookup(rows, league_slug):
    return await _get_team_metadata(
        _FakeSession(rows), {"anything"}, league_slug=league_slug
    )


# --- The production specimens, as rows -------------------------------------

def _auburn():
    return _FakeTeam(
        271, "Auburn Tigers", "basketball_ncaab", espn_id="2", abbreviation="AUB",
        alternate_names=["Texas Tech", "Texas Tech Red Raiders", "Tigers",
                         "Red Raiders", "Auburn"],
        record="22-16",
    )


def _texas_tech():
    return _FakeTeam(
        200, "Texas Tech Red Raiders", "basketball_ncaab", espn_id="2641",
        abbreviation="TTU", alternate_names=["Red Raiders", "Texas Tech"],
        record="19-15",
    )


def _akron():
    return _FakeTeam(
        3113, "Akron Zips", "basketball_ncaab", espn_id="2006", abbreviation="AKR",
        alternate_names=["Michigan Wolverines", "Michigan", "Wolverines",
                         "Eastern Michigan Eagles", "Eagles", "Akron",
                         "E Michigan", "Zips"],
        record="29-6",
    )


def _michigan():
    return _FakeTeam(
        51, "Michigan Wolverines", "basketball_ncaab", espn_id="130",
        abbreviation="MICH", alternate_names=["Wolverines", "Michigan"],
        record="22-12",
    )


def _eastern_michigan_unanchored():
    # espn_id IS NULL on production (#7676's family): no anchor channel.
    return _FakeTeam(
        1163, "Eastern Michigan Eagles", "basketball_ncaab", espn_id=None,
        abbreviation=None, alternate_names=[], record=None,
    )


def _bournemouth():
    return _FakeTeam(
        137, "Bournemouth", "soccer_epl", espn_id="349", abbreviation="BOU",
        alternate_names=["AFC Bournemouth"], record="0-3-2",
    )


def _afc_bournemouth():
    return _FakeTeam(
        14203, "AFC Bournemouth", "soccer_epl", espn_id="349", abbreviation="BOU",
        alternate_names=["Bournemouth"], record="0-3-2",
    )


# --- THE SHIP ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_a_differently_anchored_alias_does_not_take_texas_techs_own_name():
    """The photographed defect: `Auburn` (id 271) claimed `Texas Tech` (id 200)."""
    meta = await _lookup([_texas_tech(), _auburn()], "ncaa-basketball")

    assert meta["texas tech red raiders"]["team_id"] == 200
    assert meta["texas tech red raiders"]["record"] == "19-15"
    assert meta["texas tech red raiders"]["abbreviation"] == "TTU"


@pytest.mark.asyncio
async def test_the_claiming_row_keeps_its_own_identity():
    """Auburn must not be *deleted* by the repair — only stop impersonating."""
    meta = await _lookup([_texas_tech(), _auburn()], "ncaa-basketball")

    assert meta["auburn tigers"]["team_id"] == 271
    assert meta["auburn tigers"]["record"] == "22-16"


@pytest.mark.asyncio
async def test_the_result_does_not_depend_on_the_order_rows_arrive_in():
    """The real query has no ORDER BY; a fix that works one way round is luck."""
    forward = await _lookup([_texas_tech(), _auburn()], "ncaa-basketball")
    reverse = await _lookup([_auburn(), _texas_tech()], "ncaa-basketball")

    assert forward["texas tech red raiders"]["team_id"] == 200
    assert reverse["texas tech red raiders"]["team_id"] == 200


@pytest.mark.asyncio
async def test_the_second_production_pair_akron_claiming_michigan():
    meta = await _lookup([_michigan(), _akron()], "ncaa-basketball")

    assert meta["michigan wolverines"]["team_id"] == 51
    assert meta["akron zips"]["team_id"] == 3113


@pytest.mark.asyncio
async def test_an_abbreviation_is_a_claim_too():
    """`Saint Louis Billikens` carries abbreviation `UK` on production."""
    kentucky = _FakeTeam(2, "UK", "basketball_ncaab", espn_id="96")
    billikens = _FakeTeam(
        6878, "Saint Louis Billikens", "basketball_ncaab", espn_id="139",
        abbreviation="UK",
    )
    meta = await _lookup([kentucky, billikens], "ncaa-basketball")

    assert meta["uk"]["team_id"] == 2


# --- THE HELD CONTROLS: these must NOT move (gotcha #43, both directions) ---

@pytest.mark.asyncio
async def test_one_club_two_rows_is_untouched_so_7675_cannot_regress():
    """`Bournemouth` and `AFC Bournemouth` share anchor 349 and alias each other.

    Highest `id` still wins. This is the rule #6230 and #7675 rely on; a repair
    that "fixes" this pair has broken the grid's record and crest selection.
    """
    meta = await _lookup(
        [_bournemouth(), _afc_bournemouth()], "epl"
    )

    assert meta["bournemouth"]["team_id"] == 14203
    assert meta["afc bournemouth"]["team_id"] == 14203


@pytest.mark.asyncio
async def test_an_unanchored_victim_fails_closed_and_keeps_todays_answer():
    """Eastern Michigan has no `espn_id`, so the anchored rule cannot speak.

    It must leave the row exactly where it was rather than guess from the name
    — those rows need the anchor channel (#7676), not a looser name rule.
    """
    meta = await _lookup(
        [_eastern_michigan_unanchored(), _akron()], "ncaa-basketball"
    )

    assert meta["eastern michigan eagles"]["team_id"] == 3113


@pytest.mark.asyncio
async def test_an_unanchored_claimant_also_fails_closed():
    claimant = _FakeTeam(
        900, "Central Arkansas Bears", "basketball_ncaab", espn_id=None,
        alternate_names=["Arkansas Razorbacks"],
    )
    arkansas = _FakeTeam(
        266, "Arkansas Razorbacks", "basketball_ncaab", espn_id="8",
    )
    meta = await _lookup([arkansas, claimant], "ncaa-basketball")

    assert meta["arkansas razorbacks"]["team_id"] == 900


@pytest.mark.asyncio
async def test_in_scope_still_beats_out_of_scope_even_when_it_is_an_alias():
    """Scope supremacy is #6230's whole repair and is deliberately untouched."""
    out_of_scope_name = _FakeTeam(
        5, "Minnesota Twins", "baseball_mlb_preseason", espn_id="99",
        record="10-18-1",
    )
    in_scope_alias = _FakeTeam(
        10739, "Twins", "baseball_mlb", espn_id="100",
        alternate_names=["Minnesota Twins"], record="70-79",
    )
    meta = await _lookup([out_of_scope_name, in_scope_alias], "mlb")

    assert meta["minnesota twins"]["record"] == "70-79"


@pytest.mark.asyncio
async def test_an_alias_nobody_owns_as_a_name_is_still_indexed():
    """The guard refuses collisions; it must not drop aliases wholesale."""
    meta = await _lookup([_texas_tech(), _auburn()], "ncaa-basketball")

    # "Red Raiders" is nobody's canonical name, so the collision rule is silent
    # and the existing highest-`id` order still decides it.
    assert meta["red raiders"]["team_id"] == 271
    assert meta["tigers"]["team_id"] == 271


@pytest.mark.asyncio
async def test_a_row_may_still_alias_its_own_name():
    solo = _FakeTeam(
        7, "Las Vegas Aces", "basketball_wnba", espn_id="17",
        alternate_names=["Las Vegas Aces", "Aces"],
    )
    meta = await _lookup([solo], "wnba")

    assert meta["las vegas aces"]["team_id"] == 7
    assert meta["aces"]["team_id"] == 7


@pytest.mark.asyncio
async def test_the_name_owner_is_read_in_ranked_order_not_arrival_order():
    """Which row "owns" a name must be decided the same way the write order is.

    One club holds an out-of-scope row and an in-scope row under the same name.
    Read in arrival order the owner is the out-of-scope row, which puts the
    claimant in a *different* tier and lets it through; read in ranked order —
    the order the lookup itself writes in — the owner is the in-scope row and
    the claim is refused. Only the ranked read gives the same answer the rest
    of this function is built on.
    """
    in_scope_row = _FakeTeam(400, "Union Berlin", "soccer_germany_bundesliga",
                             espn_id="1000", record="2-1-2")
    out_of_scope_row = _FakeTeam(500, "Union Berlin", "soccer_germany_cup",
                                 espn_id="1000", record=None)
    claimant = _FakeTeam(600, "Hertha Berlin", "soccer_germany_bundesliga",
                         espn_id="2000", alternate_names=["Union Berlin"])
    meta = await _lookup(
        [in_scope_row, out_of_scope_row, claimant], "bundesliga"
    )

    assert meta["union berlin"]["team_id"] == 400


@pytest.mark.asyncio
async def test_one_clubs_two_rows_agree_even_when_one_anchor_is_an_int():
    """`espn_id` is a String column, but nothing stops a caller handing an int.

    Comparing `2` to `"2"` would read one club's two rows as two clubs and
    rebind a key this repair is specifically required to leave alone.
    """
    as_text = _FakeTeam(137, "Bournemouth", "soccer_epl", espn_id="349",
                        alternate_names=["AFC Bournemouth"], record="0-3-2")
    as_int = _FakeTeam(14203, "AFC Bournemouth", "soccer_epl", espn_id=349,
                       alternate_names=["Bournemouth"], record="0-3-2")
    meta = await _lookup([as_text, as_int], "epl")

    assert meta["bournemouth"]["team_id"] == 14203


@pytest.mark.asyncio
async def test_a_lower_id_claimant_was_already_losing_and_still_loses():
    """The guard must not invert the cases that were already correct."""
    claimant = _FakeTeam(
        10, "Colorado St Rams", "basketball_wncaab", espn_id="36",
        alternate_names=["Colorado Buffaloes"],
    )
    buffaloes = _FakeTeam(
        190, "Colorado Buffaloes", "basketball_wncaab", espn_id="38",
    )
    meta = await _lookup([claimant, buffaloes], "ncaa-women-basketball")

    assert meta["colorado buffaloes"]["team_id"] == 190

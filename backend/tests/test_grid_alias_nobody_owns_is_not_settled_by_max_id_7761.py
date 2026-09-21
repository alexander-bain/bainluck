"""#7761 — an alias key that is nobody's own name is not settled by `max(id)`.

A reader on `/sport/basketball/wncaab` saw the row labelled **Oklahoma** wearing
**Oklahoma State's** crest and `24-10` record, and the row labelled **West
Virginia** wearing **Utah's** row — blank crest included, because `Utah Utes`
has no `espn_id`. Served payload, production 2026-09-21 09:32Z:

    'Oklahoma'       team_id=2400 -> "Oklahoma St Cowgirls"  espn 197
    'West Virginia'  team_id=2407 -> "Utah Utes"             espn NULL

#7727 fixed the arm where the contested key IS some row's canonical name. This
is the other arm, and it is the one the venues actually exercise: college feeds
publish BARE SCHOOL NAMES. `oklahoma` is nobody's canonical name — `Oklahoma
Sooners` is — so `canonical_owners.get("oklahoma")` is None, #7727's guard
returns True unconditionally, and the key falls through to last-one-wins by
`id`. `Oklahoma St Cowgirls` is 2400 and `Oklahoma Sooners` is 235; nothing
about the choice is about truth, 2400 > 235 is the whole reason.

Thirteen unrelated schools claim to be West Virginia. The one that IS West
Virginia is the one whose own name the alias LEADS — a fact, available without
an anchor, that settles a 13-way contest. Where even that ties between two
differently-anchored clubs (`new york` is not the Yankees rather than the Mets)
the key is refused rather than guessed.

Measured over all 9,958 `teams` rows: 659 ownerless contested keys, 599 keep
today's winner byte-for-byte, 56 rebind (every one to the correct club) and 4
refuse. The controls at the bottom hold the 599 and #7727's own arm in place.

Every specimen here is a CONTEST, because a rule whose job is to choose between
claimants cannot be tested with one claimant: delete the rule and a lone row
still resolves to itself.
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


_WNCAAB = "basketball_wncaab"
_SLUG = "ncaa-women-basketball"


# --- The production specimens, as rows -------------------------------------

def _sooners():
    return _FakeTeam(
        235, "Oklahoma Sooners", _WNCAAB, espn_id="201", abbreviation="OU",
        alternate_names=["Hawkeyes", "Sooners", "Iowa", "Oklahoma",
                         "Iowa Hawkeyes"],
        record="18-12",
    )


def _cowgirls():
    return _FakeTeam(
        2400, "Oklahoma St Cowgirls", _WNCAAB, espn_id="197", abbreviation="OKST",
        alternate_names=["Sooners", "Oklahoma", "Cowgirls", "Oklahoma Sooners",
                         "Oklahoma St"],
        record="24-10",
    )


def _mountaineers():
    return _FakeTeam(
        149, "West Virginia Mountaineers", _WNCAAB, espn_id="277",
        abbreviation="WVU", alternate_names=["Mountaineers", "West Virginia"],
        record="18-11",
    )


def _utah():
    # espn_id IS NULL on production — the blank crest the reader saw.
    return _FakeTeam(
        2407, "Utah Utes", _WNCAAB, espn_id=None, abbreviation="UTAH",
        alternate_names=["West Virginia", "West Virginia Mountaineers", "Utes"],
        record="22-9",
    )


def _princeton():
    return _FakeTeam(
        120, "Princeton Tigers", _WNCAAB, espn_id="163", abbreviation="PRIN",
        alternate_names=["Princeton", "West Virginia Mountaineers",
                         "West Virginia", "Tigers", "Mountaineers"],
    )


def _georgetown():
    return _FakeTeam(
        2399, "Georgetown Hoyas", _WNCAAB, espn_id="46",
        alternate_names=["West Virginia", "West Virginia Mountaineers"],
    )


def _arizona_state():
    return _FakeTeam(
        2415, "Arizona St Sun Devils", _WNCAAB, espn_id="9",
        alternate_names=["West Virginia", "West Virginia Mountaineers"],
    )


# --- THE SHIP ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_oklahoma_is_the_sooners_not_oklahoma_state():
    """The photographed defect: the bare school name went to the bigger `id`."""
    meta = await _lookup([_sooners(), _cowgirls()], _SLUG)

    assert meta["oklahoma"]["team_id"] == 235
    assert meta["oklahoma"]["record"] == "18-12"
    assert meta["oklahoma"]["espn_id"] == "201"


@pytest.mark.asyncio
async def test_oklahoma_state_keeps_its_own_identity():
    """The repair must stop the impersonation, not delete the claimant."""
    meta = await _lookup([_sooners(), _cowgirls()], _SLUG)

    assert meta["oklahoma st cowgirls"]["team_id"] == 2400
    assert meta["oklahoma st cowgirls"]["record"] == "24-10"


@pytest.mark.asyncio
async def test_west_virginia_beats_twelve_impostors_including_utah():
    """The second photographed defect, at its production width."""
    meta = await _lookup(
        [_princeton(), _mountaineers(), _georgetown(), _utah(), _arizona_state()],
        _SLUG,
    )

    assert meta["west virginia"]["team_id"] == 149
    assert meta["west virginia"]["espn_id"] == "277"
    assert meta["west virginia"]["abbreviation"] == "WVU"


@pytest.mark.asyncio
async def test_the_blank_crest_was_the_impersonation_not_a_missing_image():
    """`Utah Utes` has no `espn_id`; serving it under West Virginia is the bug."""
    meta = await _lookup([_mountaineers(), _utah()], _SLUG)

    assert meta["west virginia"]["espn_id"] is not None
    assert meta["utah utes"]["team_id"] == 2407


@pytest.mark.asyncio
async def test_the_result_does_not_depend_on_the_order_rows_arrive_in():
    """The real query has no ORDER BY; a fix that works one way round is luck."""
    forward = await _lookup([_sooners(), _cowgirls()], _SLUG)
    reverse = await _lookup([_cowgirls(), _sooners()], _SLUG)

    assert forward["oklahoma"]["team_id"] == 235
    assert reverse["oklahoma"]["team_id"] == 235


@pytest.mark.asyncio
async def test_a_lower_id_impostor_is_refused_too_so_the_rule_is_not_min_id():
    """Flipping `max(id)` to `min(id)` is a different arbitrary rule, not a fix.

    Here the impostor holds the SMALLER `id`, so a `min(id)` rule would serve
    it and today's `max(id)` rule already gets this key right.
    """
    impostor = _FakeTeam(
        7, "Colorado St Rams", _WNCAAB, espn_id="36",
        alternate_names=["Colorado"], record="9-21",
    )
    buffaloes = _FakeTeam(
        190, "Colorado Buffaloes", _WNCAAB, espn_id="38",
        alternate_names=["Colorado"], record="22-9",
    )
    meta = await _lookup([impostor, buffaloes], _SLUG)

    assert meta["colorado"]["team_id"] == 190


@pytest.mark.asyncio
async def test_the_alias_must_LEAD_the_name_not_merely_appear_in_it():
    """Token-wise prefix, not substring: `land` does not lead `Cleveland`.

    A substring test would hand `land` to Cleveland and re-introduce exactly
    the class of wrong answer this rule exists to remove.
    """
    cleveland = _FakeTeam(
        5, "Cleveland Cavaliers", "basketball_nba", espn_id="5",
        alternate_names=["Land"],
    )
    portland = _FakeTeam(
        22, "Portland Trail Blazers", "basketball_nba", espn_id="22",
        alternate_names=["Land"],
    )
    meta = await _lookup([cleveland, portland], "nba")

    # Neither name is LED by "land", so nothing is true here and today's
    # highest-`id` order stands rather than a fresh guess.
    assert meta["land"]["team_id"] == 22


@pytest.mark.asyncio
async def test_two_differently_anchored_clubs_that_tie_are_refused_not_guessed():
    """`New York` is not the Yankees rather than the Mets. Serve neither."""
    yankees = _FakeTeam(
        6610, "New York Yankees", "baseball_mlb", espn_id="10",
        alternate_names=["New York"], record="90-60",
    )
    mets = _FakeTeam(
        10737, "New York Mets", "baseball_mlb", espn_id="21",
        alternate_names=["New York"], record="85-65",
    )
    meta = await _lookup([yankees, mets], "mlb")

    assert "new york" not in meta
    # Refusing the ambiguous key must not cost either club its own row.
    assert meta["new york yankees"]["team_id"] == 6610
    assert meta["new york mets"]["team_id"] == 10737


# --- THE HELD CONTROLS: these must NOT move (gotcha #43, both directions) ---

@pytest.mark.asyncio
async def test_an_uncontested_alias_is_still_indexed():
    """The rule settles contests; it must not drop aliases wholesale."""
    solo = _FakeTeam(
        7, "Las Vegas Aces", "basketball_wnba", espn_id="17",
        alternate_names=["Aces", "LVA"],
    )
    meta = await _lookup([solo], "wnba")

    assert meta["aces"]["team_id"] == 7
    assert meta["lva"]["team_id"] == 7


@pytest.mark.asyncio
async def test_one_club_two_rows_still_takes_the_highest_id_so_7675_holds():
    """Tied finalists sharing an anchor are one club — #6230/#7675's rule."""
    bournemouth = _FakeTeam(
        137, "Bournemouth", "soccer_epl", espn_id="349",
        alternate_names=["The Cherries"], record="0-3-2",
    )
    afc = _FakeTeam(
        14203, "AFC Bournemouth", "soccer_epl", espn_id="349",
        alternate_names=["The Cherries"], record="0-3-2",
    )
    meta = await _lookup([bournemouth, afc], "epl")

    assert meta["the cherries"]["team_id"] == 14203


@pytest.mark.asyncio
async def test_a_contest_that_no_rule_can_settle_keeps_todays_answer():
    """`Red Raiders` leads neither name and both rows are anchored.

    Nothing true is available, so the existing highest-`id` order stands — a
    refusal here would drop a key that has been serving correctly.
    """
    auburn = _FakeTeam(
        271, "Auburn Tigers", "basketball_ncaab", espn_id="2",
        alternate_names=["Red Raiders"],
    )
    texas_tech = _FakeTeam(
        200, "Texas Tech Red Raiders", "basketball_ncaab", espn_id="2641",
        alternate_names=["Red Raiders"],
    )
    meta = await _lookup([auburn, texas_tech], "ncaa-basketball")

    assert meta["red raiders"]["team_id"] == 271


@pytest.mark.asyncio
async def test_scope_still_decides_before_any_of_this():
    """An in-scope row beats an out-of-scope one even when it leads with less.

    `Twins` is out-of-scope and led by the alias; the in-scope row is not led
    by it at all. Scope must still win, or #6230's spring-training repair goes
    back out — the tiers are never mixed.
    """
    out_of_scope = _FakeTeam(
        5, "Minnesota Twins", "baseball_mlb_preseason", espn_id="99",
        alternate_names=["Minnesota"], record="10-18-1",
    )
    in_scope = _FakeTeam(
        10739, "Twins Of Minnesota", "baseball_mlb", espn_id="100",
        alternate_names=["Minnesota"], record="70-79",
    )
    meta = await _lookup([out_of_scope, in_scope], "mlb")

    assert meta["minnesota"]["record"] == "70-79"


@pytest.mark.asyncio
async def test_7727s_arm_is_untouched_a_name_still_beats_an_alias():
    """The contested key here IS a canonical name, so the other rule owns it."""
    auburn = _FakeTeam(
        271, "Auburn Tigers", "basketball_ncaab", espn_id="2", abbreviation="AUB",
        alternate_names=["Texas Tech Red Raiders"], record="22-16",
    )
    texas_tech = _FakeTeam(
        200, "Texas Tech Red Raiders", "basketball_ncaab", espn_id="2641",
        abbreviation="TTU", record="19-15",
    )
    meta = await _lookup([auburn, texas_tech], "ncaa-basketball")

    assert meta["texas tech red raiders"]["team_id"] == 200

"""TYPING A COLLEGE TEAM'S NICKNAME REACHES THAT TEAM'S GAME. #9076.

Production `d0ae9c4a`, 2026-09-27 06:3xZ, `/api/events/typeahead`:

    noles    3 championship futures; no Florida State team or game
    horns    TCU Horned Frogs, a novel ("A Court Of Thorns and Roses"), 4 Thorns FC markets
    bama     5 Alabama POLITICS markets, then the Alabama game
    vols     one row: Volsungur (an Icelandic soccer club)
    huskers  3 championship futures, then the Nebraska game

`CURATED_TEAM_ALIASES` had never held a college nickname. The game rail, the
futures rail and the typeahead "nickname leads with the game" promotion (#4986)
all read that map at query time, so the whole fix is five rows — and the guards
below are what keeps those rows from being the #8685 fan-out mistake.

Measured before adding (the #8685 bar): each last-word token names exactly ONE
ncaaf club over 120 days of events, and no open football futures market carries
`Tide` or `Volunteers` in another club's name.
"""

from __future__ import annotations

import pytest

from app.config.team_aliases import (
    CURATED_TEAM_ALIASES,
    _alias_claim_counts,
    team_nickname_event_expansions,
    team_nickname_search_expansions,
)
from app.routes.events import (
    _nickname_names_participant,
    _team_nickname_event_admissions,
    _team_nickname_event_arms,
)

NCAAF = "americanfootball_ncaaf"

COLLEGE = {
    "noles": "Florida State Seminoles",
    "horns": "Texas Longhorns",
    "bama": "Alabama Crimson Tide",
    "vols": "Tennessee Volunteers",
    "huskers": "Nebraska Cornhuskers",
}


def _sql(arm) -> str:
    return str(arm.compile(compile_kwargs={"literal_binds": True}))


@pytest.mark.parametrize("alias,team", sorted(COLLEGE.items()))
def test_each_nickname_is_curated_for_its_school_in_ncaaf(alias, team) -> None:
    assert alias in CURATED_TEAM_ALIASES[(NCAAF, team)]


@pytest.mark.parametrize("alias", sorted(COLLEGE))
def test_each_nickname_has_exactly_one_claimant(alias) -> None:
    """🔴 Football only, and this is why.

    The same school exists under `basketball_ncaab` (Texas Longhorns 1073,
    Alabama Crimson Tide 672, ...). Adding the basketball row as well makes the
    alias CONTESTED, and `_alias_claim_counts` (#8084) then refuses it in BOTH
    derived maps — the five game arms this issue exists for would silently vanish
    while the config still reads as if they were there.
    """
    assert _alias_claim_counts()[alias] == 1


@pytest.mark.parametrize("alias,team", sorted(COLLEGE.items()))
def test_the_game_arm_is_the_schools_token_scoped_to_ncaaf(alias, team) -> None:
    token = team.split()[-1]
    assert team_nickname_event_expansions()[alias] == (token, NCAAF)

    arms = _team_nickname_event_arms([alias])
    assert len(arms) == 1, f"{alias} produced {len(arms)} arms"
    sql = _sql(arms[0])
    assert token.lower() in sql.lower()
    assert NCAAF in sql, f"{alias} built an arm not scoped to college football"


def test_only_bama_and_vols_get_a_futures_arm() -> None:
    """The other three are spelled inside their tokens (Semi*noles*, Long*horns*,
    Corn*huskers*), so the plain ILIKE futures arm already reaches them — the
    `9ers` rule. The game arm keeps all five because it word-matches."""
    s = team_nickname_search_expansions()
    assert s["bama"] == ("Tide", "football")
    assert s["vols"] == ("Volunteers", "football")
    for inside in ("noles", "horns", "huskers"):
        assert inside not in s


@pytest.mark.parametrize("alias,team", sorted(COLLEGE.items()))
def test_the_nickname_names_its_own_game_in_ncaaf(alias, team) -> None:
    """The typeahead admission/promotion test (#4847/#4986) admits the school's game."""
    admissions = _team_nickname_event_admissions([alias])
    assert _nickname_names_participant(admissions, NCAAF, [team, "Some Opponent"])


@pytest.mark.parametrize(
    "alias,wrong_sport,participants",
    [
        # The same school's BASKETBALL game is not admitted by the football alias
        # — the scope, not the name, decides.
        ("horns", "basketball_ncaab", ["Texas Longhorns", "Baylor Bears"]),
        ("bama", "basketball_ncaab", ["Alabama Crimson Tide", "Auburn Tigers"]),
        # The reader-visible wrong answers from the BEFORE read.
        ("horns", "soccer_usa_nwsl", ["Portland Thorns FC", "Boston Legacy FC"]),
        ("vols", "soccer_other", ["Volsungur", "KA Akureyri"]),
    ],
)
def test_the_nickname_does_not_name_another_sports_row(alias, wrong_sport, participants) -> None:
    admissions = _team_nickname_event_admissions([alias])
    assert not _nickname_names_participant(admissions, wrong_sport, participants)


def test_the_contested_college_nicknames_stay_out() -> None:
    """Refused on the same measurement: `canes` (Miami + Carolina Hurricanes),
    `dawgs` (Georgia, Washington, Mississippi State, UConn), `zags` (its last-word
    token would be `Bulldogs` — every Bulldogs club), `cuse` (token `Orange`
    reaches Orange Bowl markets in bowl season), `cards` (three Cardinals clubs)."""
    curated = {a.lower() for aliases in CURATED_TEAM_ALIASES.values() for a in aliases}
    for refused in ("canes", "dawgs", "zags", "cuse", "cards"):
        assert refused not in curated, refused

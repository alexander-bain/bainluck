"""#8142 — a shared mascot is not a shared school.

The bracket lookups used to accept "2+ shared words" as identity. Between two
college teams a shared word is usually a MASCOT, so the grid served one
school's tournament seed on another school's row: `Grambling St Tigers` wore
Tennessee State's Midwest 15 and `Norfolk St Spartans` wore Michigan State's 3
— a 3-seed, sitting at row 63 of the championship grid.

Measured over all 690 `basketball_ncaab`/`basketball_wncaab` names in `teams`,
the old arm answered 29 names and got 25 of them wrong. The four it got right
differ from their bracket key by an honorific alone, which is why the guard
below asserts BOTH directions: the wrong-school matches are refused AND the
honorific matches still resolve. A one-directional guard here would pass on an
implementation that simply deleted the arm, blanking four correct women's rows.
"""

import pytest

from app.routes.playoffs import _lookup_ncaa_bracket, _lookup_wncaa_bracket

# (input name, the bracket entry it used to steal) — every one of these is a
# DIFFERENT institution from the key it matched.
WRONG_SCHOOL_MEN = [
    ("Grambling St Tigers", "Tennessee State Tigers"),
    ("Jackson St Tigers", "Tennessee State Tigers"),
    ("East Tennessee St Buccaneers", "Tennessee State Tigers"),
    ("Norfolk St Spartans", "Michigan State Spartans"),
    ("San José St Spartans", "Michigan State Spartans"),
    ("South Dakota St Jackrabbits", "North Dakota State Bison"),
    ("North Dakota Fighting Hawks", "North Dakota State Bison"),
    ("Central Connecticut St Blue Devils", "Duke Blue Devils"),
    ("North Carolina A&T Aggies", "North Carolina Tar Heels"),
    ("North Carolina Central Eagles", "North Carolina Tar Heels"),
    ("New Mexico St Aggies", "Utah State Aggies"),
    ("East Texas A&M Lions", "Texas A&M Aggies"),
]

WRONG_SCHOOL_WOMEN = [
    ("Norfolk St Spartans", "Michigan State Spartans"),
    ("San José St Spartans", "Michigan State Spartans"),
    ("Central Connecticut St Blue Devils", "Duke Blue Devils"),
    ("North Carolina A&T Aggies", "North Carolina Tar Heels"),
    ("North Carolina Central Eagles", "North Carolina Tar Heels"),
    ("North Dakota St Bison", "South Dakota State Jackrabbits"),
    ("South Dakota Coyotes", "South Dakota State Jackrabbits"),
    ("San Diego St Aztecs", "UC San Diego Tritons"),
    ("San Diego Toreros", "UC San Diego Tritons"),
    ("Morgan St Bears", "Missouri State Lady Bears"),
    ("SE Missouri St Redhawks", "Missouri State Lady Bears"),
    # `South Carolina State` is not `South Carolina`: this one is refused by the
    # institution-marker veto, not by containment, because the shorter name IS
    # a subset of the longer one. Losing the veto puts a 1-seed on its row.
    ("South Carolina St Bulldogs", "South Carolina Gamecocks"),
    ("East Tennessee St Buccaneers", "Tennessee Lady Volunteers"),
]

# The honorific cases: one school, two spellings. These MUST keep resolving.
SAME_SCHOOL_WOMEN = [
    ("Georgia Bulldogs", "Region 4", 7),
    ("Tennessee Volunteers", "Region 3", 10),
    ("Missouri St Bears", "Region 3", 16),
    ("Texas Tech Red Raiders", "Region 2", 7),
]


@pytest.mark.parametrize("name,stolen_from", WRONG_SCHOOL_MEN)
def test_mens_bracket_refuses_a_different_school(name, stolen_from):
    got = _lookup_ncaa_bracket(name)
    from app.routes.playoffs import NCAA_2026_BRACKET

    stolen = NCAA_2026_BRACKET[stolen_from]
    assert got != stolen, (
        f"{name!r} was served {stolen_from!r}'s "
        f"{stolen['region']} {stolen['seed']} — a shared mascot is not a "
        f"shared school (#8142)"
    )


@pytest.mark.parametrize("name,stolen_from", WRONG_SCHOOL_WOMEN)
def test_womens_bracket_refuses_a_different_school(name, stolen_from):
    got = _lookup_wncaa_bracket(name)
    from app.routes.playoffs import WNCAA_2026_BRACKET

    stolen = WNCAA_2026_BRACKET[stolen_from]
    assert got != stolen, (
        f"{name!r} was served {stolen_from!r}'s "
        f"{stolen['region']} {stolen['seed']} — a shared mascot is not a "
        f"shared school (#8142)"
    )


@pytest.mark.parametrize("name,region,seed", SAME_SCHOOL_WOMEN)
def test_womens_bracket_still_resolves_across_an_honorific(name, region, seed):
    """`Georgia Bulldogs` and `Georgia Lady Bulldogs` are one school.

    This is the half that stops the fix from being "delete the fuzzy arm".
    """
    got = _lookup_wncaa_bracket(name)
    assert got is not None, f"{name!r} lost its seed to the #8142 tightening"
    assert (got["region"], got["seed"]) == (region, seed)


def test_exact_and_alias_keys_are_untouched():
    """The tightening is subtractive only — it may not move a real answer."""
    assert _lookup_ncaa_bracket("Duke Blue Devils") == {
        "region": "East", "seed": 1
    }
    assert _lookup_ncaa_bracket("NC State Wolfpack") == {
        "region": "West", "seed": 11
    }
    # abbreviation expansion still runs: `St` → `State`
    assert _lookup_wncaa_bracket("Iowa St Cyclones") == {
        "region": "Region 1", "seed": 8
    }


def test_the_two_grambling_and_tennessee_rows_no_longer_share_a_seed():
    """The reader-visible symptom: two schools on one seed line.

    A region may legitimately hold two teams on the 11 and 16 lines (the First
    Four), so this asserts the specific collision #8142 reported rather than
    seed uniqueness in general.
    """
    grambling = _lookup_ncaa_bracket("Grambling St Tigers")
    tennessee_state = _lookup_ncaa_bracket("Tennessee St Tigers")
    assert tennessee_state == {"region": "Midwest", "seed": 15}
    assert grambling != tennessee_state
    assert grambling is None

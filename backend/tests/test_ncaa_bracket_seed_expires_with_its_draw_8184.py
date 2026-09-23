"""#8184 — a 2027 grid stops printing the seeds of the 2026 draw.

Measured on production 2026-09-23 07:27Z, `/playoffs/ncaa-basketball` is titled
**"NCAA Tournament 2027"** and 64 of its 68 rows print a small grey seed beside
the crest: Florida 1, Duke 1, Illinois 3, UConn 2, Texas 11. The women's grid is
titled "Women's NCAA Tournament 2027" and prints a seed on all 30. Every one of
those numbers comes from a bracket drawn on Selection Sunday **2026**. The 2027
bracket does not exist and will not until March 2027.

The region that would tell the four "#1" seeds apart is served in the payload and
never rendered by the grid, so the reader is shown four number-ones on one page
with nothing to distinguish them.

WHY THE SEED CANNOT SURVIVE ITS DRAW BUT THE FIELD CAN. The same dictionary is
put to two uses and only one is a claim to the reader. `seed`/`region` assert a
fact about a draw. `_in_bracket` decides which teams are listed, which is a
heuristic that survives the season turning over — last March's 68 is a far better
field than all 239 Division I teams carrying a championship price (market id 3
has 239 outcomes). So the gate is on the metadata only, and
`test_the_field_filter_is_deliberately_left_alone` pins that split so a later
tidy-up cannot quietly turn the grid into 239 rows or into none.

WHY THE GATE IS AT THE CALL SITES AND NOT INSIDE THE LOOKUPS. `_lookup_ncaa_bracket`
and `_lookup_wncaa_bracket` are name matchers, and #8142's guards test them as
such. Gating inside them would have made every one of those guards vacuous. They
still resolve names here; two call sites decide whether to ask.

EVERY SERVED SEED IS BRACKET-DERIVED, WHICH IS WHY THE EXPECTATION IS `None` AND
NOT "SMALLER". The other writer is `meta["seed"] = standings.get("position")` at
playoffs.py:2252, and `teams.standings_data` is NULL on all 366 `basketball_ncaab`
and all 324 `basketball_wncaab` rows (`n_position` 0, `n_seed` 0, measured
2026-09-23). Nothing else can put a number there.
"""

import inspect

import pytest

from app.routes.playoffs import (
    NCAA_BRACKET_SEASON,
    WNCAA_BRACKET_SEASON,
    _bracket_metadata_applies,
    _get_team_metadata,
    _lookup_ncaa_bracket,
    _lookup_wncaa_bracket,
    get_playoff_grid,
)
from app.config.league_configs import get_league_config

NCAAB = "ncaa-basketball"
WNCAAB = "ncaa-women-basketball"


class _FakeSport:
    def __init__(self, key):
        self.key = key


class _FakeTeam:
    """Only the attributes `_get_team_metadata` reads."""

    def __init__(self, team_id, name, sport_key):
        self.id = team_id
        self.name = name
        self.sport = _FakeSport(sport_key)
        self.espn_id = None
        self.abbreviation = None
        self.alternate_names = []
        self.current_record = "35-3"
        self.logo_url_small = "https://a.espncdn.com/i/teamlogos/ncaa/500/150.png"
        self.logo_url_large = None
        self.primary_color = "#001a57"
        self.secondary_color = None
        # The production reality: NULL for every NCAA basketball row, so the
        # bracket is the only thing that can supply a seed.
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


async def _meta_for(name, sport_key, league_slug):
    """Drive the real metadata path and return the one row's metadata."""
    meta = await _get_team_metadata(
        _FakeSession([_FakeTeam(1, name, sport_key)]),
        {"probe"},
        league_slug=league_slug,
    )
    matching = [v for v in meta.values() if v.get("name") == name]
    assert matching, f"{name!r} never reached the metadata map: {sorted(meta)}"
    return matching[0]


# --- The ship ---------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,sport_key,league_slug",
    [
        ("Duke Blue Devils", "basketball_ncaab", NCAAB),
        ("UConn Huskies", "basketball_wncaab", WNCAAB),
    ],
)
async def test_a_2027_grid_serves_no_seed_and_no_region_from_the_2026_draw(
    name, sport_key, league_slug
):
    """The reader stops being told Duke is a 1 seed in a bracket nobody has drawn."""
    served = await _meta_for(name, sport_key, league_slug)

    assert served["seed"] is None, (
        f"{name} is still printing seed {served['seed']!r} on a "
        f"{get_league_config(league_slug).season_pattern} grid"
    )
    # `.get` deliberately: unlike `seed`, `region` is never initialised in the
    # metadata dict — the bracket branch is the only thing that creates the key
    # at all, which is why every consumer downstream reads it with `.get`.
    assert served.get("region") is None, (
        f"{name} is still carrying region {served.get('region')!r} from the 2026 draw"
    )


# --- The control that stops all of the above passing for the wrong reason ----


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name,sport_key,league_slug,constant,region,seed",
    [
        ("Duke Blue Devils", "basketball_ncaab", NCAAB, "NCAA_BRACKET_SEASON", "East", 1),
        (
            "UConn Huskies",
            "basketball_wncaab",
            WNCAAB,
            "WNCAA_BRACKET_SEASON",
            "Region 1",
            1,
        ),
    ],
)
async def test_the_same_call_still_serves_the_seed_in_the_brackets_own_season(
    monkeypatch, name, sport_key, league_slug, constant, region, seed
):
    """Point the bracket at the season the grid is on and the number comes back.

    Without this arm the test above passes just as happily if the name stopped
    matching, if the fake row stopped reaching the map, or if `seed` were deleted
    from the payload outright. It is the only thing proving the gate is a gate
    and not a deletion — and it exercises the opposite branch of the exact
    condition the change added.
    """
    monkeypatch.setattr(
        "app.routes.playoffs." + constant,
        get_league_config(league_slug).season_pattern,
    )

    served = await _meta_for(name, sport_key, league_slug)

    assert served["region"] == region
    assert served["seed"] == seed


# --- The gate is at the call sites, so #8142's matchers are still live -------


def test_the_bracket_lookups_themselves_are_untouched():
    """Both helpers still resolve names — #8142's guards are testing real code.

    If the gate had been put inside the lookups, every assertion in
    `test_playoff_bracket_shared_mascot_is_not_identity_8142.py` would pass
    against a function that returns `None` unconditionally, and the
    wrong-school veto it guards would be unprotected.
    """
    assert _lookup_ncaa_bracket("Duke Blue Devils") == {"region": "East", "seed": 1}
    assert _lookup_wncaa_bracket("UConn Huskies") == {"region": "Region 1", "seed": 1}


# --- The predicate's own edges ----------------------------------------------


def test_the_gate_reads_the_season_and_refuses_an_absent_config():
    assert _bracket_metadata_applies(get_league_config(NCAAB), "2027") is True
    assert _bracket_metadata_applies(get_league_config(NCAAB), "2026") is False
    assert _bracket_metadata_applies(None, "2026") is False


def test_both_brackets_still_describe_the_2026_draw():
    """The constants are the thing to bump when the 2027 field is announced.

    Stated as an assertion so that bumping one and forgetting the other — which
    would revive the defect on exactly one of the two grids — fails here rather
    than on the page.
    """
    assert NCAA_BRACKET_SEASON == "2026"
    assert WNCAA_BRACKET_SEASON == "2026"
    assert get_league_config(NCAAB).season_pattern == "2027"
    assert get_league_config(WNCAAB).season_pattern == "2027"


# --- The two things this change deliberately does NOT do ---------------------


def test_the_grid_fallback_site_is_gated_too():
    """`get_playoff_grid` re-derives region/seed when the metadata map had none.

    That fallback fires precisely when `region` is falsy — which, after this
    change, is every NCAA row. So it is the one site that would put the 2026
    seed straight back on the page, and an ungated branch there makes the whole
    fix invisible. Asserted structurally because the branch lives inside a route
    that needs a database to drive.
    """
    source = inspect.getsource(get_playoff_grid)

    for lookup in ("_lookup_ncaa_bracket", "_lookup_wncaa_bracket"):
        assert lookup in source, f"{lookup} is no longer called here — retarget this guard"

    assert source.count("_bracket_metadata_applies") == 2, (
        "the two NCAA fallback branches in get_playoff_grid must both be gated"
    )


def test_the_field_filter_is_deliberately_left_alone():
    """Which teams are LISTED is a heuristic and survives the season turning over.

    The grid serves 68 men's rows because `_in_bracket` filters the championship
    market's 239 outcomes down to last March's field. That is not a claim to the
    reader, and ungating it would put 239 rows on the page. Pinned so a later
    tidy-up that "finishes the job" has to argue with a test first.
    """
    source = inspect.getsource(get_playoff_grid)

    filter_block = source.split("filter to bracket teams only")[-1]
    assert "NCAA_2026_BRACKET" in filter_block
    assert "WNCAA_2026_BRACKET" in filter_block
    assert "_bracket_metadata_applies" not in filter_block, (
        "the field filter was gated on the season — that turns 68 rows into 239"
    )

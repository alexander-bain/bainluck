"""Guards for #4978 — a club in two competitions keeps its crest.

#4862 measured 35 of 49 served game cards with no crest on at least one side.
It split three ways with no residue, and this is the second part: **20 of 36
crest-less sides had more than one ESPN-enriched row, every row carrying the
SAME logo**, and the cross-league ambiguity guard dropped them for a collision
that has no wrong answer.

`_dedupe_team_name_lookup` drops any name key whose enriched rows sit in more
than one league, so it attaches no crest rather than a wrong one. #4945 fixed
the case where the two "leagues" are a *season variant* of one league
(`baseball_mlb` / `baseball_mlb_preseason`). **A club entered in its domestic
league AND a continental cup has the same shape but genuinely IS in two
leagues**, so the identity collapse cannot reach it:

    AS Roma   soccer_italy_serie_a       colour+logo
    AS Roma   soccer_uefa_champs_league  colour+logo   -> 2 identities -> DROPPED

The contrast measured on 2026-09-10 is exact: the only two UCL sides that DID
render (Fenerbahce, Slavia Praha) are precisely the two with a *single* enriched
row. Over all 1,014 enriched names, 350 sit in >1 league — 115 where every row
carries the same logo, 235 with genuinely different logos. So **85 names beyond
#4945's 30** lose a crest for nothing, and they are Arsenal, Liverpool,
Barcelona, Real Madrid, Bayern Munich, Paris Saint-Germain, Manchester City.

**The discriminator is logo AGREEMENT, not league identity.**

Two halves are guarded here, and the second is the one #4945 paid for:

1. Where the crest agrees, the key survives; where it differs, it still drops.
2. Once the key survives, something must PICK a row, and an unordered query
   yields them arbitrarily. Every retention test below therefore asserts **both
   insertion orders** — a one-order test passes on first-write-wins and proves
   nothing.
"""

from dataclasses import dataclass, field
from itertools import permutations

import pytest

from app.routes.events import (
    _crest_is_shared,
    _crest_row_preference,
    _dedupe_team_name_lookup,
)

ROMA_CREST = "https://a.espncdn.com/i/teamlogos/soccer/500/104.png"
OTHER_CREST = "https://a.espncdn.com/i/teamlogos/nhl/500/fla.png"


@dataclass
class _Row:
    """A `TeamSnapshot`-shaped row: attribute surface only, no ORM."""

    id: int
    name: str
    sport_id: int
    sport_key: str | None = None
    alternate_names: list = field(default_factory=list)
    logo_url_small: str | None = None
    primary_color: str | None = None
    current_record: str | None = None
    standings_data: dict | None = None


def _roma(row_id, sport_key, sport_id, **kw):
    return _Row(
        row_id,
        "AS Roma",
        sport_id=sport_id,
        sport_key=sport_key,
        logo_url_small=ROMA_CREST,
        primary_color="8E1F2F",
        **kw,
    )


def _both_orders(rows):
    """Every arrival order of `rows`, as separate lookups."""
    return [_dedupe_team_name_lookup(list(order)) for order in permutations(rows)]


# --- The reported defect ------------------------------------------------


def test_a_club_in_its_league_and_a_continental_cup_keeps_its_crest():
    """AS Roma, verbatim from the issue — Serie A + UCL, one crest."""
    rows = [
        _roma(1, "soccer_italy_serie_a", 900),
        _roma(2, "soccer_uefa_champs_league", 901),
    ]
    for lookup in _both_orders(rows):
        assert "AS Roma" in lookup, "the crest-less UCL row is the whole defect"
        assert lookup["AS Roma"].logo_url_small == ROMA_CREST


@pytest.mark.parametrize(
    "name,domestic,sport_id",
    [
        ("AS Roma", "soccer_italy_serie_a", 900),
        ("Como", "soccer_italy_serie_a", 900),
        ("RB Leipzig", "soccer_germany_bundesliga", 902),
        ("RC Lens", "soccer_france_ligue_one", 903),
    ],
)
def test_the_four_named_specimens_all_keep_their_crest(name, domestic, sport_id):
    """The four clubs #4978 is scoped to, each in both arrival orders."""
    crest = f"https://a.espncdn.com/i/teamlogos/soccer/500/{sport_id}.png"
    rows = [
        _Row(1, name, sport_id=sport_id, sport_key=domestic, logo_url_small=crest),
        _Row(
            2,
            name,
            sport_id=901,
            sport_key="soccer_uefa_champs_league",
            logo_url_small=crest,
        ),
    ]
    for lookup in _both_orders(rows):
        assert lookup.get(name) is not None, f"{name} lost its crest"
        assert lookup[name].logo_url_small == crest


# --- What must still drop ------------------------------------------------


def test_a_genuine_cross_league_collision_still_drops():
    """Carolina Panthers / Florida Panthers — different crests, no safe answer.

    This is Queue #238 and it is the reason the guard exists. It must survive
    #4978 intact, in both orders.
    """
    rows = [
        _Row(
            1,
            "Carolina Panthers",
            sport_id=1,
            sport_key="americanfootball_nfl",
            alternate_names=["Panthers"],
            logo_url_small=OTHER_CREST + "?car",
        ),
        _Row(
            2,
            "Florida Panthers",
            sport_id=4,
            sport_key="icehockey_nhl",
            alternate_names=["Panthers"],
            logo_url_small=OTHER_CREST,
        ),
    ]
    for lookup in _both_orders(rows):
        assert "Panthers" not in lookup, "a wrong crest is worse than none"
        assert lookup["Carolina Panthers"].id == 1
        assert lookup["Florida Panthers"].id == 2


def test_two_rows_agreeing_only_on_having_NO_logo_still_drop():
    """Absence is not agreement.

    Two rows with no logo agree about nothing — they can still disagree on
    `primary_color`, which is the other thing the card paints. Retaining them
    would widen the fix past the 115 same-logo names it was measured for, and
    would quietly reintroduce the wrong-COLOUR half of Queue #238.
    """
    rows = [
        _Row(
            1,
            "Saints",
            sport_id=1,
            sport_key="americanfootball_nfl",
            primary_color="AAAAAA",
        ),
        _Row(
            2,
            "Saints",
            sport_id=3,
            sport_key="basketball_ncaab",
            primary_color="BBBBBB",
        ),
    ]
    for lookup in _both_orders(rows):
        assert "Saints" not in lookup


def test_one_row_with_a_logo_and_one_without_still_drops():
    """Conservative on purpose: the measured population is rows that AGREE."""
    rows = [
        _Row(
            1,
            "Rangers",
            sport_id=4,
            sport_key="icehockey_nhl",
            logo_url_small=OTHER_CREST,
        ),
        _Row(2, "Rangers", sport_id=7, sport_key="soccer_scotland_premiership"),
    ]
    for lookup in _both_orders(rows):
        assert "Rangers" not in lookup


def test_a_third_league_with_a_different_crest_drops_the_whole_key():
    """Agreement must hold across ALL rows, not just the first pair seen."""
    rows = [
        _roma(1, "soccer_italy_serie_a", 900),
        _roma(2, "soccer_uefa_champs_league", 901),
        _Row(
            3,
            "AS Roma",
            sport_id=999,
            sport_key="basketball_italy_lega",
            logo_url_small=OTHER_CREST,
        ),
    ]
    for lookup in _both_orders(rows):
        assert "AS Roma" not in lookup, (
            "one disagreeing row makes the name ambiguous again, whichever "
            "order it arrives in"
        )


# --- The half #4945 paid for: WHICH row, deterministically ---------------


def test_the_richer_row_wins_in_both_orders_standings():
    """`_format_team_data` ships `standings_data` beside the crest.

    Same crest, so the reader's badge is right either way — but only one row
    carries the standings the card prints. Without a deterministic preference
    the standings coin-flip on query order, which is exactly the #4945 defect
    one layer out.
    """
    rich = _roma(1, "soccer_italy_serie_a", 900, standings_data={"rank": 4})
    thin = _roma(2, "soccer_uefa_champs_league", 901)
    for lookup in _both_orders([rich, thin]):
        assert lookup["AS Roma"].id == 1
        assert lookup["AS Roma"].standings_data == {"rank": 4}


def test_the_richer_row_wins_in_both_orders_current_record():
    rich = _roma(1, "soccer_italy_serie_a", 900, current_record="3-1-0")
    thin = _roma(2, "soccer_uefa_champs_league", 901)
    for lookup in _both_orders([rich, thin]):
        assert lookup["AS Roma"].current_record == "3-1-0"


def test_rows_disagreeing_on_colour_resolve_to_the_SAME_row_either_way():
    """Same crest, different `primary_color` — Syracuse Orange, Cornell Big Red.

    There is no principled winner between two colours, so the requirement is
    not which one wins but that it is always the SAME one. A guard that only
    asserted "a colour is present" would pass on a coin flip.
    """
    a = _Row(
        1,
        "Syracuse Orange",
        sport_id=760,
        sport_key="americanfootball_ncaaf",
        logo_url_small=ROMA_CREST,
        primary_color="F76900",
    )
    b = _Row(
        2,
        "Syracuse Orange",
        sport_id=3,
        sport_key="basketball_ncaab",
        logo_url_small=ROMA_CREST,
        primary_color="000E54",
    )
    winners = {lookup["Syracuse Orange"].id for lookup in _both_orders([a, b])}
    assert len(winners) == 1, f"order-dependent winner: {winners}"


def test_the_preference_is_a_TOTAL_order_over_distinct_rows():
    """Non-vacuity for every both-orders test above.

    A preference that TIES leaves the winner decided by arrival order on
    precisely the rows it failed to separate, and every test above would then
    be passing on first-write-wins rather than on the rule.
    """
    rows = [
        _roma(1, "soccer_italy_serie_a", 900),
        _roma(2, "soccer_uefa_champs_league", 901),
        _roma(3, "soccer_italy_serie_a", 900, standings_data={"rank": 1}),
        _roma(4, "soccer_uefa_europa_league", 904, current_record="1-0-0"),
    ]
    ranks = [_crest_row_preference(r) for r in rows]
    assert len(set(ranks)) == len(ranks), f"preference ties: {ranks}"


def test_the_preference_stays_total_when_two_rows_SHARE_a_sport_key():
    """The final `id` term, which the test above cannot reach.

    Inside the cross-league branch two rows always differ on `sport_key`,
    because a differing league identity is derived from it — so `sport_key`
    alone looks sufficient and the `id` term looks like dead weight.
    `_crest_row_preference` is a standalone helper, though, and a ranking that
    ties for two equally-rich rows of one league is a coin flip left lying
    around for the next caller.
    """
    a = _roma(1, "soccer_italy_serie_a", 900)
    b = _roma(2, "soccer_italy_serie_a", 900)
    assert _crest_row_preference(a) != _crest_row_preference(b)


# --- The discriminator itself -------------------------------------------


def test_crest_is_shared_requires_a_present_and_equal_logo():
    same_a = _Row(1, "x", sport_id=1, logo_url_small=ROMA_CREST)
    same_b = _Row(2, "x", sport_id=2, logo_url_small=ROMA_CREST)
    diff = _Row(3, "x", sport_id=3, logo_url_small=OTHER_CREST)
    none_a = _Row(4, "x", sport_id=4)
    none_b = _Row(5, "x", sport_id=5)

    assert _crest_is_shared(same_a, same_b) is True
    assert _crest_is_shared(same_a, diff) is False
    assert _crest_is_shared(same_a, none_a) is False
    assert _crest_is_shared(none_a, same_a) is False
    assert _crest_is_shared(none_a, none_b) is False, "absence is not agreement"


def test_an_empty_string_logo_is_not_a_crest():
    """`bool(logo)` is doing real work — two rows with '' must not agree."""
    a = _Row(1, "x", sport_id=1, logo_url_small="")
    b = _Row(2, "x", sport_id=2, logo_url_small="")
    assert _crest_is_shared(a, b) is False


# --- #4945 must be untouched --------------------------------------------


def test_the_mlb_season_variant_collapse_still_works_without_any_logo():
    """#4945's subject reaches its own branch, not #4978's.

    The preseason rows in that defect are matched by league identity BEFORE the
    crest question is asked, so this must pass with no logos set at all —
    otherwise #4978 has quietly become load-bearing for #4945.
    """
    parent = _Row(
        1,
        "Boston Red Sox",
        sport_id=53232,
        sport_key="baseball_mlb",
        standings_data={"rank": 1},
    )
    variant = _Row(
        2, "Boston Red Sox", sport_id=33178, sport_key="baseball_mlb_preseason"
    )
    for lookup in _both_orders([parent, variant]):
        assert lookup["Boston Red Sox"].id == 1, "the parent-league row must win"
        assert lookup["Boston Red Sox"].standings_data == {"rank": 1}

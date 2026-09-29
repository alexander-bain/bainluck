"""#9309 — searching `bucs` stops listing East Tennessee State under two spellings.

Production 2026-09-28 06:13Z, `/search?q=bucs` at 390px: the TEAMS card read
Tampa Bay Buccaneers, Charleston Southern Buccaneers, **East Tennessee St
Buccaneers** (baseball), **East Tennessee State Buccaneers** (football) — same
logo, two spellings, so a reader saw one school listed twice.

They are two real rows for two sports (3607 baseball_ncaa, 18615 FCS
football); only the display name is wrong. `_unify_school_st_spelling`, read
by `/api/events/search` on the carded rows, rewrites a middle `St` to `State`
only when that `State` spelling is evidenced — a sibling row on the card, or
the row's own aliases. The window is production's 25-row Teams window for
`bucs`, shared with #9281's test so the two cannot drift.
"""

import inspect

from app.routes import events as ev
from tests.test_search_team_card_stem_only_rows_9281 import BUCS_WINDOW, BULL_WINDOW, _rows


def _card(window, query):
    return [c for _k, c in ev._team_card_keyed(_rows(window), query)]


def _served(window, query):
    return [(c["name"], c["sport_key"]) for c in ev._unify_school_st_spelling(_card(window, query))]


def test_bucs_card_spells_east_tennessee_state_once():
    assert _served(BUCS_WINDOW, "bucs") == [
        ("Tampa Bay Buccaneers", "americanfootball_nfl"),
        ("Charleston Southern Buccaneers", "americanfootball_ncaaf"),
        ("East Tennessee State Buccaneers", "baseball_ncaa"),
        ("East Tennessee State Buccaneers", "americanfootball_ncaaf_fcs"),
    ]


def test_strawman_the_card_before_the_rewrite_is_production():
    """The fixture IS the defect: un-rewritten, the card is what production served."""
    assert [(c["name"], c["sport_key"]) for c in _card(BUCS_WINDOW, "bucs")] == [
        ("Tampa Bay Buccaneers", "americanfootball_nfl"),
        ("Charleston Southern Buccaneers", "americanfootball_ncaaf"),
        ("East Tennessee St Buccaneers", "baseball_ncaa"),
        ("East Tennessee State Buccaneers", "americanfootball_ncaaf_fcs"),
    ]


def test_ids_slugs_and_order_are_untouched():
    before = [(c["id"], c["slug"], c["sport_key"]) for c in _card(BUCS_WINDOW, "bucs")]
    after = [(c["id"], c["slug"], c["sport_key"]) for c in ev._unify_school_st_spelling(_card(BUCS_WINDOW, "bucs"))]
    assert after == before


def test_sibling_alone_is_evidence():
    cards = [{"name": "Tennessee St Tigers"}, {"name": "Tennessee State Tigers"}]
    assert [c["name"] for c in ev._unify_school_st_spelling(cards)] == [
        "Tennessee State Tigers", "Tennessee State Tigers",
    ]


def test_own_alias_alone_is_evidence():
    cards = [{"name": "Fresno St Bulldogs", "_aliases": ["Fresno St", "Fresno State Bulldogs", "Bulldogs"]}]
    assert ev._unify_school_st_spelling(cards)[0]["name"] == "Fresno State Bulldogs"


def test_saint_never_becomes_state():
    """No evidence, no rewrite: a middle or leading St that means Saint stays."""
    cards = [
        {"name": "Mount St Mary's Mountaineers", "_aliases": ["Mount St. Mary's"]},
        {"name": "St Johns Red Storm", "_aliases": []},
        {"name": "St. Louis Cardinals", "_aliases": ["St.Louis Cardinals"]},
        {"name": "Mount St. Mary's", "_aliases": None},
    ]
    assert [c["name"] for c in ev._unify_school_st_spelling(cards)] == [
        "Mount St Mary's Mountaineers", "St Johns Red Storm", "St. Louis Cardinals", "Mount St. Mary's",
    ]


def test_near_miss_alias_does_not_rewrite():
    """`South Carolina St Bulldogs` aliases `...State Lady Bulldogs` — not the same
    name, so no rewrite (the rule wants the exact spelling, never a guess)."""
    cards = [{"name": "South Carolina St Bulldogs", "_aliases": ["SC State", "South Carolina State Lady Bulldogs"]}]
    assert ev._unify_school_st_spelling(cards)[0]["name"] == "South Carolina St Bulldogs"


def test_bulldogs_card_spells_each_state_school_by_its_own_alias():
    """The same window's rows through `bulldogs`: Fresno St and Mississippi St
    carry their `State` spelling as an alias, so the card reads it; the three
    other schools have no `St` and are untouched."""
    assert [c["name"] for c in ev._unify_school_st_spelling(_card(BULL_WINDOW, "bulldogs"))] == [
        "Alabama A&M Bulldogs", "Butler Bulldogs", "Citadel Bulldogs",
        "Fresno State Bulldogs", "Mississippi State Bulldogs",
    ]


def test_search_route_applies_it_to_the_card_before_aliases_are_popped():
    src = inspect.getsource(ev.search_events)
    call = src.index("_unify_school_st_spelling(")
    carded = src.index("_team_card_keyed(_team_result_rows")
    popped = src.index('_t.pop("_aliases", None)')
    assert call < carded < popped
    assert src[call:carded].count(")") == 0  # the card is the call's argument
    assert '"teams": matched_teams' in src

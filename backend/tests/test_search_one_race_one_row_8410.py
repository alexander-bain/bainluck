"""#8410 — search must not print one election race two or three times.

`bainluck.com/search?q=senate` (390px, 2026-09-24 ~17:00Z) printed the Maine race
as `Maine Senate winner` (Kalshi party series, 74%), `Maine Senate winner? (Person)`
(Kalshi person series, 65%) and `Maine Senate Election Winner` (Polymarket). The
fixtures are those production rows, verbatim (id, source, name, market_tier).
"""

from __future__ import annotations

import pytest

from app.routes import events as events_route


class _Market:
    def __init__(self, id, source, name, market_tier):
        self.id = id
        self.source = source
        self.name = name
        self.market_tier = market_tier
        self.canonical_market_key = None


ME_PARTY = _Market(109082, "kalshi", "Maine Senate winner?", 1)
ME_PERSON = _Market(52794903, "kalshi", "Maine Senate winner? (Person)", 1)
ME_POLY = _Market(113095, "polymarket", "Maine Senate Election Winner", 1)
MI_PARTY = _Market(109081, "kalshi", "Michigan Senate winner?", 1)
MI_PERSON = _Market(16756946, "kalshi", "Michigan Senate winner? (Person)", 1)
TX_KALSHI = _Market(109065, "kalshi", "Texas Senate winner?", 1)
TX_POLY = _Market(113109, "polymarket", "Texas Senate Election Winner", 1)
CA17_POLY = _Market(114099, "polymarket", "CA-17 House Election Winner", 1)
CA17_KALSHI = _Market(109031, "kalshi", "CA-17 House winner?", 1)
# #8378's control: one venue, two fiscal years, one title — must stay two rows.
URBN_FY26 = _Market(55686514, "kalshi", "Urban Outfitters Total Stores in Q1", 5)
URBN_FY27 = _Market(60473124, "kalshi", "Urban Outfitters total stores in Q1", 2)


def _page(rows):
    """Run rows through the route's own per-row decision, in order."""
    seen: set = set()
    kept: dict = {}
    return [m.id for m in rows if events_route._admit_search_future(m, seen, kept, [])]


def test_the_specimen_maine_prints_once():
    # Precondition: the #8378 question key really does split all three —
    # otherwise this passes on the old rule and proves nothing.
    keys = {events_route._futures_dedup_question_key(m) for m in (ME_PARTY, ME_PERSON, ME_POLY)}
    assert len(keys) == 3
    assert _page([ME_PARTY, ME_PERSON, ME_POLY]) == [ME_PARTY.id]


@pytest.mark.parametrize(
    "first, second",
    [(TX_KALSHI, TX_POLY), (CA17_POLY, CA17_KALSHI), (ME_POLY, ME_PARTY)],
    ids=["texas-senate", "ca17-house-poly-first", "maine-poly-first"],
)
def test_polymarkets_election_winner_is_kalshis_winner(first, second):
    assert _page([first, second]) == [first.id]


@pytest.mark.parametrize(
    "first, second",
    [(MI_PARTY, MI_PERSON), (MI_PERSON, MI_PARTY), (ME_PERSON, ME_PARTY)],
    ids=["party-first", "person-first", "maine-person-first"],
)
def test_kalshis_person_series_is_the_same_race_within_one_venue(first, second):
    assert _page([first, second]) == [first.id]


def test_a_person_row_then_the_other_venue_is_still_one_row():
    assert _page([ME_PERSON, ME_POLY]) == [ME_PERSON.id]


def test_different_races_are_untouched():
    rows = [ME_PARTY, MI_PARTY, TX_KALSHI, CA17_KALSHI]
    assert _page(rows) == [m.id for m in rows]


def test_the_election_fold_is_still_cross_venue_only():
    """Two bare titles from ONE venue that fold together stay two rows — the
    Election fold widens the key, never the venue rule."""
    a = _Market(1, "polymarket", "Maine Senate Election Winner", 1)
    b = _Market(2, "polymarket", "Maine Senate winner", 2)
    assert _page([a, b]) == [1, 2]


def test_the_fiscal_year_control_still_stays_two_rows():
    assert _page([URBN_FY26, URBN_FY27]) == [URBN_FY26.id, URBN_FY27.id]


def test_person_means_the_trailing_parenthetical_only():
    ptoy = _Market(3, "kalshi", "Time Person of the Year", 2)
    key, person = events_route._search_question_identity(ptoy)
    assert person is False and key.endswith("person of the year")


def test_the_shared_tiered_key_is_unchanged():
    """`league_futures` reads the tiered key; #8410 must not move it."""
    assert events_route._normalize_futures_dedup_key(ME_PERSON) == (
        "name:maine senate champion person:1"
    )
    assert events_route._normalize_futures_dedup_key(ME_POLY) == (
        "name:maine senate election champion:1"
    )

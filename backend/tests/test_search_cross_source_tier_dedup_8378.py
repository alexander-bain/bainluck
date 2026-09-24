"""#8378 — search must not print one question twice because two venues disagree on its tier.

`bainluck.com/search?q=bills` (390px, 2026-09-24 ~08:05Z) printed
`Which bills will become law in 2026?  Housing for the 21st…  100%` twice in the
ANSWERS card: Kalshi 109423 (`market_tier` 2) and Polymarket 1212562 (tier 5).
The tiered dedup key `name:<folded>:<tier>` kept them apart.

Every open market was read on production the same day for folded-name pairs whose
tiers disagree: FOUR. The fixtures below are those four pairs, verbatim — three
cross-venue copies of one question that must merge, and one same-venue pair (two
Kalshi fiscal years under one title) that must NOT.
"""

from __future__ import annotations

import inspect

import pytest

from app.routes import events as events_route


class _Market:
    def __init__(self, id, source, name, market_tier):
        self.id = id
        self.source = source
        self.name = name
        self.market_tier = market_tier
        self.canonical_market_key = None


# The production rows (id, source, name, market_tier), read 2026-09-24.
BILLS_KALSHI = _Market(109423, "kalshi", "Which bills will become law in 2026?", 2)
BILLS_POLY = _Market(1212562, "polymarket", "Which bills will become law in 2026?", 5)
FEDEX_KALSHI = _Market(61461681, "kalshi", "FedEx Open de France Winner", 1)
FEDEX_DG = _Market(61720782, "datagolf", "FedEx Open de France - Winner", None)
WS_ODDS = _Market(1, "odds_api", "MLB World Series Winner", 5)
WS_POLY = _Market(114584, "polymarket", "MLB World Series Champion 2026", 1)
URBN_FY26 = _Market(55686514, "kalshi", "Urban Outfitters Total Stores in Q1", 5)
URBN_FY27 = _Market(60473124, "kalshi", "Urban Outfitters total stores in Q1", 2)


def _page(rows):
    """Run rows through the route's own per-row decision, in order."""
    seen: set = set()
    kept_sources: dict = {}
    return [m.id for m in rows if events_route._admit_search_future(m, seen, kept_sources)]


# --- the specimen, and the other two cross-venue pairs -------------------------


@pytest.mark.parametrize(
    "first, second",
    [(BILLS_KALSHI, BILLS_POLY), (FEDEX_KALSHI, FEDEX_DG), (WS_POLY, WS_ODDS)],
    ids=["bills", "fedex", "world-series"],
)
def test_a_second_venues_copy_of_a_question_is_dropped(first, second):
    # Precondition: the tiered key really does split them — otherwise this test
    # would pass on the old rule and prove nothing.
    assert events_route._normalize_futures_dedup_key(
        first
    ) != events_route._normalize_futures_dedup_key(second)
    assert _page([first, second]) == [first.id]


def test_the_ranked_leader_is_the_one_kept():
    assert _page([BILLS_POLY, BILLS_KALSHI]) == [BILLS_POLY.id]


# --- the control: a same-venue pair stays two rows ----------------------------


def test_two_fiscal_years_from_one_venue_stay_two_rows():
    assert events_route._futures_dedup_question_key(
        URBN_FY26
    ) == events_route._futures_dedup_question_key(URBN_FY27)
    assert _page([URBN_FY26, URBN_FY27]) == [URBN_FY26.id, URBN_FY27.id]


def test_a_third_venue_is_still_dropped_after_a_same_venue_pair():
    urbn_poly = _Market(9, "polymarket", "Urban Outfitters Total Stores in Q1?", 3)
    assert _page([URBN_FY26, URBN_FY27, urbn_poly]) == [URBN_FY26.id, URBN_FY27.id]


def test_different_questions_are_untouched():
    rows = [BILLS_KALSHI, FEDEX_KALSHI, WS_POLY, URBN_FY26]
    assert _page(rows) == [m.id for m in rows]


def test_same_tier_duplicates_still_merge_as_before():
    same_tier = _Market(2, "polymarket", "Which bills will become law in 2026", 2)
    assert _page([BILLS_KALSHI, same_tier]) == [BILLS_KALSHI.id]


# --- the shared key is byte-identical (league_futures depends on the tier) ----


@pytest.mark.parametrize(
    "m",
    [BILLS_KALSHI, BILLS_POLY, FEDEX_KALSHI, FEDEX_DG, WS_ODDS, WS_POLY, URBN_FY26],
)
def test_the_tiered_key_is_the_question_key_plus_its_tier(m):
    assert events_route._normalize_futures_dedup_key(m) == (
        f"{events_route._futures_dedup_question_key(m)}:{m.market_tier or 0}"
    )


def test_the_tiered_key_values_are_unchanged():
    assert events_route._normalize_futures_dedup_key(BILLS_KALSHI) == (
        "name:which bills will become law in:2"
    )
    assert events_route._normalize_futures_dedup_key(
        _Market(3, "kalshi", "Celtics vs 76ers", 5)
    ) == "matchup:76ers|celtics:5"


def test_the_question_key_reads_no_taxonomy_field():
    """#1769's rule moved with the name logic: `canonical_market_key` is a
    CATEGORY, so it can never be part of a question's identity."""
    body = inspect.getsource(events_route._futures_dedup_question_key).split('"""')[-1]
    assert "canonical_market_key" not in body


# --- both route loops use the decision ----------------------------------------


def test_the_window_and_the_refill_both_call_the_admit_rule():
    src = inspect.getsource(events_route.search_events)
    code = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    assert code.count("_admit_search_future(") == 2
    assert "dkey in seen_search_keys" not in code

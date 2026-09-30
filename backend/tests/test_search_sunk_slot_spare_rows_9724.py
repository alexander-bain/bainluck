"""#9724 r2 — a team search reads the name matches it already holds past rank 20.

After #9724's game key went live (production `adf0d5f0`, 2026-09-30 06:57Z),
`/search?q=braves` served the World Series, the series and NLDS boards, and then
four sunk Phillies vs. Braves props in rows 7-10 (6th/7th/8th Inning Winner,
Player Props). "Will Atlanta Braves advance to the NLDS in the 2026 MLB
Playoffs?" (61380837, open, tier 5) was on neither page. `?debug_timing=1`:
`futures_outcome_arm: skipped`, `futures_refill_source: not_fired`,
`futures_sunk_slot_arm: merged`.

It is a NAME match past rank 20. Production holds 38 open markets whose name
says "braves", so the window statement's 60 tier<=1 rows hold it — in
`_futures_spare_rows`, which nothing read: the collapse refill's gate counts a
sunk row as an answer, and #9597's arm fetches outcome-only rows.

`SERVED` is the page production returned, in served order. `SPARE` is the open
"braves" rows production holds that are not on it (stored ids, links and
categories), standing in for the window statement's ranks 21+. Their order is
not read from production; what the rows test is that a spare name match
outranks every sunk row wherever it sits, and a wrong-sport one does not.
"""

from __future__ import annotations

import inspect

import pytest

from app.routes import events as ev


class _Market:
    def __init__(self, id, name, event_id=None, category="baseball", market_tier=5):
        self.id = id
        self.source = "polymarket"
        self.name = name
        self.market_tier = market_tier
        self.event_id = event_id
        self.llm_sport_category = category
        self.canonical_market_key = None


GAME = 15321782
PA = "Philadelphia Phillies vs. Atlanta Braves"
CALEDONIAN = "Caledonian Braves FC vs. Fraserburgh FC"
NLDS_BRAVES = 61380837
#: The TEAMS card for `braves`: Atlanta (MLB), Alcorn State (NCAAF, NCAAB),
#: Bradley (NCAAB), Southern Brave (The Hundred). No soccer club.
TEAM_CATEGORIES = frozenset({"baseball", "football", "basketball", "cricket"})
SERVED = [
    _Market(114584, "MLB World Series Champion 2026", market_tier=1),
    _Market(63315424, f"{PA} - 1st Inning Winner"),
    _Market(63348823, "MLB Playoffs: Who Will Win Series? - Braves vs. Phillies"),
    _Market(3, "NCAAB Championship Winner", category="basketball", market_tier=1),
    _Market(199050, "MLB: 2026 National League Champion", market_tier=2),
    _Market(60087232, "MLB Playoffs: Team to advance to NLDS"),
    _Market(63315426, f"{PA} - Player Props", GAME),
    _Market(63315417, f"{PA} - 7th Inning Winner"),
    _Market(63315418, f"{PA} - 8th Inning Winner"),
    _Market(63315419, f"{PA} - 6th Inning Winner"),
]
#: Production's verdict: rows 7-10 sit below the #9597 row, where only the sink
#: puts a row, so the game's name key and its link key were both full.
SUNK_ON_THE_SERVED_PAGE = {63315426, 63315417, 63315418, 63315419}
#: Open rows production holds whose name says "braves" and that are not on the
#: served page, with their stored `event_id` and category (read 2026-09-30).
SPARE = [
    _Market(63315416, f"{PA} - 9th Inning Winner"),
    _Market(63319343, f"{PA}: O/U 7.5", GAME),
    _Market(61665136, CALEDONIAN, 15316154, category="soccer"),
    _Market(61665096, f"{CALEDONIAN} - Exact Score", 15316154, category="soccer"),
    _Market(61665107, f"{CALEDONIAN} - First Team to Score", 15316154, category="soccer"),
    _Market(NLDS_BRAVES, "Will Atlanta Braves advance to the NLDS in the 2026 MLB Playoffs?"),
    _Market(63315420, f"{PA} - 5th Inning Winner"),
]


def _words(q):
    return frozenset(ev._SEARCH_WORD.findall(q.lower()))


def _served_state():
    """The handler's state after the window: SERVED admitted, the game full."""
    seen, kept, counts, out = set(), {}, {}, []
    for m in SERVED:
        assert ev._admit_search_future(m, seen, kept, [])
        ev._is_over_match_cap(m, counts, _words("braves"))
        out.append(m)
    for key in (ev._search_match_key(SERVED[1]), f"event:{GAME}"):
        counts[key] = max(counts.get(key, 0), ev._SEARCH_MATCH_ROWS_CAP)
    return seen, kept, counts, set(SUNK_ON_THE_SERVED_PAGE), out


def _page(spare, *, arm_state="skipped", refill_source="not_fired"):
    """The #9724 r2 spare read, then the handler's sink and teamless pass."""
    seen, kept, counts, over, out = _served_state()
    teamless = lambda m: ev._is_teamless_sport(m, TEAM_CATEGORIES)  # noqa: E731
    answer = sum(1 for m in out if m.id not in over and not teamless(m))
    for m in ev._sunk_slot_spare_rows(arm_state, spare, over, answer, refill_source):
        if not ev._admit_search_future(m, seen, kept, []):
            continue
        if ev._is_over_match_cap(m, counts, _words("braves")):
            over.add(m.id)
        out.append(m)
    ordered = ev._demote_teamless_sport(ev._sink_over_match_cap(out, over), TEAM_CATEGORIES)
    return [m.id for m in ordered][: ev._SEARCH_FUTURES_PAGE]


def test_precondition_the_served_page_is_the_window_state():
    assert _page([]) == [m.id for m in SERVED]


def test_the_clubs_nlds_question_takes_a_sunk_props_slot():
    page = _page(SPARE)
    assert NLDS_BRAVES in page
    # The six rows that led stay where they were; the question joins right after.
    assert page[:7] == [m.id for m in SERVED[:6]] + [NLDS_BRAVES]
    assert set(page[7:]) <= SUNK_ON_THE_SERVED_PAGE


def test_the_scottish_braves_stay_off_page_one():
    """Two Caledonian Braves rows are under their fixture's cap, but no club
    called Braves plays soccer here, so they are not answers and sink below
    every baseball row, the game's sunk props included."""
    page = _page(SPARE)
    assert not {61665136, 61665096, 61665107} & set(page)


def test_strawman_without_the_spare_read_the_page_is_the_served_one():
    assert _page(SPARE, refill_source="query") == [m.id for m in SERVED]


@pytest.mark.parametrize("arm_state", ["merged", "shed", "budget_exceeded", "not_reached"])
def test_other_arm_states_read_nothing(arm_state):
    assert _page(SPARE, arm_state=arm_state) == [m.id for m in SERVED]


def test_an_absent_arm_reads_the_spare_rows_too():
    assert NLDS_BRAVES in _page(SPARE, arm_state="absent")


@pytest.mark.parametrize("refill_source", ["window", "query"])
def test_a_refill_that_ran_already_read_these_ranks(refill_source):
    assert ev._sunk_slot_spare_rows("skipped", SPARE, {1}, 3, refill_source) == []


class TestTheGate:
    def test_reads_when_a_sunk_row_would_ship(self):
        assert ev._sunk_slot_spare_rows("skipped", SPARE, {1}, 6, "not_fired") == SPARE

    def test_a_short_spare_page_is_still_read(self):
        assert ev._sunk_slot_spare_rows("skipped", SPARE[:1], {1}, 6, "not_fired") == SPARE[:1]

    def test_nothing_sunk_reads_nothing(self):
        assert ev._sunk_slot_spare_rows("skipped", SPARE, set(), 6, "not_fired") == []

    def test_a_page_the_answers_fill_reads_nothing(self):
        page = ev._SEARCH_FUTURES_PAGE
        assert ev._sunk_slot_spare_rows("skipped", SPARE, {1}, page, "not_fired") == []

    def test_returns_a_copy(self):
        spare = list(SPARE)
        ev._sunk_slot_spare_rows("skipped", spare, {1}, 0, "not_fired").clear()
        assert spare == SPARE


def test_the_route_reads_the_spare_rows_before_paying_for_outcome_rows():
    src = inspect.getsource(ev.search_events)
    spare = src.index("_sunk_slot_spare_rows(")
    assert spare < src.index("_needs_sunk_slot_outcome_arm(")
    assert spare > src.index("_futures_refill_source = \"window\" if refill_rows")
    assert '_futures_refill_source = "spare"' in src

"""#9724 — one GAME stops filling a team search's market rows.

#8628 r2 caps a fixture at two rows, but it reads the fixture from the text
before a colon. `?q=braves` on Wild Card day (production 2026-09-30 04:05Z,
390px) served seven market rows from Phillies vs. Braves, and six of them name
no fixture there: `Spread: Atlanta Braves (-1.5)`, `Atlanta Braves Team Total:
O/U 3.5`, `Will the game go to extra innings?: Philadelphia Phillies vs.
Atlanta Braves`. They all carry the game's `event_id` (15321782). "Will
Atlanta Braves advance to the NLDS?" and the NLDS board were off the page.

The rows are the served page, verbatim, in served order, with their stored
`event_id`s. The outcome-only rows are what production's #9597 sunk-slot arm
returns for `braves` (window order read 2026-09-30).
"""

from __future__ import annotations

import pytest

from app.routes import events as ev


class _Market:
    def __init__(self, id, name, event_id=None, source="polymarket", market_tier=5):
        self.id = id
        self.source = source
        self.name = name
        self.market_tier = market_tier
        self.event_id = event_id
        self.canonical_market_key = None


GAME = 15321782
PA = "Philadelphia Phillies vs. Atlanta Braves"
BRAVES_PAGE = [
    _Market(114584, "MLB World Series Champion 2026", source="kalshi", market_tier=1),
    _Market(63315424, f"{PA} - 1st Inning Winner"),
    _Market(63194385, f"Will there be a run scored in the first inning?: {PA}", GAME),
    _Market(63319344, "1st 5 Innings Spread: Atlanta Braves (-1.5)", GAME),
    _Market(63319351, f"Will the game go to extra innings?: {PA}", GAME),
    _Market(63319353, "Atlanta Braves Team Total: O/U 3.5", GAME),
    _Market(63319354, "Spread: Atlanta Braves (-2.5)", GAME),
    _Market(63319355, "Spread: Atlanta Braves (-1.5)", GAME),
    _Market(3, "NCAAB Championship Winner", source="kalshi", market_tier=1),
    _Market(199050, "MLB: 2026 National League Champion", source="kalshi", market_tier=2),
]
GAME_ONLY_IDS = {63319344, 63319351, 63319353, 63319354, 63319355, 63194385}
#: #9597's outcome-only rows after the three already on the page, in its order.
SUNK_SLOT_ROWS = [
    _Market(60087232, "MLB Playoffs: Team to advance to NLDS"),
    _Market(63319356, "Spread: Philadelphia Phillies (-2.5)", GAME),
    _Market(63319342, "Spread: Philadelphia Phillies (-1.5)", GAME),
    _Market(63319345, "1st 5 Innings Spread: Philadelphia Phillies (-1.5)", GAME),
    _Market(1, "MLB World Series Winner", source="kalshi"),
]


def _words(q):
    return frozenset(ev._SEARCH_WORD.findall(q.lower()))


def _compose(rows, q):
    """The handler's admission loops and its sink, over rows in rank order."""
    seen, kept, counts, over = set(), {}, {}, set()
    out = []
    for m in rows:
        if not ev._admit_search_future(m, seen, kept, []):
            continue
        if ev._is_over_match_cap(m, counts, _words(q)):
            over.add(m.id)
        out.append(m)
    return [m.id for m in ev._sink_over_match_cap(out, over)], over


def _unlinked(rows):
    return [_Market(m.id, m.name, None, m.source, m.market_tier) for m in rows]


def test_precondition_the_name_key_cannot_see_six_of_the_game_rows():
    assert all(
        ev._search_match_key(m) is None for m in BRAVES_PAGE if m.id in GAME_ONLY_IDS
    )


def test_strawman_without_the_link_nothing_is_capped_and_the_page_is_the_served_one():
    ids, over = _compose(_unlinked(BRAVES_PAGE + SUNK_SLOT_ROWS), "braves")
    assert over == set()
    assert ids[:10] == [m.id for m in BRAVES_PAGE]
    assert 60087232 not in ids[:10]


class TestTheGameKey:
    def test_braves_keeps_two_rows_of_the_game_and_sinks_the_rest(self):
        ids, over = _compose(BRAVES_PAGE, "braves")
        assert over == {63319351, 63319353, 63319354, 63319355}
        assert ids[-4:] == [63319351, 63319353, 63319354, 63319355]

    def test_the_nlds_board_takes_a_slot_on_page_one(self):
        ids, over = _compose(BRAVES_PAGE + SUNK_SLOT_ROWS, "braves")
        page = ids[:ev._SEARCH_FUTURES_PAGE]
        assert 60087232 in page
        assert {63319356, 63319342, 63319345} <= over
        # Eight rows lead; two sunk game rows fill the last two slots.
        assert page[:8] == [
            114584, 63315424, 63194385, 63319344, 3, 199050, 60087232, 1,
        ]
        assert set(page[8:]) <= over

    def test_sinking_drops_nothing(self):
        ids, _ = _compose(BRAVES_PAGE + SUNK_SLOT_ROWS, "braves")
        assert sorted(ids) == sorted(m.id for m in BRAVES_PAGE + SUNK_SLOT_ROWS)

    def test_a_row_with_a_name_fixture_and_a_link_counts_against_both(self):
        counts = {}
        rows = [
            _Market(1, f"{PA}: O/U 6.5", GAME),
            _Market(2, f"{PA}: O/U 7.5", GAME),
            _Market(3, "Spread: Atlanta Braves (-2.5)", GAME),
            _Market(4, f"{PA} - 2nd Inning Winner"),
        ]
        assert [ev._is_over_match_cap(m, counts, _words("braves")) for m in rows] == [
            False, False, True, True,
        ]

    def test_two_games_are_two_keys(self):
        counts = {}
        rows = [_Market(i, f"Spread: Braves (-{i}.5)", GAME) for i in (1, 2)]
        rows += [_Market(i, f"Spread: Braves (-{i}.5)", GAME + 1) for i in (3, 4)]
        assert not any(ev._is_over_match_cap(m, counts, _words("braves")) for m in rows)

    @pytest.mark.parametrize("event_id", [None, 0])
    def test_an_unlinked_row_with_no_fixture_is_never_capped(self, event_id):
        counts = {}
        rows = [_Market(i, f"Spread: Braves (-{i}.5)", event_id) for i in range(5)]
        assert not any(ev._is_over_match_cap(m, counts, _words("braves")) for m in rows)
        assert counts == {}


class TestTheQueryThatNamesTheMatch:
    def test_naming_both_sides_still_disarms_a_named_linked_row(self):
        counts = {}
        rows = [_Market(i, f"{PA}: O/U {i}.5", GAME) for i in range(5)]
        assert not any(
            ev._is_over_match_cap(m, counts, _words("phillies braves")) for m in rows
        )

    def test_a_disarmed_row_does_not_spend_the_games_slots(self):
        counts = {}
        named = [_Market(i, f"{PA}: O/U {i}.5", GAME) for i in range(5)]
        for m in named:
            ev._is_over_match_cap(m, counts, _words("phillies braves"))
        spreads = [_Market(10 + i, f"Spread: Atlanta Braves (-{i}.5)", GAME) for i in range(3)]
        assert [
            ev._is_over_match_cap(m, counts, _words("phillies braves")) for m in spreads
        ] == [False, False, True]

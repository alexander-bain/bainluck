"""#8664 — search stops printing an UNLINKED game's Polymarket container.

THE DEFECT, SEEN ON PRODUCTION (2026-09-25 17:3xZ, 390px, `/search?q=kings`).
The ANSWERS card's "Other Sports" row read

    Honor of Kings: Buriram United Esports vs King of Gamers Club (BO5) — Game 1 Winner 91%

"Game 1 Winner" is not an outcome; it is the NAME of a sibling market. Row
62250339 is the Polymarket EVENT row for the series (`group_id`
polymarket:1076304, `event_id` NULL). #8375 withholds exactly this container
from search — but only when `event_id` is set, because the unlinked leg-copy
boards it measured were the legitimate ones. The same day `q=infinite saw` led
with 62357974: "Map Handicap … 48% · O/U 2.5 Games 45% · Map 2 Winner 44%".

🔴 THE CONTROLS ARE THE POINT. "The container is gone" is satisfied by a search
that withholds every unlinked Polymarket board. So: a Yes/No board with no game
("Team to Make Playoffs") stays; a date ladder whose children carry three
outcomes ("Yes / No / September 30") stays; a board with one leg that names no
row stays even when another leg is two-sided; a one-winner board is never a
candidate; #8375's linked arm is byte-for-byte unchanged; and a timed-out read
serves the page unfiltered.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes import events as events_module
from app.routes.events import (
    _outcomes_name_two_sides,
    _search_container_parent_candidates,
    _search_container_parent_ids,
    _search_unlinked_container_parent_candidates,
    _search_unlinked_container_parents_among,
)

GROUP = "polymarket:1076304"
CONTAINER_ID = 62250339
G1, G2, G3 = "0x8d05", "0x0796", "0x277c"
TEAMS = ("Buriram United Esports", "King of Gamers Club")


def _outcome(external_id):
    return SimpleNamespace(external_id=external_id, name="leg", current_probability=0.5)


def _market(id, *, legs, group_id=GROUP, event_id=None, mutually_exclusive=False):
    return SimpleNamespace(
        id=id,
        source="polymarket",
        group_id=group_id,
        event_id=event_id,
        mutually_exclusive=mutually_exclusive,
        outcomes=[_outcome(e) for e in legs],
    )


def _container():
    return _market(CONTAINER_ID, legs=[G1, G2, G3])


def _named(rows):
    """``{(id, external_id): names}`` → the read's one-row-per-outcome shape."""
    return [(mid, GROUP, ext, n) for (mid, ext), names in rows.items() for n in names]


def _game_siblings():
    return _named(
        {(62337574, G1): TEAMS, (62337575, G2): TEAMS, (62337576, G3): TEAMS}
    )


# ── the pure verdict ────────────────────────────────────────────────────────


def test_the_honor_of_kings_container_is_withheld():
    """🔴 THE SHIP: every leg is a sibling row, and the siblings name two sides."""
    candidates = _search_unlinked_container_parent_candidates([_container()])
    assert candidates == {CONTAINER_ID: (GROUP, {G1, G2, G3})}
    assert _search_unlinked_container_parents_among(candidates, _game_siblings()) == {
        CONTAINER_ID
    }


def test_one_two_sided_sibling_is_enough():
    """62357974's board mixes duels, an Over/Under and a handicap — one sided
    sibling makes it a game's container; the other legs need only be rows."""
    siblings = _named(
        {(1, G1): ("Over", "Under"), (2, G2): ("Yes", "No"), (3, G3): ("Yes", "No")}
    )
    candidates = _search_unlinked_container_parent_candidates([_container()])
    assert _search_unlinked_container_parents_among(candidates, siblings) == {CONTAINER_ID}


def test_a_yes_no_board_with_no_game_is_kept():
    """ "VALORANT Champions 2026: Team to Make Playoffs" — #8375's legitimate
    shape. Every leg is a row, and every row is Yes/No."""
    siblings = _named({(1, G1): ("Yes", "No"), (2, G2): ("Yes", "No"), (3, G3): ("No", "Yes")})
    candidates = _search_unlinked_container_parent_candidates([_container()])
    assert _search_unlinked_container_parents_among(candidates, siblings) == set()


def test_a_date_ladder_with_three_outcome_children_is_kept():
    """ "Israel military action against Iraq by...?" — measured: its child
    stores "Yes / No / September 30". Not exactly two sides, so not this shape."""
    siblings = _named(
        {(1, G1): ("Yes", "No", "September 30"), (2, G2): ("Yes", "No"), (3, G3): ("Yes", "No")}
    )
    candidates = _search_unlinked_container_parent_candidates([_container()])
    assert _search_unlinked_container_parents_among(candidates, siblings) == set()


def test_a_leg_that_names_no_row_keeps_the_board_even_when_another_is_sided():
    """#8375's copy test still governs: the parent is the only place an
    unwritten sub-market can be found."""
    siblings = _named({(1, G1): TEAMS, (2, G2): TEAMS})  # G3 never written
    candidates = _search_unlinked_container_parent_candidates([_container()])
    assert _search_unlinked_container_parents_among(candidates, siblings) == set()


def test_a_sided_row_on_another_group_does_not_count():
    siblings = [(mid, "polymarket:999", ext, n) for mid, _g, ext, n in _game_siblings()]
    candidates = _search_unlinked_container_parent_candidates([_container()])
    assert _search_unlinked_container_parents_among(candidates, siblings) == set()


def test_a_one_winner_board_is_never_a_candidate():
    exclusive = _market(1, legs=[G1, G2], mutually_exclusive=True)
    assert _search_unlinked_container_parent_candidates([exclusive]) == {}


def test_the_two_arms_partition_on_the_event():
    """A row is a candidate of exactly one arm, and #8375's linked arm still
    refuses the unlinked row exactly as its own test says."""
    linked = _market(2, legs=[G1, G2], event_id=14780546)
    unlinked = _container()
    assert set(_search_container_parent_candidates([linked, unlinked])) == {2}
    assert set(_search_unlinked_container_parent_candidates([linked, unlinked])) == {
        CONTAINER_ID
    }


@pytest.mark.parametrize(
    "names,expected",
    [
        (TEAMS, True),
        (("Over", "Under"), True),
        (("Infinite", "SAW"), True),
        (("Yes", "No"), False),
        (("Yes", "SAW"), False),
        (("SAW",), False),
        (("Yes", "No", "September 30"), False),
        (("Norway", "Draw", "Denmark"), False),  # exactly two, not "at least"
        (("SAW", "saw"), False),
        (("SAW", None), False),
        (("SAW", "  "), False),
    ],
)
def test_two_sides(names, expected):
    assert _outcomes_name_two_sides(list(names)) is expected


# ── the async read ──────────────────────────────────────────────────────────


def _result(rows):
    r = MagicMock()
    r.all.return_value = rows
    return r


@pytest.fixture
def no_timeout(monkeypatch):
    monkeypatch.setattr(events_module, "_apply_search_statement_timeout", AsyncMock())


@pytest.mark.asyncio
async def test_the_read_names_the_unlinked_container(no_timeout):
    db = AsyncMock()
    savepoint = AsyncMock()
    db.begin_nested = AsyncMock(return_value=savepoint)
    db.execute = AsyncMock(return_value=_result(_game_siblings()))
    got = await _search_container_parent_ids(db, [_container()], deadline=float("inf"))
    assert got == {CONTAINER_ID}
    db.execute.assert_awaited_once()  # no linked candidate ⇒ only the named read
    sql = str(db.execute.await_args.args[0]).lower()
    assert "join futures_outcomes" in sql and "futures_markets.external_id in" in sql
    savepoint.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_both_arms_in_one_request(no_timeout):
    linked = _market(58980362, legs=["0xaaa1"], group_id="polymarket:848221", event_id=1)
    db = AsyncMock()
    db.begin_nested = AsyncMock(return_value=AsyncMock())
    db.execute = AsyncMock(
        side_effect=[
            _result([(61766324, "polymarket:848221", "0xaaa1")]),
            _result(_game_siblings()),
        ]
    )
    got = await _search_container_parent_ids(db, [linked, _container()], float("inf"))
    assert got == {58980362, CONTAINER_ID}
    assert db.execute.await_count == 2


@pytest.mark.asyncio
async def test_a_timeout_on_the_named_read_fails_open(no_timeout, monkeypatch):
    monkeypatch.setattr(events_module, "_is_query_timeout", lambda exc: True)
    db = AsyncMock()
    savepoint = AsyncMock()
    db.begin_nested = AsyncMock(return_value=savepoint)
    db.execute = AsyncMock(side_effect=RuntimeError("canceling statement due to statement timeout"))
    assert await _search_container_parent_ids(db, [_container()], float("inf")) == set()
    savepoint.rollback.assert_awaited_once()
    db.rollback.assert_not_awaited()


def test_a_thin_row_without_event_id_never_reaches_the_event_arm():
    """#6447's thin search row (kalshi, no `event_id` attribute at all) must be
    refused by the shared conditions BEFORE either arm reads `event_id`."""
    thin = SimpleNamespace(id=1, source="kalshi", group_id=None, mutually_exclusive=True, outcomes=[])
    assert _search_container_parent_candidates([thin]) == {}
    assert _search_unlinked_container_parent_candidates([thin]) == {}

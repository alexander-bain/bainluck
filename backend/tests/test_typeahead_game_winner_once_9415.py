"""#9415 — the search dropdown prints each game once, as its game row.

THE DEFECT, SEEN ON PRODUCTION (2026-09-28 16:3xZ, `/api/events/typeahead?q=chiefs`):

    row 2  event    Kansas City Chiefs at Las Vegas Raiders      (event 14781710)
    row 5  futures  KC Chiefs vs LV Raiders — Kansas City 65.5%  (market 61894620,
                    kalshi:KXNFLGAME-26OCT04KCLV, event_id 14781710)

One game, two rows, and the second prints one venue's price for the question the
game row already answers. `/search` has withheld that row since #8734
(`_answers_a_served_game_card`); the dropdown never asked — the same gap #9404
closed for #8378's repeat rule.

WHY THESE TESTS DRIVE THE REAL SCORER. The rule is "the market leaves when its game
is among the rows the reader SEES", and which rows those are is decided by the
scorer, the reservation, the entity floor and the slice together. A hand-ordered
list would assert the fixture (#4614's lesson). So every page here starts from
`Evidence` and goes through `rank_with_keys`, as the route does.

🔴 THE CONTROLS ARE THE POINT. "The winner row is gone" is satisfied by a dropdown
that withholds every market attached to a game. So: the same game's spread and
total stay; a winner market whose game is cut from the seven stays (it is then the
only way to reach the game); an unattached market stays.
"""

import ast
import inspect
import textwrap

from app.routes import events as events_module
from app.routes.events import _typeahead_seven_without_served_game_winners
from app.utils.search_match_class import (
    ENTITY_EVENT_KIND,
    ENTITY_TEAM_KIND,
    Evidence,
    rank_with_keys,
)

GAME = 14781710
OTHER_GAME = 14781799
WINNER = 61894620
OTHER_WINNER = 61894699


def _team():
    return (
        Evidence(name="Kansas City Chiefs", aliases=("Chiefs", "KC"), kind=ENTITY_TEAM_KIND),
        {"type": "team", "text": "Kansas City Chiefs"},
    )


def _game(text, event_id):
    return (
        Evidence(name=text, kind=ENTITY_EVENT_KIND),
        {"type": "event", "text": text, "event_id": event_id},
    )


def _futures(text, market_id, *, answers=None, outcomes=()):
    return (
        Evidence(name=text, outcomes=tuple(outcomes), kind="futures"),
        {"type": "futures", "text": text, "market_id": market_id,
         "_answers_game": answers},
    )


def _winner():
    return _futures("KC Chiefs vs LV Raiders", WINNER, answers=GAME,
                    outcomes=("Kansas City", "Las Vegas"))


def _props(n, start=62932000):
    names = ("Spread", "Total Points", "First Touchdown", "Team Total",
             "Highest Scoring Quarter", "Anytime Touchdown")
    return [_futures(f"KC Chiefs vs LV Raiders: {names[i]}", start + i) for i in range(n)]


def _chiefs_page():
    """The production page for `chiefs`, as `(evidence, payload)` pairs."""
    return [
        _team(),
        _game("Kansas City Chiefs at Las Vegas Raiders", GAME),
        _game("Exeter Chiefs at Bath", 15314850),
        _futures("NFL: 2027 Champion", 129037, outcomes=("Kansas City Chiefs",)),
        _winner(),
        *_props(2),
    ]


def _seven(q, candidates, headline_ids=frozenset()):
    return _typeahead_seven_without_served_game_winners(
        rank_with_keys(q, candidates), set(headline_ids)
    )


def _ids(rows):
    return [r.get("market_id") or r.get("event_id") or r["text"] for r in rows]


def test_the_fixture_reproduces_the_production_page():
    """Fence: without the fix this page carries the game AND its winner market,
    in the order production served them. If this stops holding, the tests below
    are about some other page."""
    keyed = rank_with_keys("chiefs", _chiefs_page())
    texts = [p["text"] for _k, p in keyed]
    assert texts[:5] == [
        "Kansas City Chiefs",
        "Kansas City Chiefs at Las Vegas Raiders",
        "Exeter Chiefs at Bath",
        "KC Chiefs vs LV Raiders",
        "KC Chiefs vs LV Raiders: Spread",
    ], texts


def test_chiefs_shows_the_game_once():
    """🔴 THE SHIP: the game row stays, its winner market leaves, and the same
    game's spread and total are still offered."""
    rows = _seven("chiefs", _chiefs_page())
    ids = _ids(rows)
    assert GAME in ids, ids
    assert WINNER not in ids, ids
    assert {62932000, 62932001} <= set(ids), ids


def test_the_freed_slot_is_refilled():
    """Filter, then slice: the eighth row takes the slot the winner gave up, as on
    /search (#6327)."""
    page = [*_chiefs_page(), *_props(2, start=62932100)]
    assert len(page) == 9
    rows = _seven("chiefs", page)
    assert len(rows) == 7, _ids(rows)
    assert WINNER not in _ids(rows)


def test_a_winner_whose_game_is_cut_from_the_seven_stays():
    """Control: for `kc chiefs` the market outranks its game (the game row does
    not hold `kc`). With five props between them the game is eighth and cut, so
    the market is the only way to that game and must stay."""
    page = [_team(), _winner(), *_props(5),
            _game("Kansas City Chiefs at Las Vegas Raiders", GAME)]
    keyed_texts = [p["text"] for _k, p in rank_with_keys("kc chiefs", page)]
    assert keyed_texts[1] == "KC Chiefs vs LV Raiders", keyed_texts
    assert keyed_texts[7] == "Kansas City Chiefs at Las Vegas Raiders", keyed_texts
    rows = _seven("kc chiefs", page)
    assert WINNER in _ids(rows), _ids(rows)
    assert GAME not in _ids(rows)


def test_the_same_page_with_the_game_visible_drops_the_winner():
    """The control's twin, one prop fewer: now the game is seventh and visible,
    so the market leaves. Proves the control above stayed for the RIGHT reason."""
    page = [_team(), _winner(), *_props(4),
            _game("Kansas City Chiefs at Las Vegas Raiders", GAME)]
    rows = _seven("kc chiefs", page)
    assert GAME in _ids(rows) and WINNER not in _ids(rows), _ids(rows)


def test_a_drop_that_brings_a_second_game_into_view_drops_its_winner_too():
    """The loop, not one pass. Dropping the Raiders market lifts the Broncos game
    into the seventh slot; its own winner market, already visible, must leave
    too. A single pass keeps it."""
    page = [
        _team(),
        _winner(),
        _futures("KC Chiefs vs DEN Broncos", OTHER_WINNER, answers=OTHER_GAME,
                 outcomes=("Kansas City", "Denver")),
        *_props(3),
        _game("Kansas City Chiefs at Las Vegas Raiders", GAME),
        _game("Denver Broncos at Kansas City Chiefs", OTHER_GAME),
    ]
    first_seven = [p.get("event_id") for _k, p in rank_with_keys("kc chiefs", page)][:7]
    assert OTHER_GAME not in first_seven  # fence: B starts out of view
    ids = _ids(_seven("kc chiefs", page))
    assert {GAME, OTHER_GAME} <= set(ids), ids
    assert WINNER not in ids and OTHER_WINNER not in ids, ids


def test_an_unattached_market_is_never_dropped():
    """`_answers_game` None (spreads, props, unattached boards) never matches."""
    rows = _seven("chiefs", _chiefs_page())
    assert 129037 in _ids(rows)


def test_a_page_with_no_game_rows_is_unchanged():
    """No served game ⇒ the function is the old reservation + slice."""
    page = [_team(), _winner(), *_props(2)]
    assert WINNER in _ids(_seven("chiefs", page))


# ── the wiring ──────────────────────────────────────────────────────────────


def _route_source():
    return textwrap.dedent(inspect.getsource(events_module.typeahead_search))


def test_the_route_slices_through_the_function():
    """The route's one slice goes through the #9415 function; no second
    `reserve_headline_slot(...)[:7]` survives beside it."""
    tree = ast.parse(_route_source())
    calls = [
        ast.unparse(n.func)
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    assert calls.count("_typeahead_seven_without_served_game_winners") == 1, calls
    assert "reserve_headline_slot" not in calls, calls


def test_the_futures_row_is_stamped_with_the_search_pages_rule():
    """The stamp asks #8734's helper with the row's own game, inside the futures
    loop while the ORM row is live, and the key is stripped before the response."""
    src = _route_source()
    stamp_at = src.index('"_answers_game": (')
    ask_at = src.index("_answers_a_served_game_card(", stamp_at)
    assert ask_at - stamp_at < 200, (stamp_at, ask_at)
    assert 'market, {getattr(market, "event_id", None)}' in src[ask_at:ask_at + 120]
    assert stamp_at < src.index(
        "_typeahead_seven_without_served_game_winners("
    )
    assert '_s.pop("_answers_game", None)' in src

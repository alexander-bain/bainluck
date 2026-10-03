"""#10298 — search tells the client when a Polymarket game listing sits beside its game.

THE DEFECT, SEEN ON PRODUCTION (2026-10-03 06:4xZ, release v5436,
`/search?q=lions`). GAMES served Lions v Packers, Oct 25, Lions 56%. ANSWERS led
with "Packers vs. Lions — Packers 53% · Oct 25": Polymarket market 61040985, the
listing for that same game (`market_type` field, `event_id` 14780566), whose legs
are `Packers` (a stale last trade), `Spread -5.5`, `1H Spread -6.5` and
`Packers 2H O/U 20.5`. One game, two rows, opposite favourites. The dropdown
served the same row under the game for `q=lions packers`.

THE RULE IS #10089's (October 1 product decision, live on the NFL week hubs):
beside its own game, that listing becomes a link to more questions on the game,
with no percentages. Not withheld, and nothing guessed from leg names. This file
is the producer half: an additive `related_game_listing` key, present only when
the listing's game is in the same response. ux and native render it.

🔴 THE CONTROLS ARE THE POINT. "The key is there" is satisfied by stamping every
row. So: no key when the game is not on the page; no key on a Kalshi row or on a
Polymarket non-field row attached to the same game; `top_outcomes` unchanged on
the stamped row (a client without the consumer half prints what it printed).
"""

import ast
import inspect
import textwrap

import pytest

from app.routes import events as events_module
from app.routes.events import (
    _game_listing_event_id,
    _typeahead_stamp_related_game_listings,
)
from tests.test_search_game_winner_once_8734 import _event, _market, _payload

GAME_ID = 14780566
OTHER_GAME_ID = 14780552
LISTING_ID = 61040985
SPREAD_ROW_ID = 62224145
TOTAL_ID = 62932016
SPECIMEN_LEGS = (
    ("Packers 2H O/U 20.5", 0.5),
    ("1H Spread -6.5", 0.5),
    ("Packers", 0.53),
    ("Spread -5.5", 0.29),
)


def _listing(*, event_id=GAME_ID, source="polymarket", market_type="field"):
    m = _market(LISTING_ID, "Packers vs. Lions", "1022448", event_id=event_id,
                legs=SPECIMEN_LEGS, source=source)
    m.group_id = "polymarket:1022448"
    m.mutually_exclusive = False
    m.market_type = market_type
    return m


def _spread_row():
    m = _market(
        SPREAD_ROW_ID, "Spread: Lions (-5.5)", "0xe82432d3", event_id=GAME_ID,
        legs=(("Lions", 0.29), ("Packers", 0.71)), source="polymarket",
        volume=500_000.0,
    )
    m.group_id = "polymarket:1022448"
    m.market_type = "duel"
    return m


def _total_row():
    m = _market(
        TOTAL_ID, "DET Lions vs GB Packers: Total Points", "KXNFLTOTAL-26OCT25GBDET",
        event_id=GAME_ID, legs=(("Over 50.5 points", 0.52), ("Under 50.5 points", 0.48)),
        volume=400_000.0,
    )
    m.market_type = "field"  # a Kalshi field is not the Polymarket listing
    return m


# ── the pure predicate ──────────────────────────────────────────────────────


def test_the_lions_packers_listing_names_its_game():
    assert _game_listing_event_id(_listing()) == GAME_ID


@pytest.mark.parametrize(
    "kw", [{"source": "kalshi"}, {"market_type": "duel"}, {"market_type": None},
           {"event_id": None}],
)
def test_only_a_linked_polymarket_field_is_a_game_listing(kw):
    assert _game_listing_event_id(_listing(**kw)) is None


# ── the /search route ───────────────────────────────────────────────────────


def _cards(payload):
    out = {f["id"]: f for f in payload.get("futures") or []}
    for fam in payload.get("futures_families") or []:
        for m in [fam.get("headline"), *fam["members"]]:
            if m:
                out[m["id"]] = m
    return out


@pytest.mark.asyncio
async def test_the_route_stamps_the_listing_beside_its_game():
    """🔴 THE SHIP at the route: the listing is still served, says which game it
    belongs to and how many questions it holds, and keeps its outcomes."""
    payload = await _payload(
        [_event(GAME_ID, home="Detroit Lions", away="Green Bay Packers")],
        [_listing(), _spread_row(), _total_row()],
        q="lions",
    )
    assert [r["id"] for r in payload["results"]] == [GAME_ID]
    cards = _cards(payload)
    assert LISTING_ID in cards, cards.keys()
    card = cards[LISTING_ID]
    assert card["related_game_listing"] == {
        "event_id": GAME_ID,
        "question_count": card["outcome_count"],
    }
    assert card["outcome_count"] > 0
    assert [o["name"] for o in card["top_outcomes"]], card
    for other in (SPREAD_ROW_ID, TOTAL_ID):
        assert other in cards, cards.keys()
        assert "related_game_listing" not in cards[other], cards[other]


@pytest.mark.asyncio
async def test_the_route_does_not_stamp_when_the_game_is_not_served():
    """Control: the same window, the game absent from `results`."""
    payload = await _payload(
        [_event(OTHER_GAME_ID, home="Carolina Panthers", away="Detroit Lions")],
        [_listing(), _spread_row()],
        q="lions",
    )
    cards = _cards(payload)
    assert LISTING_ID in cards, cards.keys()
    assert "related_game_listing" not in cards[LISTING_ID]


# ── the dropdown ────────────────────────────────────────────────────────────


def _ta_rows(*, game_in_seven=True):
    rows = [{"type": "event", "text": "Green Bay Packers at Detroit Lions",
             "event_id": GAME_ID if game_in_seven else OTHER_GAME_ID}]
    rows.append({"type": "futures", "text": "Packers vs. Lions", "market_id": LISTING_ID,
                 "top_outcomes": [{"name": "Packers", "probability": 0.53}],
                 "_listing_of_game": GAME_ID, "_listing_questions": 4})
    rows.append({"type": "futures", "text": "NFL: 2027 Champion", "market_id": 129037,
                 "_listing_of_game": None, "_listing_questions": 32})
    return rows


def test_the_dropdown_stamps_the_listing_under_its_game():
    rows = _ta_rows()
    _typeahead_stamp_related_game_listings(rows)
    assert rows[1]["related_game_listing"] == {"event_id": GAME_ID, "question_count": 4}
    assert rows[1]["top_outcomes"] == [{"name": "Packers", "probability": 0.53}]
    assert "related_game_listing" not in rows[2]


def test_the_dropdown_leaves_a_listing_whose_game_is_cut():
    rows = _ta_rows(game_in_seven=False)
    _typeahead_stamp_related_game_listings(rows)
    assert "related_game_listing" not in rows[1]


def test_the_private_keys_never_ship():
    for game_in_seven in (True, False):
        rows = _ta_rows(game_in_seven=game_in_seven)
        _typeahead_stamp_related_game_listings(rows)
        assert not any(k.startswith("_listing") for r in rows for k in r), rows


def _typeahead_source():
    return textwrap.dedent(inspect.getsource(events_module.typeahead_search))


def test_the_dropdown_stamps_after_the_slice_and_reads_the_predicate():
    src = _typeahead_source()
    assert '"_listing_of_game": _game_listing_event_id(market)' in src
    call = src.index("_typeahead_stamp_related_game_listings(suggestions)")
    assert src.index("_typeahead_seven_without_served_game_winners(") < call
    tree = ast.parse(src)
    assert any(
        isinstance(n, ast.Call)
        and getattr(n.func, "id", None) == "_typeahead_stamp_related_game_listings"
        for n in ast.walk(tree)
    )

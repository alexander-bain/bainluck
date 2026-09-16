"""#6447 residual — the SEARCH surfaces stop naming a club that does not exist.

The event-page half merged as `11f3fdcd4` and went live on v4606. Measured on
production the same morning, twenty club queries against `/api/events/search`::

    distinct futures cards inspected                  187
    cards printing a club that does not exist           6

A reader who searched `Jets` was handed a card titled `GB Packers vs NY Jets`
whose two options read `Green Bay` and `New York J`. The page repair could not
reach it — it runs inside `_build_game_markets` on a different payload shape —
so the fix was complete for the screen it was measured on and silent on the
screen a reader reaches first.

Every ticker, market name and outcome name below is a REAL production row, read
from `futures_markets` / `futures_outcomes` on 2026-09-16. The club spellings are
the ones `events.home_team_name` carries for the same rows.

THE TWO LOAD-BEARING TESTS
==========================

:func:`test_one_vocabulary_per_response` and
:func:`test_a_club_two_leagues_spell_differently_is_left_alone` are the pair that
justify the design, and each fails for a different removal:

* pooling the map per CARD instead of per response passes everything else here
  and still prints `New York Jets` above `New York J` in one list;
* dropping ``build_page_repairs``' contradiction guard passes everything else
  here and prints `Los Angeles Clippers` on an NFL Chargers card — `LAC` is
  Chargers in `KXNFL…` and Clippers in `KXNBA…`, verified against the real map.

The second is why the response-wide pool needs the guard at all. On the event
page the guard was future-proofing with zero measured occurrences; here the pool
really does span leagues, so it is live.

WHAT THIS SHIP DOES NOT REACH, ASSERTED SO IT CANNOT BE MISREAD AS COVERED
==========================================================================

Season-long championship fields — `2027 Pro Football Champion` (`KXSB-27`),
`Pro Baseball Champion` (`KXMLB-26`) — still list `Los Angeles R`,
`Los Angeles D` and `New York Y`. Their MARKET ticker carries no team codes and
`repair_truncated_names` parses a game pair, so it resolves nothing for them.
The outcomes' own tickers (`KXSB-27-LAR`) do carry the code, but reading them
means widening `kalshi_display_names`' parser, which has two admin callers and a
pinned suite of its own. Filed separately rather than smuggled in here, and
:func:`test_the_championship_field_is_untouched_and_that_is_recorded` pins the
current answer so the residual cannot be lost.
"""

from __future__ import annotations

import copy

import pytest

from app.utils.game_market_club_names import (
    SEARCH_CARD_FIELDS,
    TYPEAHEAD_CARD_FIELDS,
    any_truncated_side,
    repair_card_club_names,
)

# ---------------------------------------------------------------------------
# Production specimens, 2026-09-16.
# ---------------------------------------------------------------------------

# Market 59659439 — the card a reader gets for `Jets`.
JETS_ID = 59659439
JETS_TICKER = "KXNFLGAME-26SEP20GBNYJ"
JETS_EVENT = 14782704
JETS_CLUBS = ("New York Jets", "Green Bay Packers")

# Market 59659428 — `Rams` and `Giants` both return it, and BOTH its sides are
# truncated, which is why it is the two-repairs-in-one-card specimen.
RAMS_ID = 59659428
RAMS_TICKER = "KXNFLGAME-26SEP21NYGLAR"

# Market 59659433 — the NFL Chargers. `LAC` in an NBA ticker is the Clippers.
CHARGERS_ID = 59659433
CHARGERS_TICKER = "KXNFLGAME-26SEP20LVLAC"
CLIPPERS_TICKER = "KXNBAGAME-26OCT20LACGSW"

# `KXNFLTD-26SEP20GBNYJ` resolves nothing while `KXNFLGAME-26SEP20GBNYJ` resolves
# `New York J` — measured, and the whole reason the map is pooled.
JETS_TICKER_UNRESOLVING = "KXNFLTD-26SEP20GBNYJ"

# Market 40533 / 275 — the championship fields this ship does not reach.
SUPERBOWL_ID = 40533
SUPERBOWL_TICKER = "KXSB-27"


def _search_card(market_id, name, outcome_names):
    """A `/api/events/search` futures card, in the shape the route serves."""
    return {
        "id": market_id,
        "name": name,
        "market_tier": 5,
        "top_outcomes": [
            {"id": 1000 + i, "name": n, "probability": 0.5, "rank": i + 1}
            for i, n in enumerate(outcome_names)
        ],
    }


def _typeahead_card(market_id, text, outcome_names):
    """A `/api/events/typeahead` dropdown row — same question, other key names."""
    return {
        "type": "futures",
        "market_id": market_id,
        "text": text,
        "top_outcomes": [
            {"name": n, "probability": 0.5} for n in outcome_names
        ],
    }


def _outcome_names(card):
    return [o["name"] for o in card["top_outcomes"]]


# ---------------------------------------------------------------------------
# The ship.
# ---------------------------------------------------------------------------


def test_the_jets_card_stops_offering_new_york_j():
    card = _search_card(JETS_ID, "GB Packers vs NY Jets", ["Green Bay", "New York J"])

    changed = repair_card_club_names(
        [card],
        {JETS_ID: JETS_TICKER},
        title_field=SEARCH_CARD_FIELDS[0],
        id_field=SEARCH_CARD_FIELDS[1],
        protected_names=JETS_CLUBS,
    )

    assert changed == 1
    assert _outcome_names(card) == ["Green Bay", "New York Jets"]
    # The title was already the house short form and must not move.
    assert card["name"] == "GB Packers vs NY Jets"


def test_both_sides_of_one_card_are_completed():
    card = _search_card(
        RAMS_ID, "NY Giants vs LA Rams", ["Los Angeles R", "New York G"]
    )

    changed = repair_card_club_names(
        [card],
        {RAMS_ID: RAMS_TICKER},
        title_field=SEARCH_CARD_FIELDS[0],
        id_field=SEARCH_CARD_FIELDS[1],
        protected_names=("Los Angeles Rams", "New York Giants"),
    )

    assert changed == 2
    assert _outcome_names(card) == ["Los Angeles Rams", "New York Giants"]


def test_the_dropdown_row_is_the_same_repair_under_other_key_names():
    row = _typeahead_card(
        JETS_ID, "GB Packers vs NY Jets", ["Green Bay", "New York J"]
    )

    changed = repair_card_club_names(
        [row],
        {JETS_ID: JETS_TICKER},
        title_field=TYPEAHEAD_CARD_FIELDS[0],
        id_field=TYPEAHEAD_CARD_FIELDS[1],
        protected_names=JETS_CLUBS,
    )

    assert changed == 1
    assert _outcome_names(row) == ["Green Bay", "New York Jets"]


def test_a_truncated_title_side_is_completed_too():
    """The truncation is not always in an outcome.

    `Green Bay vs New York J: 1st Half Spread` has outcomes `Green Bay`/`New
    York J` on the game line but `Over`/`Under` on the total — so a repair that
    only ever read outcome labels would leave the title naming a club that does
    not exist. Real row, `futures_markets` 2026-09-16.
    """
    card = _search_card(
        JETS_ID, "Green Bay vs New York J: 2nd Half Total", ["Over", "Under"]
    )

    changed = repair_card_club_names(
        [card],
        {JETS_ID: JETS_TICKER},
        title_field=SEARCH_CARD_FIELDS[0],
        id_field=SEARCH_CARD_FIELDS[1],
    )

    assert changed == 1
    assert card["name"] == "Green Bay vs New York Jets: 2nd Half Total"
    assert _outcome_names(card) == ["Over", "Under"]


# ---------------------------------------------------------------------------
# The two that justify the design.
# ---------------------------------------------------------------------------


def test_one_vocabulary_per_response():
    """Two cards for one club, one resolving ticker — BOTH read the full name.

    This is the search-list form of #5181's criterion. A per-card pool passes
    every other test in this file and ships a results page reading `New York
    Jets` on one row and `New York J` on the next, which is the objection the
    event-page version exists to answer.
    """
    resolving = _search_card(
        JETS_ID, "GB Packers vs NY Jets", ["Green Bay", "New York J"]
    )
    unresolving = _search_card(
        JETS_ID + 1, "New York J vs Detroit: Touchdowns", ["New York J", "Detroit"]
    )

    changed = repair_card_club_names(
        [resolving, unresolving],
        {JETS_ID: JETS_TICKER, JETS_ID + 1: JETS_TICKER_UNRESOLVING},
        title_field=SEARCH_CARD_FIELDS[0],
        id_field=SEARCH_CARD_FIELDS[1],
    )

    assert changed == 3
    assert _outcome_names(resolving) == ["Green Bay", "New York Jets"]
    assert _outcome_names(unresolving) == ["New York Jets", "Detroit"]
    assert unresolving["name"] == "New York Jets vs Detroit: Touchdowns"


def test_a_club_two_leagues_spell_differently_is_left_alone():
    """`LAC` is the Chargers in the NFL and the Clippers in the NBA.

    A response-wide pool is what makes this reachable, so the contradiction
    guard is what makes it safe. Verified against the real ticker map: both
    tickers below resolve `Los Angeles C`, and to different clubs. Neither card
    is rewritten — the venue's own text is this module's failure direction
    everywhere, and printing the wrong club is strictly worse than printing a
    truncated one.
    """
    nfl = _search_card(
        CHARGERS_ID, "LV Raiders vs LA Chargers", ["Las Vegas", "Los Angeles C"]
    )
    nba = _search_card(
        CHARGERS_ID + 1, "LA Clippers vs GS Warriors", ["Los Angeles C", "Golden State"]
    )
    before = copy.deepcopy([nfl, nba])

    changed = repair_card_club_names(
        [nfl, nba],
        {CHARGERS_ID: CHARGERS_TICKER, CHARGERS_ID + 1: CLIPPERS_TICKER},
        title_field=SEARCH_CARD_FIELDS[0],
        id_field=SEARCH_CARD_FIELDS[1],
    )

    assert changed == 0
    assert [nfl, nba] == before


def test_the_contradiction_only_drops_the_contested_name():
    """A contested key must not take an uncontested one down with it."""
    nfl = _search_card(
        CHARGERS_ID, "LV Raiders vs LA Chargers", ["Los Angeles C", "Las Vegas"]
    )
    nba = _search_card(
        CHARGERS_ID + 1, "LA Clippers vs GS Warriors", ["Los Angeles C", "Golden State"]
    )
    jets = _search_card(
        JETS_ID, "GB Packers vs NY Jets", ["Green Bay", "New York J"]
    )

    repair_card_club_names(
        [nfl, nba, jets],
        {
            CHARGERS_ID: CHARGERS_TICKER,
            CHARGERS_ID + 1: CLIPPERS_TICKER,
            JETS_ID: JETS_TICKER,
        },
        title_field=SEARCH_CARD_FIELDS[0],
        id_field=SEARCH_CARD_FIELDS[1],
    )

    assert _outcome_names(nfl) == ["Los Angeles C", "Las Vegas"]
    assert _outcome_names(nba) == ["Los Angeles C", "Golden State"]
    assert _outcome_names(jets) == ["Green Bay", "New York Jets"]


# ---------------------------------------------------------------------------
# The refusals.
# ---------------------------------------------------------------------------


def test_our_own_anchored_club_name_vetoes_the_rewrite():
    """`Real Sociedad B` is a real club that matches the truncation shape."""
    card = _search_card(
        JETS_ID, "Real Sociedad B vs Eibar", ["Real Sociedad B", "Eibar"]
    )

    changed = repair_card_club_names(
        [card],
        {JETS_ID: JETS_TICKER},
        title_field=SEARCH_CARD_FIELDS[0],
        id_field=SEARCH_CARD_FIELDS[1],
        protected_names=("Real Sociedad B", "Eibar"),
    )

    assert changed == 0
    assert _outcome_names(card) == ["Real Sociedad B", "Eibar"]


def test_a_veto_from_another_card_in_the_response_still_binds():
    """The pool is response-wide, so the veto is too — the safe direction.

    A real club matching the shape ANYWHERE in the response stops the rewrite
    everywhere in it. The cost is one card keeping the venue's truncation; the
    alternative is a rewrite made while a row on the same screen says that
    string is somebody's actual name.
    """
    truncated = _search_card(
        JETS_ID, "GB Packers vs NY Jets", ["Green Bay", "New York J"]
    )
    real_club = _search_card(
        JETS_ID + 2, "New York J vs Someone", ["New York J", "Someone"]
    )

    changed = repair_card_club_names(
        [truncated, real_club],
        {JETS_ID: JETS_TICKER, JETS_ID + 2: None},
        title_field=SEARCH_CARD_FIELDS[0],
        id_field=SEARCH_CARD_FIELDS[1],
        protected_names=("New York J",),
    )

    assert changed == 0
    assert _outcome_names(truncated) == ["Green Bay", "New York J"]


def test_placeholder_outcomes_are_shaped_like_a_truncation_and_are_refused():
    """`New York Governor Election Winner` lists `Option C` / `Option E`.

    Real production card (market 113071, ticker `57184`). The cheap pre-test
    says "maybe" — it is deliberately over-inclusive — and then no ticker
    resolves anything, so the repair leaves them exactly as they were. That the
    two halves disagree here is the design: shape proposes, the ticker decides.

    (The placeholder labels are their own defect and are not this ship's.)
    """
    card = _search_card(
        113071, "New York Governor Election Winner", ["Option C", "Option E"]
    )

    assert any_truncated_side([card], title_field="name") is True

    changed = repair_card_club_names(
        [card],
        {113071: "57184"},
        title_field=SEARCH_CARD_FIELDS[0],
        id_field=SEARCH_CARD_FIELDS[1],
    )

    assert changed == 0
    assert _outcome_names(card) == ["Option C", "Option E"]


def test_the_championship_field_is_untouched_and_that_is_recorded():
    """`2027 Pro Football Champion` still lists `Los Angeles R`. Stated, not hidden.

    `KXSB-27` carries no team codes and `repair_truncated_names` parses a game
    pair, so nothing resolves. If a later ship teaches the parser to read an
    OUTCOME ticker (`KXSB-27-LAR`), this test is the one that should change, and
    changing it is how the residual gets closed on purpose rather than by
    accident.
    """
    card = _search_card(
        SUPERBOWL_ID,
        "2027 Pro Football Champion",
        ["Los Angeles R", "Buffalo", "Baltimore"],
    )

    changed = repair_card_club_names(
        [card],
        {SUPERBOWL_ID: SUPERBOWL_TICKER},
        title_field=SEARCH_CARD_FIELDS[0],
        id_field=SEARCH_CARD_FIELDS[1],
    )

    assert changed == 0
    assert _outcome_names(card)[0] == "Los Angeles R"


# ---------------------------------------------------------------------------
# The pre-test, which is what keeps this off the latency budget.
# ---------------------------------------------------------------------------


def test_the_pre_test_is_false_for_a_clean_response():
    """No truncation shape anywhere ⇒ the route pays for no `events` read.

    181 of the 187 cards measured on production are this case, and so is every
    non-sport query. If this ever returns True for a clean page, the search path
    starts paying a keyed read on every keystroke.
    """
    cards = [
        _search_card(1, "GB Packers vs NY Jets", ["Green Bay", "New York Jets"]),
        _search_card(2, "Pro Basketball Champion", ["Boston", "Oklahoma City"]),
        _search_card(3, "Fed Decision in September", ["Yes", "No"]),
    ]

    assert any_truncated_side(cards, title_field="name") is False


@pytest.mark.parametrize(
    "card",
    [
        _search_card(1, "Green Bay vs New York J: 1st Half Spread", ["Over", "Under"]),
        _search_card(2, "Some Market", ["Los Angeles R", "Buffalo"]),
    ],
    ids=["in-the-title", "in-an-outcome"],
)
def test_the_pre_test_sees_a_truncation_in_either_slot(card):
    assert any_truncated_side([card], title_field="name") is True


# ---------------------------------------------------------------------------
# Shape safety.
# ---------------------------------------------------------------------------


def test_the_same_dict_in_two_buckets_is_repaired_once_for_both():
    """`futures` and `futures_families` hold the SAME dict, by identity.

    `_formatted_by_id` is built once and both buckets index into it, which is
    why the route repairs that map rather than either list. If the repair ever
    started rebuilding instead of mutating, one bucket would be fixed and the
    other would not, and no test that looks at a single list could see it.
    """
    card = _search_card(JETS_ID, "GB Packers vs NY Jets", ["Green Bay", "New York J"])
    flat = [card]
    families = [{"headline": card, "markets": [card]}]

    repair_card_club_names(
        [card],
        {JETS_ID: JETS_TICKER},
        title_field=SEARCH_CARD_FIELDS[0],
        id_field=SEARCH_CARD_FIELDS[1],
    )

    assert _outcome_names(flat[0]) == ["Green Bay", "New York Jets"]
    assert _outcome_names(families[0]["headline"]) == ["Green Bay", "New York Jets"]
    assert families[0]["markets"][0] is flat[0]


def test_applying_twice_changes_nothing_the_second_time():
    """A truncated name is a prefix of its own replacement (`Ramsams`)."""
    card = _search_card(
        RAMS_ID, "New York G vs Los Angeles R", ["Los Angeles R", "New York G"]
    )
    args = dict(
        title_field=SEARCH_CARD_FIELDS[0],
        id_field=SEARCH_CARD_FIELDS[1],
    )

    first = repair_card_club_names([card], {RAMS_ID: RAMS_TICKER}, **args)
    settled = copy.deepcopy(card)
    second = repair_card_club_names([card], {RAMS_ID: RAMS_TICKER}, **args)

    assert first == 3
    assert second == 0
    assert card == settled
    assert card["name"] == "New York Giants vs Los Angeles Rams"


@pytest.mark.parametrize(
    "card",
    [
        {"id": 1, "name": None, "top_outcomes": None},
        {"id": 2, "name": "GB Packers vs NY Jets"},
        {"id": 3, "name": "", "top_outcomes": []},
        {"id": None, "name": "New York J vs Detroit", "top_outcomes": [{}]},
    ],
    ids=["nulls", "no-outcomes-key", "empty", "no-market-id"],
)
def test_a_thin_card_is_not_a_500(card):
    """A serializer must never be the thing that 500s a search page."""
    assert any_truncated_side([card], title_field="name") in (True, False)
    assert (
        repair_card_club_names(
            [card],
            {1: JETS_TICKER, 2: JETS_TICKER, 3: JETS_TICKER},
            title_field=SEARCH_CARD_FIELDS[0],
            id_field=SEARCH_CARD_FIELDS[1],
        )
        == 0
    )


def test_no_cards_is_no_work():
    assert any_truncated_side([], title_field="name") is False
    assert (
        repair_card_club_names(
            [], {}, title_field="name", id_field="id"
        )
        == 0
    )

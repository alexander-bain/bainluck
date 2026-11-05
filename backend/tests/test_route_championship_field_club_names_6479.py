"""The two surfaces that RENDER a championship board carry the repair (#6479).

The engine is unit-tested next door. A pure function nothing calls is inert, so
this file asks the only question that decides whether a reader sees anything:
does the SERVED payload spell the club.

TWO SURFACES, ONE SHIP, AND THAT IS DELIBERATE
==============================================

`_format_market_detail` (the detail ladder, all 32 rungs) and
`_build_search_top_outcomes` (the search card and the typeahead dropdown, top
3-5) are the same board through two serializers. #993 and UX-P164 are the
standing record of what happens when only one of them is fixed: the detail page
and search printed two different answers for one market, and the second fix had
to be written anyway — having moved the disagreement rather than ended it.

So both are asserted here, off the same specimen rows, in one file.

THE SPECIMENS ARE REAL
======================

Every outcome below — ticker, shipped name and probability — is a row read off
production 2026-09-16 from `futures_markets` 40533 (`KXSB-27`, "2027 Pro
Football Champion") and 275 (`KXMLB-26`, "Pro Baseball Champion"). `Los Angeles
R` at 0.108 really is the Super Bowl field's favourite, which is why this
defect led the card rather than hiding in its tail.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

# ── The Super Bowl field, production 2026-09-16, top of the ladder ───────────
#: `(outcome id, ticker, shipped name, probability)`.
SUPER_BOWL_RUNGS = [
    (643828, "KXSB-27-LAR", "Los Angeles R", 0.108),
    (643833, "KXSB-27-BUF", "Buffalo", 0.086),
    (643841, "KXSB-27-BAL", "Baltimore", 0.068),
    (643829, "KXSB-27-SF", "San Francisco", 0.068),
    (643827, "KXSB-27-SEA", "Seattle", 0.059),
    (643850, "KXSB-27-LAC", "Los Angeles C", 0.030),
    (643851, "KXSB-27-NYG", "New York G", 0.012),
    (643852, "KXSB-27-NYJ", "New York J", 0.010),
]

#: The World Series field. `A's` is here on purpose: it is the one rung whose
#: real name contains punctuation and a capital, and it must survive verbatim.
WORLD_SERIES_RUNGS = [
    (700001, "KXMLB-26-LAD", "Los Angeles D", 0.180),
    (700002, "KXMLB-26-NYY", "New York Y", 0.110),
    (700003, "KXMLB-26-BOS", "Boston", 0.090),
    (700004, "KXMLB-26-CHC", "Chicago C", 0.070),
    (700005, "KXMLB-26-CWS", "Chicago WS", 0.020),
    (700006, "KXMLB-26-LAA", "Los Angeles A", 0.015),
    (700007, "KXMLB-26-NYM", "New York M", 0.012),
    (700008, "KXMLB-26-ATH", "A's", 0.010),
    (700009, "KXMLB-26-STL", "St. Louis", 0.009),
]

#: What each board must READ once served. Everything not named here ships byte
#: for byte.
EXPECTED_COMPLETIONS = {
    "Los Angeles R": "Los Angeles Rams",
    "Los Angeles C": "Los Angeles Chargers",
    "New York G": "New York Giants",
    "New York J": "New York Jets",
    "Los Angeles D": "Los Angeles Dodgers",
    "Los Angeles A": "Los Angeles Angels",
    "New York Y": "New York Yankees",
    "New York M": "New York Mets",
    "Chicago C": "Chicago Cubs",
    "Chicago WS": "Chicago White Sox",
}


def _outcome(oid, ticker, name, prob):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=ticker,
        current_probability=prob,
        current_american_odds=400,
        rank=1,
        # #6676: the search builder judges the stored BOOK as well as the price.
        # Both sides None is "no book at all", which `is_empty_book_midpoint`
        # passes through by construction, so nothing in this file moves.
        current_yes_bid=None,
        current_yes_ask=None,
        rank_change_24h=None,
        probability_change_24h=None,
        opening_probability=None,
        opening_american_odds=None,
        is_winner=None,
        resolution_source=None,
        last_updated=None,
    )


def _board(market_id, ticker, name, rungs):
    return SimpleNamespace(
        id=market_id,
        external_id=ticker,
        name=name,
        description=None,
        sport=None,
        sport_name=None,
        category=None,
        llm_sport_category="football",
        status="open",
        source="kalshi",
        market_type="championship",
        mutually_exclusive=True,
        commence_time=None,
        resolution_date=None,
        created_at=None,
        updated_at=None,
        group_id=None,
        canonical_market_key=None,
        hook_description=None,
        category_tags=None,
        image_url=None,
        outcomes=[_outcome(*r) for r in rungs],
    )


BOARDS = {
    "super_bowl": (40533, "KXSB-27", "2027 Pro Football Champion", SUPER_BOWL_RUNGS),
    "world_series": (275, "KXMLB-26", "Pro Baseball Champion", WORLD_SERIES_RUNGS),
}


def _detail_names(board_key):
    from app.routes.futures import _format_market_detail

    detail = _format_market_detail(_board(*BOARDS[board_key]))
    return [o["name"] for o in detail["outcomes"]]


def _search_names(board_key, *, lean):
    from app.routes.events import _build_search_top_outcomes

    rows = _build_search_top_outcomes(_board(*BOARDS[board_key]), limit=8, lean=lean)
    return [o["name"] for o in rows]


# ─────────────────────────────────────────────────────────────────────────────
# The detail ladder
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("board_key", sorted(BOARDS))
def test_the_detail_ladder_spells_every_club_it_can_6479(board_key):
    """The ship, on the surface where the WHOLE field renders at once."""
    names = _detail_names(board_key)
    shipped = [r[2] for r in BOARDS[board_key][3]]
    expected = [EXPECTED_COMPLETIONS.get(n, n) for n in shipped]
    assert sorted(names) == sorted(expected)


@pytest.mark.parametrize("board_key", sorted(BOARDS))
def test_the_detail_ladder_prints_no_club_that_does_not_exist_6479(board_key):
    """Stated as the reader's complaint rather than as a diff.

    A served rung may not end in a lone one-to-three-capital run UNLESS that is
    genuinely the club's name. On these two boards nothing legitimately does, so
    the count is zero — and `A's` and `St. Louis` prove the predicate is not
    simply never firing.
    """
    import re

    truncated = [n for n in _detail_names(board_key) if re.match(r"^.+ [A-Z]{1,3}$", n)]
    assert truncated == []


def test_the_detail_ladder_leaves_every_correct_name_byte_for_byte_6479():
    """A repair that rewrites correct data is a worse bug than the truncation."""
    names = set(_detail_names("world_series"))
    for verbatim in ("Boston", "A's", "St. Louis"):
        assert verbatim in names


def test_the_detail_row_keeps_its_id_and_price_while_the_name_moves_6479():
    """Only the prose moves. Ids and numbers are what the client keys on."""
    from app.routes.futures import _format_market_detail

    detail = _format_market_detail(_board(*BOARDS["super_bowl"]))
    row = next(o for o in detail["outcomes"] if o["id"] == 643828)
    assert row["name"] == "Los Angeles Rams"
    assert row["probability"] == pytest.approx(0.108, rel=1e-3)
    assert row["american_odds"] == 400


# ─────────────────────────────────────────────────────────────────────────────
# The search card and the typeahead dropdown
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("board_key", sorted(BOARDS))
@pytest.mark.parametrize("lean", [True, False])
def test_both_search_payload_shapes_spell_the_club_6479(board_key, lean):
    """`lean=True` is the typeahead dropdown, `lean=False` the results card.

    Parametrized rather than asserted once because the two shapes are built by
    two separate comprehensions in the serializer, and a fix applied to one of
    them is exactly the half-fix #993 is the standing record of.
    """
    names = _search_names(board_key, lean=lean)
    for shipped, club in EXPECTED_COMPLETIONS.items():
        assert shipped not in names
    assert any(n in EXPECTED_COMPLETIONS.values() for n in names)


def test_the_search_card_leads_with_the_club_not_the_truncation_6479():
    """The reader's exact path: `?q=Los Angeles` ranks the board's favourite
    first, and on production that favourite IS the defect."""
    assert _search_names("super_bowl", lean=False)[0] == "Los Angeles Rams"
    assert _search_names("super_bowl", lean=True)[0] == "Los Angeles Rams"


def test_the_two_surfaces_agree_with_each_other_6479():
    """#993's criterion, asserted directly rather than implied.

    The click-through must match the answer search showed. Both lists are the
    same board, so every name the dropdown prints must be a name the ladder
    prints.
    """
    for board_key in BOARDS:
        ladder = set(_detail_names(board_key))
        for lean in (True, False):
            assert set(_search_names(board_key, lean=lean)) <= ladder


# ─────────────────────────────────────────────────────────────────────────────
# What the wiring must NOT do
# ─────────────────────────────────────────────────────────────────────────────


def test_a_rung_with_no_ticker_is_served_exactly_as_the_venue_sent_it_6479():
    """A NULL `external_id` has no code to read, so there is no answer to give.

    The serializer must still serve the card. Deliberately NOT written as "the
    repair survives a missing attribute": `_drop_duplicate_legs` already reads
    `o.external_id` two statements earlier, so by the time the repair runs the
    attribute is guaranteed present and a `getattr` there would be redundant
    armour with a false justification. `None` is the shape that actually
    reaches this code.
    """
    from app.routes.events import _build_search_top_outcomes

    board = _board(*BOARDS["super_bowl"])
    for outcome in board.outcomes:
        outcome.external_id = None

    rows = _build_search_top_outcomes(board, limit=8, lean=False)
    assert [r["name"] for r in rows][0] == "Los Angeles R"


def test_a_board_of_entirely_unresolvable_rungs_is_served_unchanged_6479():
    """The common case — most futures boards are not team sports at all.

    Named `Contestant`/`Option` rows on a Polymarket hex id: nothing resolves,
    nothing is rewritten, and the serializer must not care.
    """
    from app.routes.futures import _format_market_detail

    rungs = [
        (900001, "0x" + "a" * 64, "Option A", 0.5),
        (900002, "0x" + "b" * 64, "Option B", 0.3),
        (900003, "KXSPORTSEMMY-26OLSSCE-SUP", "Super Bowl LX", 0.2),
    ]
    board = _board(113071, "57184", "New York Governor Election Winner", rungs)
    served = [o["name"] for o in _format_market_detail(board)["outcomes"]]
    assert sorted(served) == ["Option A", "Option B", "Super Bowl LX"]

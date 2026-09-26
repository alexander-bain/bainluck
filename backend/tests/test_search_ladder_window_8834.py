"""#8834 — a threshold ladder's search card shows the rungs around its crossing, in order.

WHAT A READER SAW, production 2026-09-26 14:40Z, ``/search?q=fed rate`` at 390px::

    Fed funds rate after Oct 2026 meeting?
      Above 2.75% >99% · Above 3.75% >99% · Above 3.00% >99% · Above 3.25% >99% · Above 3.50% 99%

Five always-true rungs out of order, while the rungs that carry the answer —
``Above 4.00%`` 62.5%, ``Above 4.25%`` 1.5% — were never drawn. Top-N by
probability picks the LOOSEST rungs of a nested ladder, and the 0.995 ties fell
back to row order.

THE FIXTURE IS THE SPECIMEN'S STORED ROWS (Kalshi 109947, all 11 legs, read via
``db-query`` 2026-09-26 ~15:10Z), so the builder's own pre-sort refusals run on
the real bids and asks.

THE CONTROLS: an exclusive field and a mixed ``↑``/``↓`` board are not one
ladder and must keep the probability order they had.
"""

from types import SimpleNamespace

from app.routes.events import _build_search_top_outcomes

#: ``(id, name, external_id, prob, bid, ask)`` — 109947 verbatim, row order as stored.
SPECIMEN_LEGS = [
    (1601946, "Above 2.75%", "KXFED-26OCT-T2.75", 0.995, 0.99, 1.0),
    (1601947, "Above 3.00%", "KXFED-26OCT-T3.00", 0.995, 0.99, 1.0),
    (1601948, "Above 3.25%", "KXFED-26OCT-T3.25", 0.995, 0.99, 1.0),
    (1601949, "Above 3.50%", "KXFED-26OCT-T3.50", 0.99, 0.98, 1.0),
    (1601950, "Above 3.75%", "KXFED-26OCT-T3.75", 0.995, 0.99, 1.0),
    (1601951, "Above 4.00%", "KXFED-26OCT-T4.00", 0.625, 0.62, 0.63),
    (1601952, "Above 5.25%", "KXFED-26OCT-T5.25", 0.01, 0.0, 0.01),
    (1601953, "Above 4.75%", "KXFED-26OCT-T4.75", 0.01, 0.0, 0.01),
    (1601954, "Above 5.00%", "KXFED-26OCT-T5.00", 0.01, 0.0, 0.01),
    (1601955, "Above 4.25%", "KXFED-26OCT-T4.25", 0.015, 0.01, 0.02),
    (1601956, "Above 4.50%", "KXFED-26OCT-T4.50", 0.02, 0.0, 0.02),
]

CROSSING_ID = 1601951  # Above 4.00%, the rung nearest even


def _leg(oid, name, ext, prob, bid, ask):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=ext,
        current_probability=prob,
        current_american_odds=None,
        rank=None,
        probability_change_24h=None,
        is_winner=False,
        resolution_source="ungradeable_result",
        current_yes_bid=bid,
        current_yes_ask=ask,
        price_changed_at=None,
        last_updated=None,
    )


def _market(legs=SPECIMEN_LEGS, *, name="Fed funds rate after Oct 2026 meeting?",
            mutually_exclusive=False):
    return SimpleNamespace(
        id=109947,
        name=name,
        source="kalshi",
        status="open",
        mutually_exclusive=mutually_exclusive,
        outcomes=[_leg(*row) for row in legs],
    )


def _names(out):
    return [o["name"] for o in out]


def test_the_card_draws_the_rungs_around_the_crossing_in_threshold_order():
    out = _build_search_top_outcomes(_market())
    assert _names(out) == [
        "Above 3.50%", "Above 3.75%", "Above 4.00%", "Above 4.25%", "Above 4.50%",
    ]
    # The answer is ON the card, at its raw price — a ladder is not squeezed.
    crossing = next(o for o in out if o["id"] == CROSSING_ID)
    assert crossing["probability"] == 0.625


def _printed_pair(out):
    """What the dropdown PRINTS: the first two priced rows
    (`frontend/lib/searchSuggestionDisplay.ts::futuresAnswer`), not all three."""
    return [(o["name"], o["probability"]) for o in out if o["probability"] is not None][:2]


def test_the_typeahead_prints_the_pair_that_straddles_the_crossing():
    # #993: the dropdown and the card are one pair — both must move. The first
    # window led with two rungs, so the dropdown printed `3.75% >99% · 4.00% 63%`
    # — both over even — and never the rung under it.
    out = _build_search_top_outcomes(_market(), limit=3, lean=True)
    assert _names(out) == ["Above 4.00%", "Above 4.25%", "Above 4.50%"]
    assert _printed_pair(out) == [("Above 4.00%", 0.625), ("Above 4.25%", 0.015)]


def test_a_ladder_wholly_on_one_side_of_even_clamps_to_the_nearest_end():
    # `Next Fed rate hike?` (61461512): every rung 92–98%, a DATE ladder that
    # rises with the deadline. The nearest rung to even is the earliest.
    legs = [
        (1, "Before 2029", "KXFEDHIKE-29", 0.98, 0.97, 0.99),
        (2, "Before July 2028", "KXFEDHIKE-28JUL", 0.98, 0.97, 0.99),
        (3, "Before 2028", "KXFEDHIKE-28", 0.98, 0.97, 0.99),
        (4, "Before July 2027", "KXFEDHIKE-27JUL", 0.955, 0.95, 0.96),
        (5, "Before 2027", "KXFEDHIKE-27", 0.915, 0.91, 0.92),
        (6, "Before July 2026", "KXFEDHIKE-26JUL", 0.85, 0.84, 0.86),
    ]
    out = _build_search_top_outcomes(_market(legs, name="Next Fed rate hike?"), limit=3)
    assert _names(out) == ["Before July 2026", "Before 2027", "Before July 2027"]
    lean = _build_search_top_outcomes(
        _market(legs, name="Next Fed rate hike?"), limit=3, lean=True
    )
    assert _printed_pair(lean) == [("Before July 2026", 0.85), ("Before 2027", 0.915)]


def test_a_falling_ladder_wholly_over_even_prints_its_last_two_rungs():
    # The mirror of the clamp above: every "Above X" rung over even, so the rungs
    # nearest the answer are the TOP two. A 3-rung clamp would print 3.00/3.25 and
    # hide 3.50, the rung nearest even.
    legs = [
        (31, "Above 2.50%", "KXFED-T2.50", 0.99, 0.98, 1.0),
        (32, "Above 2.75%", "KXFED-T2.75", 0.98, 0.97, 0.99),
        (33, "Above 3.00%", "KXFED-T3.00", 0.96, 0.95, 0.97),
        (34, "Above 3.25%", "KXFED-T3.25", 0.90, 0.89, 0.91),
        (35, "Above 3.50%", "KXFED-T3.50", 0.72, 0.70, 0.74),
    ]
    out = _build_search_top_outcomes(_market(legs), limit=3, lean=True)
    assert _printed_pair(out) == [("Above 3.25%", 0.90), ("Above 3.50%", 0.72)]


def test_a_withheld_rung_is_neither_the_centre_nor_drawn():
    """A refused price draws no dash: the window is the priced rungs around the
    crossing, in threshold order (see the Jan 2027 specimen below for why)."""
    out = _build_search_top_outcomes(_market(), withheld={CROSSING_ID})
    assert CROSSING_ID not in [o["id"] for o in out]
    assert all(o["probability"] is not None for o in out)
    names = _names(out)
    assert names == sorted(names, key=lambda n: float(n.split()[1].rstrip("%")))
    assert names == ["Above 3.25%", "Above 3.50%", "Above 3.75%", "Above 4.25%", "Above 4.50%"]


#: Kalshi 108626 *Fed funds rate after Jan 2027 meeting?*, all 25 rungs as stored,
#: read via ``db-query`` 2026-09-26 17:5xZ. Four rungs are unquoted (no price, no
#: book), and Above 5.25% is quoted at 13% on a 1c/97c book.
JAN_2027_LEGS = [
    (2_000 + i, f"Above {t:.2f}%", f"KXFED-27JAN-T{t:.2f}", p, b, a)
    for i, (t, p, b, a) in enumerate([
        (0.00, 0.98, 0.97, 0.99), (0.25, 0.96, 0.94, 0.98), (0.50, 0.975, 0.97, 0.98),
        (0.75, 0.975, 0.97, 0.98), (1.00, 0.97, 0.96, 0.98), (1.25, 0.96, 0.94, 0.98),
        (1.50, 0.95, 0.93, 0.97), (1.75, 0.95, 0.93, 0.97), (2.00, 0.925, 0.89, 0.96),
        (2.25, 0.955, 0.92, 0.99), (2.50, 0.94, 0.92, 0.96), (2.75, 0.935, 0.90, 0.97),
        (3.00, 0.94, 0.91, 0.97), (3.25, 0.92, 0.88, 0.96), (3.50, 0.925, 0.86, 0.99),
        (3.75, 0.85, 0.78, 0.92), (4.00, 0.835, 0.75, 0.92), (4.25, 0.64, 0.56, 0.72),
        (4.50, None, None, None), (4.75, None, None, None), (5.00, None, None, None),
        (5.25, 0.13, 0.01, 0.97), (5.50, None, None, None), (5.75, None, None, None),
        (6.00, 0.155, 0.01, 0.30),
    ])
]


def test_unquoted_rungs_do_not_push_the_answer_off_the_card():
    """🔴 THE REPAIR, on production's own rows. The first window kept unquoted
    rungs in their slots and served `4.50 — · 4.75 — · 5.00 — · 5.25 13% · 5.50 —`:
    one number and no rung above even. Over priced rungs it shows both sides."""
    market = _market(JAN_2027_LEGS, name="Fed funds rate after Jan 2027 meeting?")
    out = _build_search_top_outcomes(market)
    assert _names(out) == [
        "Above 3.75%", "Above 4.00%", "Above 4.25%", "Above 5.25%", "Above 6.00%",
    ]
    assert all(o["probability"] is not None for o in out)


def test_the_typeahead_row_of_the_same_ladder_straddles_even():
    market = _market(JAN_2027_LEGS, name="Fed funds rate after Jan 2027 meeting?")
    out = _build_search_top_outcomes(market, limit=3, lean=True)
    assert _names(out) == ["Above 4.25%", "Above 5.25%", "Above 6.00%"]
    assert _printed_pair(out) == [("Above 4.25%", 0.64), ("Above 5.25%", 0.13)]


#: `Fed funds rate after Dec 2026 meeting?` (Kalshi 109658), all 11 rungs as
#: stored, row order as stored (ux's read; Above 4.25% re-read 2026-09-26 18:55Z
#: at 0.495 on a 0.49/0.50 book).
DEC_2026_LEGS = [
    (1600178, "Above 2.75%", "KXFED-26DEC-T2.75", 0.985, 0.98, 0.99),
    (1600179, "Above 3.00%", "KXFED-26DEC-T3.00", 0.99, 0.98, 1.0),
    (1600180, "Above 3.25%", "KXFED-26DEC-T3.25", 0.985, 0.98, 0.99),
    (1600181, "Above 3.50%", "KXFED-26DEC-T3.50", 0.975, 0.97, 0.98),
    (1600182, "Above 3.75%", "KXFED-26DEC-T3.75", 0.975, 0.97, 0.98),
    (1600183, "Above 4.00%", "KXFED-26DEC-T4.00", 0.9, 0.89, 0.91),
    (1600184, "Above 5.00%", "KXFED-26DEC-T5.00", 0.02, 0.0, 0.02),
    (1600185, "Above 4.75%", "KXFED-26DEC-T4.75", 0.02, 0.0, 0.02),
    (1600186, "Above 5.25%", "KXFED-26DEC-T5.25", 0.01, 0.0, 0.01),
    (1600187, "Above 4.25%", "KXFED-26DEC-T4.25", 0.495, 0.49, 0.5),
    (1600188, "Above 4.50%", "KXFED-26DEC-T4.50", 0.06, 0.03, 0.09),
]


def test_the_dec_2026_typeahead_prints_its_answer():
    """🔴 ux's finding on #8882, live at 390px: the dropdown printed `Above 3.75%
    98% · Above 4.00% 90%` and never Above 4.25% at 49.5%, the rung the rate is
    betting on — it was the window's third row, which the dropdown does not print."""
    market = _market(DEC_2026_LEGS, name="Fed funds rate after Dec 2026 meeting?")
    out = _build_search_top_outcomes(market, limit=3, lean=True)
    assert _printed_pair(out) == [("Above 4.00%", 0.9), ("Above 4.25%", 0.495)]
    # The card (limit 5) keeps its ceil(5/2) lead.
    card = _build_search_top_outcomes(market)
    assert _names(card) == [
        "Above 3.50%", "Above 3.75%", "Above 4.00%", "Above 4.25%", "Above 4.50%",
    ]


def test_control_an_exclusive_field_keeps_its_probability_order():
    # `What will the Fed rate be at the end of 2026?` (114367) — bands, not rungs.
    legs = [
        (11, "3.5%", "0xa", 0.012, 0.01, 0.014),
        (12, "4.25%", "0xb", 0.4705, 0.46, 0.48),
        (13, "3.75%", "0xc", 0.0305, 0.03, 0.031),
        (14, "≥ 4.5%", "0xd", 0.4315, 0.43, 0.433),
        (15, "4.0%", "0xe", 0.0835, 0.08, 0.087),
    ]
    out = _build_search_top_outcomes(
        _market(legs, name="What will the Fed rate be at the end of 2026?",
                mutually_exclusive=True)
    )
    assert _names(out) == ["4.25%", "≥ 4.5%", "4.0%", "3.75%", "3.5%"]


def test_control_a_mixed_direction_board_keeps_its_probability_order():
    # `What will Fed Rate hit before 2027` (113427): ↑ and ↓ are two ladders on
    # one board, so it is not ONE ladder and the window must not fire.
    legs = [
        (21, "↓ 3.25%", "0xf", 0.032, 0.016, 0.048),
        (22, "↑ 4.5%", "0x10", 0.457, 0.395, 0.519),
        (23, "↑ 4.25%", "0x11", 0.9025, 0.9, 0.905),
        (24, "↑ 4.75%", "0x12", 0.1095, 0.035, 0.184),
    ]
    out = _build_search_top_outcomes(
        _market(legs, name="What will Fed Rate hit before 2027")
    )
    assert _names(out) == ["↑ 4.25%", "↑ 4.5%", "↑ 4.75%", "↓ 3.25%"]

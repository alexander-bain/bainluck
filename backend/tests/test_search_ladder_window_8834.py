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


def test_the_typeahead_draws_the_crossing_and_its_two_neighbours():
    # #993: the dropdown and the card are one pair — both must move.
    out = _build_search_top_outcomes(_market(), limit=3, lean=True)
    assert _names(out) == ["Above 3.75%", "Above 4.00%", "Above 4.25%"]


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


def test_a_withheld_rung_cannot_be_the_centre_but_keeps_its_slot():
    out = _build_search_top_outcomes(_market(), withheld={CROSSING_ID})
    ids = [o["id"] for o in out]
    assert CROSSING_ID in ids, "a refused price keeps its threshold slot as a dash"
    assert next(o for o in out if o["id"] == CROSSING_ID)["probability"] is None
    names = _names(out)
    assert names == sorted(names, key=lambda n: float(n.split()[1].rstrip("%")))


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

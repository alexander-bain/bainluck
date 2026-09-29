"""#9676 — a search ladder card never draws a rung its own ladder contradicts.

WHAT A READER SAW, production 2026-09-29 19:10Z, ``/search?q=fed rate`` at 390px::

    Fed funds rate after Jan 2027 meeting?
      Above 4.00% 92% · Above 4.25% 73% · Above 4.50% 28% · Above 4.75% 76% · Above 5.00% 6%

``Above 4.75%`` is a strict subset of ``Above 4.50%``, so 76% over 28% cannot be
true. Both rungs are untraded (8¢/76¢ and 2¢/78¢ books). The feed has stripped
such a rung since #4610 via ``drop_incoherent_ladder_outcomes``; the search
ladder window (#8834) never called it.

THE FIXTURE IS THE SPECIMEN'S STORED ROWS (Kalshi 108626, all 25 legs, read via
``db-query`` 2026-09-29 ~19:15Z), so the builder's own pre-sort refusals run on
the real bids and asks before the window does.

THE CONTROLS: #8834's own specimen (109947) carries a tolerated one-tick
inversion and its tests stay green unchanged; a ladder where every rung
contradicts every other is not trimmed (never-collapse, CERT-2451). #8834's
9/26 read of this same market pinned ``Above 5.25% 13% · Above 6.00% 16%`` —
the same impossible shape — and those two assertions move with this fix.
"""

from types import SimpleNamespace

from app.routes.events import _build_search_top_outcomes

#: ``(id, name, external_id, prob, bid, ask, is_winner, resolution_source)`` — 108626 verbatim.
_OLD = (False, "ungradeable_result")
_NEW = (None, None)
SPECIMEN_LEGS = [
    (1594009, "Above 0.00%", "KXFED-27JAN-T0.00", 0.98, 0.97, 0.99, *_OLD),
    (1594008, "Above 0.25%", "KXFED-27JAN-T0.25", 0.955, 0.93, 0.98, *_OLD),
    (1594010, "Above 0.50%", "KXFED-27JAN-T0.50", 0.975, 0.97, 0.98, *_OLD),
    (1594007, "Above 0.75%", "KXFED-27JAN-T0.75", 0.975, 0.97, 0.98, *_OLD),
    (1594011, "Above 1.00%", "KXFED-27JAN-T1.00", 0.97, 0.96, 0.98, *_OLD),
    (1594012, "Above 1.25%", "KXFED-27JAN-T1.25", 0.965, 0.95, 0.98, *_OLD),
    (1594013, "Above 1.50%", "KXFED-27JAN-T1.50", 0.95, 0.93, 0.97, *_OLD),
    (1594014, "Above 1.75%", "KXFED-27JAN-T1.75", 0.96, 0.94, 0.98, *_OLD),
    (1594015, "Above 2.00%", "KXFED-27JAN-T2.00", 0.955, 0.94, 0.97, *_OLD),
    (1594016, "Above 2.25%", "KXFED-27JAN-T2.25", 0.95, 0.93, 0.97, *_OLD),
    (1594017, "Above 2.50%", "KXFED-27JAN-T2.50", 0.945, 0.92, 0.97, *_OLD),
    (1594018, "Above 2.75%", "KXFED-27JAN-T2.75", 0.945, 0.92, 0.97, *_OLD),
    (1594019, "Above 3.00%", "KXFED-27JAN-T3.00", 0.95, 0.93, 0.97, *_OLD),
    (1594020, "Above 3.25%", "KXFED-27JAN-T3.25", 0.945, 0.92, 0.97, *_OLD),
    (1594021, "Above 3.50%", "KXFED-27JAN-T3.50", 0.945, 0.92, 0.97, *_OLD),
    (1594022, "Above 3.75%", "KXFED-27JAN-T3.75", 0.95, 0.92, 0.98, *_OLD),
    (1594023, "Above 4.00%", "KXFED-27JAN-T4.00", 0.915, 0.86, 0.97, *_OLD),
    (1594024, "Above 4.25%", "KXFED-27JAN-T4.25", 0.73, 0.72, 0.74, *_OLD),
    (235954948, "Above 4.50%", "KXFED-27JAN-T4.50", 0.28, 0.08, 0.76, *_NEW),
    (235954949, "Above 4.75%", "KXFED-27JAN-T4.75", 0.76, 0.02, 0.78, *_NEW),
    (235954950, "Above 5.00%", "KXFED-27JAN-T5.00", 0.055, 0.01, 0.10, *_NEW),
    (235954947, "Above 5.25%", "KXFED-27JAN-T5.25", 0.255, 0.01, 0.50, *_NEW),
    (235954951, "Above 5.50%", "KXFED-27JAN-T5.50", 0.255, 0.01, 0.50, *_NEW),
    (235954952, "Above 5.75%", "KXFED-27JAN-T5.75", 0.255, 0.01, 0.50, *_NEW),
    (235954946, "Above 6.00%", "KXFED-27JAN-T6.00", 0.155, 0.01, 0.30, *_NEW),
]

IMPOSSIBLE_ID = 235954949  # Above 4.75% at 76%, over Above 4.50% at 28%


def _leg(oid, name, ext, prob, bid, ask, is_winner, resolution_source):
    return SimpleNamespace(
        id=oid,
        name=name,
        external_id=ext,
        current_probability=prob,
        current_american_odds=None,
        rank=None,
        probability_change_24h=None,
        is_winner=is_winner,
        resolution_source=resolution_source,
        current_yes_bid=bid,
        current_yes_ask=ask,
        price_changed_at=None,
        last_updated=None,
    )


def _market(legs=SPECIMEN_LEGS, *, name="Fed funds rate after Jan 2027 meeting?"):
    return SimpleNamespace(
        id=108626,
        name=name,
        source="kalshi",
        status="open",
        mutually_exclusive=False,
        outcomes=[_leg(*row) for row in legs],
    )


def _priced(out):
    return [(o["name"], o["probability"]) for o in out if o["probability"] is not None]


def _assert_nested(pairs):
    """A falling "Above X" ladder in threshold order never rises."""
    probs = [p for _, p in pairs]
    assert probs == sorted(probs, reverse=True), pairs


def test_the_card_does_not_draw_the_impossible_rung():
    out = _build_search_top_outcomes(_market())
    assert IMPOSSIBLE_ID not in {o["id"] for o in out}
    # The answer straddle survives at raw prices — the rung under even is the
    # 4.50% the reader was shown, not something the drop invented.
    assert ("Above 4.25%", 0.73) in _priced(out)
    assert ("Above 4.50%", 0.28) in _priced(out)
    _assert_nested(_priced(out))


def test_the_dropdown_pair_is_drawn_from_the_same_coherent_ladder():
    # #993: card and dropdown are one pair — the lean window reads the same
    # rungs, so it must not reach for the dropped one either.
    out = _build_search_top_outcomes(_market(), limit=3, lean=True)
    # Lean rows carry no id; the name is unique on this ladder.
    assert "Above 4.75%" not in {o["name"] for o in out}
    _assert_nested(_priced(out))


def test_a_short_ladder_that_fits_the_card_is_trimmed_too():
    # The `len(ordered) <= limit` early return sits AFTER the drop: a ladder
    # that fits whole must not bring its impossible rung along.
    legs = [row for row in SPECIMEN_LEGS if row[1] in {
        "Above 4.00%", "Above 4.25%", "Above 4.50%", "Above 4.75%", "Above 5.00%",
    }]
    out = _build_search_top_outcomes(_market(legs))
    assert IMPOSSIBLE_ID not in {o["id"] for o in out}
    _assert_nested(_priced(out))


def test_a_ladder_every_rung_of_which_contradicts_another_is_not_trimmed():
    # CERT-2451's never-collapse rule, inherited from the shared helper: when
    # the coherent run would leave one rung, "which rung is wrong" has no answer,
    # so nothing is dropped and the ladder is drawn as served.
    # The grader's specimen: the coherent run is `Above 10` alone.
    legs = [
        (1, "Above 10", "T10", 0.20, 0.19, 0.21, *_NEW),
        (2, "Above 20", "T20", 0.90, 0.89, 0.91, *_NEW),
        (3, "Above 30", "T30", 0.95, 0.94, 0.96, *_NEW),
    ]
    out = _build_search_top_outcomes(_market(legs, name="Widgets sold?"))
    assert {o["id"] for o in out} == {1, 2, 3}


def test_a_withheld_price_cannot_condemn_a_rung_the_card_prints():
    # #6993's withheld rungs are refused prices: the card draws no number for
    # them, so they must not vote on which printed rung is impossible. Counted,
    # the two withheld 85%/84% rungs out-vote the printed 50% and it is dropped;
    # read as unpriced, 90% / 50% / 40% is coherent and nothing moves.
    legs = [
        (1, "Above 1%", "T1", 0.90, 0.89, 0.91, *_NEW),
        (2, "Above 2%", "T2", 0.50, 0.49, 0.51, *_NEW),
        (3, "Above 3%", "T3", 0.85, 0.84, 0.86, *_NEW),
        (4, "Above 4%", "T4", 0.84, 0.83, 0.85, *_NEW),
        (5, "Above 5%", "T5", 0.40, 0.39, 0.41, *_NEW),
    ]
    out = _build_search_top_outcomes(_market(legs, name="Rate above?"), withheld={3, 4})
    assert ("Above 2%", 0.5) in _priced(out)

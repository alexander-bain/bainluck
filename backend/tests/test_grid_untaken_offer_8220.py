"""#8220 — a bracket cell stops quoting an untaken offer as a probability.

## what a reader saw

``/playoffs/ncaa-basketball`` at 390px. **South Dakota St Jackrabbits read 13%
to reach the Title Game and <0.1% to win it** — a factor of 260 on one row, two
columns that are one sideways swipe apart. A team that reaches the final wins it
about half the time.

The page supplies its own control. Florida (19.5% → 9.53%) and Duke (20.5% →
8.81%) land where a coin-flip final puts them, ratios 2.0 and 2.3; the median
ratio over the 43 priced rows is 7.0 and **eight rows exceed 50**. The two rows
that are right are the two with real two-sided books.

The served number IS the ask to the cent. ``KXMARMADROUND-27T2-SDST`` stores
``yes_bid 0.0000 / yes_ask 0.1500 / last_price 0.0000 / volume 0 / open interest
0``, untouched since 2026-04-28, and we published 0.15 as a probability.

## the number that says it is a distribution defect and not a rounding one

A bracket column is summed. Measured on production 2026-09-23, the served
columns against their seat counts:

===============  =====  ========  =========
column           seats  sum NOW   sum AFTER
===============  =====  ========  =========
round_of_32         32     20.88      20.04
sweet_16            16     13.21      11.31
elite_eight          8      7.21       5.58
final_four           4      5.35       3.03
title_game           2      4.58       2.08
===============  =====  ========  =========

**The Title Game column offered 4.58 probability for 2 places.** Withholding the
untaken offers takes it to 2.08. The shallow columns barely move (20.88 → 20.04)
because those books are real — the rule fires where the defect is, which is the
control the shape of this table provides for free.

## why the frame is declared by the grid

``futures_unsupported_price.market_is_proved_exclusive_field`` refuses all five
of these markets, and **not** because its winner-count term reads ``== "1"``
where a bracket has 2 or 4 — that was the mechanism #8220 was filed with, and it
is wrong. All five store ``exhaustive: None / expected_winners: None /
outcome_relation: 'unknown'`` at ``confidence: 'low'``: the shape classifier
declined them outright, so the frame fails three clauses and there is no winner
count recorded at all. Widening that term would have shipped nothing.

The proof exists in ``routes/playoffs`` instead, because this module BUILT the
column. That is the whole of what :func:`_grid_cell_quotes_an_untaken_offer`
adds; the book judgement is delegated to ``needs_trade_evidence``.

## what this file cannot see, and which file does

Every assertion here is a unit call. A mutant that deletes the CALL SITE in
``get_playoff_grid`` leaves all of it green — that is
``tests/integration/test_grid_untaken_offer_8220_pg.py``'s job, which drives the
real route against real PostgreSQL and reads the served payload.
"""

import pytest

from app.routes.playoffs import (
    _ADVANCEMENT_COLUMNS,
    _grid_cell_quotes_an_untaken_offer,
)


#: ``(label, col_key, source, resolution_source, bid, ask, refused)``.
#:
#: Every control below fails EXACTLY ONE clause of the decision, so a mutant that
#: drops that clause is isolated by the row named for it. The specimen and the
#: two-sided control are the real stored books of the two teams named in the
#: issue.
_CASES = (
    # 🔴 THE SPECIMEN. South Dakota St's Title Game book: nobody bidding, one
    # untaken offer at 15c, no trade in five months. We served 0.13.
    ("specimen: SDST, zero bid, lone ask", "title_game", "kalshi", None, 0.0, 0.15, True),
    # CONTROL, fails the BOOK clause alone: Duke's real two-sided book. This is
    # the row whose ratio was already right, and it must keep its number.
    ("control: Duke, two-sided book", "title_game", "kalshi", None, 0.11, 0.29, False),
    # CONTROL, fails the FRAME clause alone: identical book, but `championship`
    # is not an advancement column. Excluded deliberately — every one of its 68
    # cells carries a non-Kalshi source, so withholding one contributor is a
    # BLENDING change (reviewed class), not this ship.
    ("control: championship is blended", "championship", "kalshi", None, 0.0, 0.15, False),
    # CONTROL, fails the FRAME clause alone, other direction: a settled-season
    # column, never a fixed-size advancement partition.
    ("control: make_playoffs column", "make_playoffs", "kalshi", None, 0.0, 0.15, False),
    # CONTROL, fails the VENUE clause alone: this policy is Kalshi's. A
    # Polymarket leg with the same numbers is a different book model.
    ("control: polymarket source", "title_game", "polymarket", None, 0.0, 0.15, False),
    # CONTROL, fails the VERDICT clause alone (#7387/#6876): the venue graded it.
    # A settlement value is a RESULT, and withholding it would delete an answer —
    # the harm the graded exemption exists to prevent.
    ("control: graded leg keeps its result", "title_game", "kalshi", "api_settlement", 0.0, 0.15, False),
    # 🔴 NOT A CONTROL — THE OPPOSITE. #6876 narrows "graded" to "carries a
    # verdict", and `ungradeable_result` RETRACTS one: it asserts no winner, so
    # the number beside it is still a quote and is still refused. A mutant that
    # treats any non-null `resolution_source` as a verdict is caught here and
    # nowhere else in this file.
    ("retraction is not a verdict", "title_game", "kalshi", "ungradeable_result", 0.0, 0.15, True),
    # CONTROL, fails the BOOK clause alone: a MISSING bid is not a zero bid. None
    # means the poller never recorded a book (the candle rails store none), and
    # this rule must not claim to know anything about those rows.
    ("control: bid absent, not zero", "title_game", "kalshi", None, None, 0.15, False),
    # CONTROL, fails the BOOK clause alone: no bid AND no offer is not an
    # untaken offer, it is an empty book with nothing to refuse.
    ("control: no offer at all", "title_game", "kalshi", None, 0.0, 0.0, False),
    # CONTROL, fails the BOOK clause alone: a bid of one cent is somebody paying
    # something, which is the evidence the whole rule turns on.
    ("control: a one-cent bid is a bid", "title_game", "kalshi", None, 0.01, 0.15, False),
)


@pytest.mark.parametrize(
    "label,col_key,source,resolution_source,bid,ask,refused",
    [c for c in _CASES],
    ids=[c[0] for c in _CASES],
)
def test_untaken_offer_is_refused_only_inside_a_bracket_column(
    label, col_key, source, resolution_source, bid, ask, refused
):
    assert (
        _grid_cell_quotes_an_untaken_offer(col_key, source, resolution_source, bid, ask)
        is refused
    ), label


def test_every_advancement_column_refuses_the_specimen_book():
    """The frame is the SET, not the one column the defect was found in.

    Pinning membership one column at a time would pass on a mutant that kept
    `title_game` and dropped the other four — which is 48 of the 74 withheld
    cells, and the whole of the `final_four` overcount (5.35 for 4 places).
    """
    for col in sorted(_ADVANCEMENT_COLUMNS):
        assert (
            _grid_cell_quotes_an_untaken_offer(col, "kalshi", None, 0.0, 0.15) is True
        ), col


def test_the_frame_set_is_exactly_the_five_measured_bracket_columns():
    """Both directions, because each one catches a different mistake.

    A missing member serves fabricated cells in that column. An EXTRA member
    blanks cells on a grid nobody walked — `semifinal`, `quarterfinal`, `final`,
    `top_4/5/10/20`, `relegation` and `pennant` are the same frame and are
    excluded on purpose: their populations are unmeasured. Widening this set is
    a deliberate act that owes its own census, so it must redden a test.
    """
    assert _ADVANCEMENT_COLUMNS == frozenset(
        {"round_of_32", "sweet_16", "elite_eight", "final_four", "title_game"}
    )


def test_championship_is_not_in_the_frame_even_though_it_is_single_winner():
    """The one exclusion a reader of the rule would most expect to be included.

    `championship` IS a single-winner field — the frame argument plainly applies
    — and it is still out, because its cells are blended: 38 of 68 carry Kalshi
    beside odds_api and none is Kalshi-only. 17 of its 73 Kalshi legs are
    ask-only, so this is a real contamination that is deliberately NOT repaired
    here. Recorded so a later widening is a decision and not a tidy-up.
    """
    assert "championship" not in _ADVANCEMENT_COLUMNS
    assert (
        _grid_cell_quotes_an_untaken_offer("championship", "kalshi", None, 0.0, 0.15)
        is False
    )


def test_the_book_judgement_is_delegated_and_not_restated():
    """#8220 must not grow a second copy of the ask-only rule.

    If this module ever reimplements the shape instead of calling
    `needs_trade_evidence`, the two can drift and the grid starts refusing rows
    the futures ladder serves for a reason nobody wrote down. Asserted by
    patching the shared rule and requiring the helper to follow it.
    """
    import app.routes.playoffs as mod

    calls = []

    def _fake(source, resolution_source, bid, ask, *, in_exclusive_field=False):
        calls.append((source, resolution_source, bid, ask, in_exclusive_field))
        return False

    real = mod.needs_trade_evidence
    mod.needs_trade_evidence = _fake
    try:
        # The specimen, which the REAL rule refuses. If the helper restated the
        # shape locally it would still return True and ignore the stub.
        assert (
            _grid_cell_quotes_an_untaken_offer("title_game", "kalshi", None, 0.0, 0.15)
            is False
        )
    finally:
        mod.needs_trade_evidence = real

    assert calls == [("kalshi", None, 0.0, 0.15, True)], calls
    # And the frame flag is not merely passed — it is passed TRUE. A mutant that
    # forwards `in_exclusive_field=False` reaches `is_lone_ask_on_empty_book`,
    # whose 0.50 bound serves every one of these 11c-28c asks.
    assert calls[0][4] is True

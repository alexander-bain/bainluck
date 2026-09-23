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
    _grid_untaken_offer_candidates,
)


def _refused(col_key, source, resolution_source, bid, ask,
             last_price=0.0, *, has_trade_evidence=True):
    """The predicate asked the way #8220's fail-closed call site asked it.

    #8243 gave the helper a real trade term, so every pre-existing case here has
    to say what the trade read found. ``last_price=0.0`` with
    ``has_trade_evidence=True`` — "we looked, and this market has never traded" —
    is EXACTLY what the old `needs_trade_evidence` call assumed of every leg, so
    defaulting to it keeps all of #8220's cases asserting what they asserted
    before, and the new behaviour is pinned by the #8243 block at the end of this
    file rather than by quietly reinterpreting these rows.
    """
    return _grid_cell_quotes_an_untaken_offer(
        col_key, source, resolution_source, bid, ask, last_price,
        has_trade_evidence=has_trade_evidence,
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
        _refused(col_key, source, resolution_source, bid, ask) is refused
    ), label


def test_every_advancement_column_refuses_the_specimen_book():
    """The frame is the SET, not the one column the defect was found in.

    Pinning membership one column at a time would pass on a mutant that kept
    `title_game` and dropped the other four — which is 48 of the 74 withheld
    cells, and the whole of the `final_four` overcount (5.35 for 4 places).
    """
    for col in sorted(_ADVANCEMENT_COLUMNS):
        assert (
            _refused(col, "kalshi", None, 0.0, 0.15) is True
        ), col


def test_the_frame_set_is_exactly_the_measured_columns():
    """Both directions, because each one catches a different mistake.

    A missing member serves fabricated cells in that column. An EXTRA member
    withholds cells on a grid nobody measured — see `_MEASURED_EXCLUSIONS`.

    #8243 added `relegation` and `quarterfinal`. They are NOT here because the
    frame argument reaches them — it always did, and reaching is not the test.
    They are here because each passed three production gates on 2026-09-23:
    every cell the rule withholds is backed by exactly ONE outcome (so the cell
    CLEARS instead of moving a mean, which would be the reviewed blending class),
    no affected team loses its last populated cell, and the batched trade read
    spares the legs that have traded.
    """
    assert _ADVANCEMENT_COLUMNS == frozenset(
        {
            "round_of_32", "sweet_16", "elite_eight", "final_four", "title_game",
            "relegation", "quarterfinal",
            # #8257: admitted on the same gates once #8251 made its cells
            # accountable. See the route's `_ADVANCEMENT_COLUMNS` note.
            "semifinal",
        }
    )


#: Every fixed-size column that shares this frame and is STILL excluded, with the
#: production measurement (2026-09-23, #8243) that excludes it.
#:
#: The trade term is no longer the reason — the batched read answers it. What is
#: left is columns where the withholding would reach nobody. (`semifinal` sat here
#: until #8251 accounted for its served numbers; #8257 admitted it.)
_MEASURED_EXCLUSIONS = (
    ("conference", "nba/nfl/nhl/mls — 0 legs survive the trade read; every "
                   "ask-only leg in all four grids has traded"),
    ("pennant", "mlb — 0 legs survive the trade read"),
    ("top_4", "epl 0 + la-liga 2, and both la-liga legs name teams with no grid "
              "row, so 0 cells reach a reader"),
)


@pytest.mark.parametrize(
    "col,note", _MEASURED_EXCLUSIONS, ids=[c[0] for c in _MEASURED_EXCLUSIONS],
)
def test_a_same_frame_column_that_the_measurement_still_excludes(col, note):
    """The exclusions that a reader of the frame argument would expect to be IN.

    These columns really are the same frame — fixed-size, summed, and an ask-only
    book really does state an upper bound inside them. Reaching them with the
    argument is not the test; measuring them is.

    Asserted through the FUNCTION, not just the constant, so a mutant that adds a
    key to `_ADVANCEMENT_COLUMNS` is killed by the behaviour and reads the reason
    in the failure message rather than a bare set mismatch.
    """
    assert col not in _ADVANCEMENT_COLUMNS, (
        f"`{col}` was added to the frame, but on 2026-09-23 it was measured and "
        f"excluded — {note}. Re-measure before widening; the rig is "
        f"artifacts-authority-994/widen_reader_gate.py."
    )
    # the specimen book from the men's bracket, asked in this column's frame
    assert _refused(col, "kalshi", None, 0.0, 0.15) is False, col


def test_the_measured_exclusions_are_a_strict_superset_of_nothing_shipped():
    """Control for the table above: it must not quietly name a SHIPPED column.

    Without this, a careless edit could list `title_game` as excluded-and-traded
    and the parametrized test would fail for the right-looking wrong reason —
    or, worse, someone could satisfy it by narrowing the shipped set.
    """
    named = {c[0] for c in _MEASURED_EXCLUSIONS}
    assert named.isdisjoint(_ADVANCEMENT_COLUMNS)
    assert len(named) == len(_MEASURED_EXCLUSIONS), "duplicate column in the table"


def test_championship_is_not_in_the_frame_even_though_it_is_single_winner():
    """The one exclusion a reader of the rule would most expect to be included.

    `championship` IS a single-winner field — the frame argument plainly applies
    — and it is still out for two independent reasons.

    BLENDING: all 68 of its cells carry a non-Kalshi source and none is
    Kalshi-only, so withholding one contributor is a blending change (reviewed
    class under 49(d)), not this ship.

    AND IT NEEDS NOTHING ANYWAY, which corrects what this docstring used to
    claim. "17 of its 73 Kalshi legs are ask-only" is true and was read as a
    contamination waiting to be repaired. It is not: re-measured 2026-09-23
    (#8243), all 17 name teams with NO row on the grid — the grid renders last
    March's 68-team field — and every one of them asks 0.001, the venue floor.
    Zero reach a reader; the served column sums to 0.8175 for its one seat. The
    17 was a count of the STORED population, which is a property of the filter
    that counted it, not of what anyone sees.
    """
    assert "championship" not in _ADVANCEMENT_COLUMNS
    assert (
        _refused("championship", "kalshi", None, 0.0, 0.15) is False
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

    def _fake(source, resolution_source, bid, ask, last_price, *,
              has_trade_evidence, in_exclusive_field=False):
        calls.append((source, resolution_source, bid, ask, last_price,
                      has_trade_evidence, in_exclusive_field))
        return False

    real = mod.price_is_unsupported
    mod.price_is_unsupported = _fake
    try:
        # The specimen, which the REAL rule refuses. If the helper restated the
        # shape locally it would still return True and ignore the stub.
        assert _refused("title_game", "kalshi", None, 0.0, 0.15) is False
    finally:
        mod.price_is_unsupported = real

    assert calls == [("kalshi", None, 0.0, 0.15, 0.0, True, True)], calls
    # And the frame flag is not merely passed — it is passed TRUE. A mutant that
    # forwards `in_exclusive_field=False` reaches `is_lone_ask_on_empty_book`,
    # whose 0.50 bound serves every one of these 11c-28c asks.
    assert calls[0][6] is True
    # #8243: the trade term is FORWARDED, not swallowed. A mutant that hardcodes
    # `has_trade_evidence=True` (restoring the fail-closed behaviour while still
    # calling the new predicate) passes every other assertion in this file.
    calls.clear()
    mod.price_is_unsupported = _fake
    try:
        _refused("title_game", "kalshi", None, 0.0, 0.15, 0.19,
                 has_trade_evidence=False)
    finally:
        mod.price_is_unsupported = real
    assert calls[0][4] == 0.19, calls
    assert calls[0][5] is False, calls


# ═══════════════════════════════════════════════════════════════════════════
# #8243 — THE BATCHED TRADE READ. The rule above stops failing closed.
# ═══════════════════════════════════════════════════════════════════════════
#
# `needs_trade_evidence` withheld an ask-only book WITHOUT reading trades,
# because a per-outcome snapshot read in the grid loop is LAT-P132's 24,465 ms.
# `_newest_kalshi_trades` answers the whole grid in one statement above the loop,
# so the grid now asks `price_is_unsupported` — the same predicate AND the trade
# term. Measured on production 2026-09-23 over the two columns this admits:
# la-liga `relegation` 13 withheld → 3, champions-league `quarterfinal` 3 → 2.
# The 11 legs spared all carry a real trade (Real Sociedad asks 0.49 having last
# traded at 0.99).


#: ``(label, last_price, has_trade_evidence, refused)`` against the SPECIMEN book
#: (`bid 0.00 / ask 0.15`, `title_game`), which #8220 withholds unconditionally.
#: Every row differs from its neighbours in exactly one of the two trade inputs.
_TRADE_CASES = (
    # 🔴 THE #8243 SPECIMEN, and the row that would have been a regression. La
    # Liga's Real Sociedad asks 0.49 having last traded at 0.99: no resting bid at
    # capture, but a market that transacts. The fail-closed rule deleted it.
    ("a leg that has traded keeps its number", 0.99, True, False),
    # The trade need only be non-zero — `is_lone_ask_in_exclusive_field` asks
    # whether a trade exists, not whether it agrees with the ask. Fenerbahce asks
    # 0.59 having traded at 0.59; Barcelona asks 0.07 having traded at 0.01.
    ("a trade far below the ask is still a trade", 0.01, True, False),
    # 🔴 THE ROW THE SHIP STILL WITHHOLDS. "We looked, and this market has never
    # traded" — Athletic Bilbao, 0.48 relegation odds off a book with no bid and
    # no trade. This is the ONLY combination that withholds.
    ("looked, and it has never traded", 0.0, True, True),
    # 🔴 GOTCHA #53, AND THE ONE THAT FAILS OPEN. An absent snapshot is "we never
    # looked", not "it never traded". A mutant that collapses the two — e.g.
    # `has_trade_evidence=bool(last_price)` or passing 0.0 for a missing row —
    # is caught HERE and by nothing else: it would blank every leg on a grid the
    # snapshot table has no rows for.
    ("never looked: fails OPEN", None, False, False),
    # Same, with a stale non-null price attached to an absent read. The evidence
    # flag governs, not the number beside it.
    ("absent read outranks a price", 0.99, False, False),
)


@pytest.mark.parametrize(
    "label,last_price,has_trade,refused",
    _TRADE_CASES,
    ids=[c[0] for c in _TRADE_CASES],
)
def test_the_trade_read_decides_a_leg_the_old_rule_refused_blind(
    label, last_price, has_trade, refused
):
    assert (
        _refused("title_game", "kalshi", None, 0.0, 0.15, last_price,
                 has_trade_evidence=has_trade)
        is refused
    ), label


def test_the_swap_is_monotone_and_can_only_withhold_fewer_legs():
    """#8243 may not withhold a cell #8220 served. Asserted, not asserted-about.

    `price_is_unsupported` is `needs_trade_evidence` AND the trade term, so this
    is a property of the composition rather than of any one case — but a mutant
    that reorders the terms, or that treats "no trade evidence" as a reason to
    withhold, breaks it while leaving every single-case assertion above green.

    Swept over the cross product of both book shapes and both trade answers, in
    every frame column, so no column can be quietly given a different rule.
    """
    books = ((0.0, 0.15), (0.0, 0.48), (0.11, 0.29), (None, 0.15), (0.0, 0.0))
    trades = ((0.0, True), (0.99, True), (None, False), (0.01, True))
    for col in sorted(_ADVANCEMENT_COLUMNS):
        for bid, ask in books:
            old = _refused(col, "kalshi", None, bid, ask)  # the #8220 rule
            for last_price, has_trade in trades:
                new = _refused(col, "kalshi", None, bid, ask, last_price,
                               has_trade_evidence=has_trade)
                assert not (new and not old), (
                    f"{col} bid={bid} ask={ask} last={last_price} "
                    f"has_trade={has_trade}: #8243 withholds a cell #8220 served"
                )


def test_the_screen_never_misses_a_leg_the_verdict_would_withhold():
    """The batched read is only issued for legs `_grid_untaken_offer_candidates`
    survives, so a leg the screen drops can NEVER be withheld — it is absent from
    the dict and fails open.

    That makes the screen load-bearing in a way no assertion on the verdict can
    see: if it is ever narrowed below the verdict, cells silently start serving
    again and every test above still passes. Swept over the same cross product.
    """
    for col in sorted(_ADVANCEMENT_COLUMNS) + ["championship", "make_playoffs"]:
        for source in ("kalshi", "polymarket"):
            for resolution in (None, "api_settlement", "ungradeable_result"):
                for bid, ask in ((0.0, 0.15), (0.11, 0.29), (None, 0.15), (0.0, 0.0)):
                    for last_price in (0.0, 0.99, None):
                        verdict = _refused(
                            col, source, resolution, bid, ask, last_price,
                            has_trade_evidence=last_price is not None,
                        )
                        if verdict:
                            assert _grid_untaken_offer_candidates(
                                col, source, resolution, bid, ask
                            ), (
                                f"{col}/{source}/{resolution} bid={bid} ask={ask}: "
                                "withheld by the verdict but never screened in, so "
                                "the batched read would never fetch its trade"
                            )


def test_the_screen_is_the_shared_rule_and_not_a_local_restatement():
    """A second spelling of the book shape is how the screen and the verdict drift.

    Patching the shared rule must move the screen. If it does not, the screen has
    its own copy and can narrow below the verdict without any test noticing.
    """
    import app.routes.playoffs as mod

    calls = []

    def _fake(source, resolution_source, bid, ask, *, in_exclusive_field=False):
        calls.append((source, resolution_source, bid, ask, in_exclusive_field))
        return False

    real = mod.needs_trade_evidence
    mod.needs_trade_evidence = _fake
    try:
        assert _grid_untaken_offer_candidates(
            "title_game", "kalshi", None, 0.0, 0.15
        ) is False
    finally:
        mod.needs_trade_evidence = real

    assert calls == [("kalshi", None, 0.0, 0.15, True)], calls


def test_the_screen_costs_nothing_outside_a_frame_column():
    """A grid with no advancement column must issue NO trade query at all.

    The frame test comes FIRST in the screen, so a non-frame column never reaches
    the shared rule and contributes no id. A mutant that reorders those two lines
    is inert behaviourally and expensive in production — it would put every
    Kalshi leg of every grid into the `IN` list.
    """
    import app.routes.playoffs as mod

    called = []

    def _fake(*a, **k):
        called.append(a)
        return True

    real = mod.needs_trade_evidence
    mod.needs_trade_evidence = _fake
    try:
        assert _grid_untaken_offer_candidates(
            "make_playoffs", "kalshi", None, 0.0, 0.15
        ) is False
    finally:
        mod.needs_trade_evidence = real

    assert called == [], "a non-frame column reached the shared rule"

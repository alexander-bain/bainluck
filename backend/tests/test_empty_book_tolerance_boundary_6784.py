"""The empty-book midpoint tolerance is inclusive by intent and unreachable in float (#6784).

WHAT A READER SAW. ``/api/futures/60481170`` — "ChatGPT App Downloads in September" —
served the rung **"Above 107" at 51%**, read on production 2026-09-17. The stored row
(``futures_outcomes`` 225982191, source kalshi, market status open, ungraded):

    name         current_probability   yes_bid / yes_ask   last_updated
    Above 107    0.510000              0.0100 / 0.9900     2026-09-11 20:52Z

A 0.01/0.99 quote bounds nothing, and 0.51 is one cent off its midpoint — which is
exactly ``EMPTY_BOOK_MIDPOINT_TOLERANCE``, the distance the constant declares refusable.
:func:`is_empty_book_midpoint` should have refused it and did not.

THE CAUSE IS THE COMPARE, NOT THE CONSTANT. Condition 3 reads::

    abs(float(probability) - (bid + ask) / 2) <= EMPTY_BOOK_MIDPOINT_TOLERANCE

``abs(0.51 - 0.5)`` is ``0.010000000000000009`` in binary float, not ``0.01``. So at the
one distance the ``<=`` exists to include, it is strictly greater and the row is
admitted.

AND THE ERROR RUNS BOTH WAYS, WHICH IS THE SHARPER STATEMENT. "The ``=`` is decorative"
was the first reading of this and it was too kind. Of the **72** integer-cent triples
sitting exactly one tolerance from their midpoint on a qualifying book, ``abs(p - mid)``
evaluates to ``0.009999999999999953`` for **6** and to ``0.010000000000000009`` (or
``...064``) for the other **66**. The predicate therefore refused 6 of the 72 and
admitted 66 — same distance, same policy, opposite answers, decided by binary
representation. The boundary was not unreachable; it was arbitrary.

THE REPAIR IS THE IDIOM THIS FUNCTION ALREADY OWNS, TWO LINES ABOVE — BUT NOT ITS
CONSTANT. Condition 2 quantizes for exactly this reason and says why in its own comment
("rounded so the compare does not depend on how the bound was spelled ... 4dp is exact
for these Numeric(5,4) columns"); condition 3 was left unquantized. So the technique
carries over and the precision does not: the delta is not a book value.
``current_probability`` is Numeric(7,6) against Numeric(5,4) book columns, which makes a
midpoint exact at 5 decimals and ``|price - midpoint|`` exact at 6. Reusing the book's
4dp would collapse a genuine 0.010049 onto 0.0100 and refuse it — quantization quietly
becoming the threshold move this ship promises not to make. Hence
``_MIDPOINT_DELTA_DECIMALS = 6``, and
``test_the_delta_is_quantized_at_its_own_precision_not_the_books`` pins it. No constant
moves and no threshold is widened.

WHY NO TEST CAUGHT IT, WHICH IS THE PART WORTH KEEPING. Both other thresholds are
pinned AT their boundary — ``test_both_sides_exactly_at_the_threshold_are_refused``
does it for the spread. The tolerance's own boundary test,
``test_a_price_just_inside_and_just_outside_the_tolerance``, probes ``mid + 0.005``
(inside) and ``mid + 0.05`` (outside) and never ``mid + TOLERANCE`` itself. A boundary
that is never asserted at the boundary cannot fail, so the unreachable ``=`` survived
three constant moves (#5247, #5333, #6727).

MEASURED BOTH WAYS, because a compare change is a claim about two populations:

* Over all 1,030,301 integer-cent ``(price, bid, ask)`` triples: **66 newly refused,
  0 no longer refused.** Every one of the 66 sits at a midpoint distance of exactly
  0.0100 — the tolerance itself — so the change admits the boundary the constant
  already declares and reaches nothing else.
* On production open/active markets: **25 rows newly refused**, against **4,155 the
  predicate already refuses there** — a 0.6% extension of a shipped class, not a new
  one. All 25 are genuine empty books (0.00/1.00, 0.01/0.99, 0.02/0.96 …) carrying a
  price pinned within a cent of 50%.

SETTLED ROWS ARE NOT A NEW EXPOSURE HERE, AND THE COUNT IS THE ARGUMENT. One of the 25
is a settled winner (outcome 133046831, ``is_winner`` true, ``api_settlement``) still
carrying ``0.510000`` on a 0.00/1.00 book, on a market left ``status='open'`` by
gotcha #33. It joins **3 settled winners and 52 rows with a ``resolution_source`` that
this predicate already refuses on open markets today**. So a graded row meeting an
empty-book refusal is shipped behaviour that #6784 extends by one row; it is not a
consequence of this change.

It does falsify the "a graded side carries 0 or 1, so the result is kept" aside in
:func:`bout_price_is_supported`'s docstring, which landed on master as `41367b62b`
while this was being measured. That paragraph is corrected in the same commit — the
behaviour it described was never what the code did, and on a bout the refusal is the
right answer anyway (printing "51%" beside a fighter who already won is the defect,
not the refusal). The consumer half of #6777 is Discover's and is not yet on master,
so the bout helper still has zero callers and this interaction is latent, not
reader-visible.
"""

import pytest

from app.utils.feed_market_quality import (
    EMPTY_BOOK_MIDPOINT_TOLERANCE,
    EMPTY_BOOK_MIN_SPREAD,
    is_empty_book_midpoint,
)

# The production specimen, field for field (outcome 225982191).
SPECIMEN = (0.51, 0.01, 0.99)


class TestTheServedSpecimen:
    def test_the_chatgpt_downloads_rung_that_served_51_percent_is_refused(self):
        """`/api/futures/60481170` -> "Above 107" 51% on a 0.01/0.99 book."""
        assert is_empty_book_midpoint(*SPECIMEN) is True

    def test_its_mirror_one_cent_the_other_side_is_refused(self):
        """0.49 on the same book is the same distance and must answer the same."""
        assert is_empty_book_midpoint(0.49, 0.01, 0.99) is True

    def test_the_rungs_beside_it_on_that_ladder_are_kept(self):
        """The fix must take the one bad rung and leave the ladder standing.

        Read from the same market in the same pass: "Above 101" at 0.88 and
        "Above 105" at 0.69 sit far off the midpoint (condition 3 keeps them), and
        "Above 109" has a 0.01/0.83 book whose spread is 0.82 (condition 2 keeps it).
        """
        assert is_empty_book_midpoint(0.88, 0.01, 0.99) is False
        assert is_empty_book_midpoint(0.69, 0.01, 0.99) is False
        assert is_empty_book_midpoint(0.80, 0.01, 0.83) is False


class TestTheBoundaryIsReachable:
    """The property the old compare could not express: the `=` in `<=` must fire."""

    @pytest.mark.parametrize(
        "bid,ask",
        [(0.01, 0.99), (0.0, 1.0), (0.02, 0.96), (0.05, 0.95), (0.0, 0.9)],
    )
    def test_a_price_exactly_one_tolerance_from_the_midpoint_is_refused(self, bid, ask):
        """Derived from the constant, so moving it re-derives this and still holds."""
        mid = (bid + ask) / 2
        assert (
            is_empty_book_midpoint(mid + EMPTY_BOOK_MIDPOINT_TOLERANCE, bid, ask)
            is True
        )
        assert (
            is_empty_book_midpoint(mid - EMPTY_BOOK_MIDPOINT_TOLERANCE, bid, ask)
            is True
        )

    @pytest.mark.parametrize("bid,ask", [(0.01, 0.99), (0.0, 1.0), (0.02, 0.96)])
    def test_a_price_just_past_the_tolerance_is_still_kept(self, bid, ask):
        """The repair admits the boundary and nothing beyond it.

        One cent past the tolerance stays honest — this is the assertion that would
        fail if the compare had been loosened (a `< TOLERANCE + tick`) instead of
        quantized.
        """
        mid = (bid + ask) / 2
        past = mid + EMPTY_BOOK_MIDPOINT_TOLERANCE + 0.01
        assert is_empty_book_midpoint(past, bid, ask) is False

    def test_the_delta_is_quantized_at_its_own_precision_not_the_books(self):
        """The mutation that survived the first battery, turned into a test.

        Rounding the delta at ``_BOOK_PRICE_DECIMALS`` (4) is the obvious move —
        it is the constant the line above uses — and it is wrong, because the delta
        is not a book value. ``current_probability`` is Numeric(7,6) and the two
        book columns are Numeric(5,4), so a midpoint is exact at 5 decimals and
        ``|price - midpoint|`` is exact at 6.

        A price 0.010049 from the midpoint is genuinely OUTSIDE a 0.01 tolerance.
        At 4dp that distance collapses onto 0.0100 and the row is refused as though
        it sat exactly on the bound — the quantization silently becoming a widening
        of the very constant #6784 promised not to move. At 6dp it is kept.
        """
        assert is_empty_book_midpoint(0.510049, 0.01, 0.99) is False
        assert is_empty_book_midpoint(0.489951, 0.01, 0.99) is False
        # and the boundary itself still refuses, one ten-thousandth away
        assert is_empty_book_midpoint(0.51, 0.01, 0.99) is True

    def test_the_boundary_answers_the_same_for_every_book_on_it(self):
        """THE REAL DEFECT, which is worse than an unreachable `=`: it was ARBITRARY.

        The float error runs in BOTH directions. Of the 72 integer-cent
        `(price, bid, ask)` triples that sit exactly one tolerance from their
        midpoint on a qualifying book, `abs(p - mid)` evaluates to
        `0.009999999999999953` for 6 of them and to `0.010000000000000009` (or
        `...064`) for the other 66. So before #6784 the predicate refused 6 of the
        72 and admitted 66 — the same distance, the same policy, opposite answers,
        decided by binary representation rather than by the constant.

        "The `=` is decorative" was the first reading and it was too kind. A
        boundary whose answer depends on how the operands round is not a boundary,
        and that is the property this asserts: every point ON the tolerance answers
        the same way.
        """
        on_boundary = [
            (p_c / 100, b_c / 100, a_c / 100)
            for b_c in range(0, 101)
            for a_c in range(0, 101)
            for p_c in range(0, 101)
            if round(a_c / 100 - b_c / 100, 4) >= EMPTY_BOOK_MIN_SPREAD
            and round(abs(p_c / 100 - (b_c / 100 + a_c / 100) / 2), 4)
            == EMPTY_BOOK_MIDPOINT_TOLERANCE
        ]
        assert len(on_boundary) == 72, "the boundary population itself moved"
        kept = [t for t in on_boundary if not is_empty_book_midpoint(*t)]
        assert kept == [], (
            f"{len(kept)} of {len(on_boundary)} exact-tolerance books are still "
            f"admitted: the boundary is decided by float error, not by the constant"
        )


class TestTheBlastRadiusBothWays:
    def test_nothing_that_was_refused_stops_being_refused(self):
        """A compare change must not LOSE refusals; #6784 is one-directional.

        Recomputed here against the pre-#6784 expression rather than a recorded
        count, so it keeps testing the real thing if a constant moves.
        """
        lost = []
        for b_c in range(0, 21):
            for a_c in range(0, 101):
                for p_c in range(0, 101):
                    p, b, a = p_c / 100, b_c / 100, a_c / 100
                    old = (
                        round(a - b, 4) >= EMPTY_BOOK_MIN_SPREAD
                        and abs(p - (b + a) / 2) <= EMPTY_BOOK_MIDPOINT_TOLERANCE
                    )
                    if old and not is_empty_book_midpoint(p, b, a):
                        lost.append((p, b, a))
        assert lost == []

    def test_everything_newly_refused_sits_exactly_on_the_tolerance(self):
        """The 66 the sweep found, stated as the property that makes them safe."""
        newly = []
        for b_c in range(0, 21):
            for a_c in range(0, 101):
                for p_c in range(0, 101):
                    p, b, a = p_c / 100, b_c / 100, a_c / 100
                    old = (
                        round(a - b, 4) >= EMPTY_BOOK_MIN_SPREAD
                        and abs(p - (b + a) / 2) <= EMPTY_BOOK_MIDPOINT_TOLERANCE
                    )
                    if is_empty_book_midpoint(p, b, a) and not old:
                        newly.append((p, b, a))
        assert newly, "the repair reaches nothing — it is inert"
        for p, b, a in newly:
            assert round(abs(p - (b + a) / 2), 4) == EMPTY_BOOK_MIDPOINT_TOLERANCE

    def test_the_coin_flip_band_still_confines_the_reach(self):
        """#5247's safety property, re-asserted because the reach grew.

        Widening a compare could in principle reach outside the band the three
        constants define; this proves it did not.
        """
        band_lo = EMPTY_BOOK_MIN_SPREAD / 2 - EMPTY_BOOK_MIDPOINT_TOLERANCE
        band_hi = (1.0 - EMPTY_BOOK_MIN_SPREAD / 2) + EMPTY_BOOK_MIDPOINT_TOLERANCE
        for b_c in range(0, 21):
            for a_c in range(0, 101):
                for p_c in range(0, 101):
                    p, b, a = p_c / 100, b_c / 100, a_c / 100
                    if is_empty_book_midpoint(p, b, a):
                        assert band_lo <= p <= band_hi


class TestTheHonestLinesSurvive:
    """The classes #5247/#5333/#6727 measured and promised to keep."""

    def test_a_genuine_even_money_market_on_a_tight_book_is_kept(self):
        assert is_empty_book_midpoint(0.50, 0.49, 0.51) is False

    def test_a_traded_price_far_from_the_midpoint_is_kept(self):
        assert is_empty_book_midpoint(0.30, 0.01, 0.99) is False

    def test_a_model_price_with_no_book_is_kept(self):
        assert is_empty_book_midpoint(0.50, None, None) is False

    def test_a_one_sided_book_is_kept(self):
        assert is_empty_book_midpoint(0.50, None, 0.97) is False
        assert is_empty_book_midpoint(0.50, 0.03, None) is False

    def test_a_book_short_of_the_spread_is_kept_at_the_tolerance_too(self):
        """Condition 2 still runs first: the quantized tolerance does not rescue a
        book that never qualified as empty."""
        mid = (0.10 + 0.90) / 2
        assert (
            is_empty_book_midpoint(mid + EMPTY_BOOK_MIDPOINT_TOLERANCE, 0.10, 0.90)
            is False
        )


class TestTheNumericColumnsAgree:
    @pytest.mark.parametrize("bid,ask", [(0.01, 0.99), (0.0, 1.0), (0.02, 0.96)])
    def test_decimal_inputs_answer_the_same_at_the_boundary(self, bid, ask):
        """`current_yes_bid`/`current_yes_ask` arrive as `Decimal` from Numeric(5,4).

        The specimen row reaches the predicate as Decimal, so the boundary has to
        hold on that path and not only on floats.
        """
        from decimal import Decimal

        mid = (bid + ask) / 2
        price = Decimal(str(round(mid + EMPTY_BOOK_MIDPOINT_TOLERANCE, 4)))
        assert (
            is_empty_book_midpoint(price, Decimal(str(bid)), Decimal(str(ask))) is True
        )

"""#6676: the hourly price refresh stops writing a coin-flip onto an empty book.

WHAT A READER SAW. On 2026-09-17 at 07:53:50Z — after both that morning's
releases — market 61176445, "Game Spread: Adrian Mannarino (-4.5) vs Matisse
Bobichon (+4.5)", served two rows on a scheduled tennis match:

    Adrian Mannarino   49%   on a book quoting 0.0100 / 0.9800
    Matisse Bobichon   51%   on a book quoting 0.0200 / 0.9900

Nobody will buy at 1c and nobody will sell at 98c, so the quote bounds nothing
and the 49/51 is the midpoint of an empty book — a number manufactured by
averaging a spread no trade will ever cross. It reads as a genuine toss-up.

WHY IT REACHED PRODUCTION. ``_write_prices`` had no untradeable-book guard of
any kind: a grep of the module for ``is_fabricated_midpoint``,
``is_empty_book_midpoint``, ``_poly_book_is_untradeable`` or
``feed_market_quality`` returned zero hits. The ingest half
(``tasks/polymarket.py``) had been guarded; this is the other door into the same
column, and on the rows it touches it is the dominant writer.

THE TEST THAT MATTERS IS ``test_the_complement_leg_is_declined_with_its_twin``.
``_legs`` returns the yes leg AND the no leg, and the no leg's book is
``complementary_book(bid, ask)`` = ``(1 - ask, 1 - bid)``. A guard applied per
LEG therefore asks one question about one book twice, and gets two answers
whenever the empty-book bounds are not complements of each other: it fires on
yes, misses no, and the phantom complement prints on the row directly beneath
the one it repaired. That test fails against a per-leg guard and passes against
an item-level one; it is the only test here that can tell the two apart.

MOVING THE BOUNDS NEVER CLOSED THE ASYMMETRY; CHANGING THE PREDICATE'S SHAPE
DID. Both halves of that sentence are measured, and the order matters because
the first half is what makes the second one safe to rely on.

At the pair in force when this file was written the escaping band was
``0.95 <= ask < 0.98``, holding 131 of 499 open Polymarket yes-leg specimens
measured on production 2026-09-17 — a quarter of the class, half-fixed. #5333
widens ``EMPTY_BOOK_MAX_BID`` so the two constants sum to 1 *as written*, and
that retires the band but NOT the hazard: the complement is derived as
``1 - float(ask)`` and nothing on the path rounds, so ``1 - 0.95`` is
``0.050000000000000044`` — above a 0.05 bound, and still escaping a per-leg
read. Swept over all 5,050 integer-cent books with the writer's own arithmetic,
6 legs still escape, all at ``ask == 0.95`` exactly: an ordinary round quote,
not an exotic boundary. (A sweep that tidies the complement with ``round()``
reports that class as empty. It is not, and two readers reached for that
rounding on the same day.)

#6727 then replaces the two independent bounds with the single statement they
were jointly making — ``round(ask - bid, 4) >= EMPTY_BOOK_MIN_SPREAD`` — and
THAT closes it, for a reason no choice of constants can supply. The complement
of ``(bid, ask)`` is ``(1 - ask, 1 - bid)``, whose spread is
``(1 - bid) - (1 - ask)`` = ``ask - bid``: **identical, algebraically, for every
book.** Condition 3 is likewise invariant, since the complement's midpoint
distance is ``|(1 - p) - (1 - mid)|`` = ``|mid - p|``. So the predicate now
answers the same for a leg and its twin by construction, the 4dp rounding
absorbing the float residue that made the bid-bound form disagree. Swept the
same 5,050 books through the same ``complementary_book``: **0 disagreements**,
against 6 under #5333's bounds and 3 under the pair this file was born with —
the sweep detects the class when the class is there.

SO WHY IS THE ITEM-LEVEL GUARD STILL HERE? Because the invariance is a property
of the SHAPE, not of the numbers, and it is one edit deep. Any return to two
one-sided bounds reopens the asymmetry in full — immediately and silently if
``EMPTY_BOOK_MAX_BID + EMPTY_BOOK_MIN_ASK != 1``, and at the float boundary even
if they are spelled to sum to 1, which is exactly the 6-leg case above. The
specimen below is still chosen to escape a per-leg BID-BOUND read, and the
assertion that it does is kept precisely so this file keeps proving the shape is
what is carrying the symmetry. Do not delete the guard on the grounds that the
class is empty today: it is empty because of the spread form, and the test that
would notice its return is this one.

THE CONTROLS ARE LOAD-BEARING, and one of them is a fence.
``test_a_wide_but_real_kalshi_book_is_still_written`` encodes a measurement:
``is_fabricated_midpoint`` — the sibling predicate, which the ingest half does
carry — matches 8,357 Kalshi outcomes on open markets against the empty-book
test's 667, and 7,715 of those are two-sided real quotes spanning 0.10 to 0.90.
They are honest wide-market lines that merely sit at their own midpoint. Because
``_write_prices`` is SHARED by both venues, importing that predicate here would
freeze all 7,715 as stale to catch a class the empty-book test already catches.
The control is here so that the next reader who notices the asymmetry with the
ingest half and "completes" it turns this file red instead of shipping it.
"""

import inspect

import pytest

from app.tasks import futures_price_refresh as fpr
from app.tasks.polymarket import complementary_book
from app.utils.feed_market_quality import (
    EMPTY_BOOK_MAX_BID,
    is_empty_book_midpoint,
    is_fabricated_midpoint,
)
from tests.test_futures_price_refresh_counts_declines_5869 import _WriteSession

pytestmark = pytest.mark.asyncio


#: The measured specimen, to the digit: market 61176445's two legs as the venue
#: quoted them at 07:53:50.475920Z. The ``no`` sub-dict carries the complementary
#: book the fetcher derives, ``(1 - 0.98, 1 - 0.01)``.
def _mannarino_bobichon():
    return {
        "external_id": "0x782b59",
        "probability": 0.49,
        "yes_bid": 0.01,
        "yes_ask": 0.98,
        "no": {"probability": 0.51, "yes_bid": 0.02, "yes_ask": 0.99},
    }


def _pair_rows(condition_id="0x782b59"):
    return ((11, f"{condition_id}_yes"), (12, f"{condition_id}_no"))


class TestThePhantomCoinFlipNeverReachesTheRow:
    async def test_the_measured_specimen_is_declined_on_both_legs(self):
        session = _WriteSession(rows=_pair_rows())
        stats: dict = {}
        written = await fpr._write_prices(
            session, 61176445, "polymarket", [_mannarino_bobichon()], stats
        )
        assert written == 0
        assert session.updates == 0, "a phantom midpoint must not reach the row"
        assert session.inserts == 0, "nor be banked as a snapshot"
        assert stats["legs_declined_empty_book"] == 2

    async def test_the_complement_leg_is_declined_with_its_twin(self):
        """What carries the symmetry, and the reason the guard tests the ITEM.

        ``yes_ask = 0.95`` is the specimen that escapes a per-leg BID-BOUND read
        at BOTH settings of ``EMPTY_BOOK_MAX_BID`` — the one this file was
        written against and #5333's wider one — so this control keeps its
        meaning when that constant moves. The yes leg is an empty-book midpoint;
        the no leg's book, derived by the writer's own ``complementary_book``,
        is ``(1 - 0.95, 1 - 0.01)``, and ``1 - 0.95`` is
        ``0.050000000000000044``, above either bound.

        The complement is COMPUTED here rather than typed as ``0.05``, because
        the literal is a different number from the one production produces and
        it is the one that makes this control look unnecessary. The assertions
        state the RELATIONSHIP to the bound rather than a copy of its value.

        🔄 AMENDED BY #6727, AND THE AMENDMENT IS WHY THE BID-BOUND ASSERTION
        STAYS. Under the two-bound predicate this specimen's complement was
        False on its own and a per-leg guard wrote it — 52% on an empty book,
        under the 48% it had just declined. #6727 makes condition 2 a spread,
        and a spread is invariant under complementation for every book
        (``(1 - bid) - (1 - ask) == ask - bid``), so the complement is now
        caught reading it alone. The two assertions below therefore say
        different things and both are load-bearing: the bid bound is STILL
        escaped, and the predicate catches it ANYWAY. That pair is the proof
        that the shape is carrying the symmetry rather than the constants
        happening to sum to 1 — and it is what turns red, rather than the whole
        class going quietly unguarded, if anyone puts the two bounds back.

        If the bid-bound assertion goes red the specimen has stopped exhibiting
        the class and needs re-choosing against the new constants; if the
        complement assertion goes red the predicate has stopped being
        complement-invariant. Either way read this module's docstring, and in
        neither case relax the item-level guard.
        """
        yes_bid, yes_ask = 0.01, 0.95
        no_bid, no_ask, _ = complementary_book(yes_bid, yes_ask, None)
        yes_prob = (yes_bid + yes_ask) / 2
        no_prob = 1 - yes_prob
        item = {
            "external_id": "0xband",
            "probability": yes_prob,
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "no": {"probability": no_prob, "yes_bid": no_bid, "yes_ask": no_ask},
        }
        assert is_empty_book_midpoint(yes_prob, yes_bid, yes_ask) is True
        # The specimen still escapes the BID BOUND — that has not changed, and
        # it is what makes the next assertion mean something.
        assert no_bid > EMPTY_BOOK_MAX_BID, (
            "the specimen no longer escapes a per-leg bid-bound read — "
            "re-choose it against the current bounds; read this module's "
            "docstring first"
        )
        # ...and #6727's spread form catches it anyway, because the spread of a
        # complement is the spread of its twin. If this goes red, condition 2
        # has stopped being complement-invariant and the item-level guard below
        # is once again the ONLY thing between a reader and a phantom 52%.
        assert is_empty_book_midpoint(no_prob, no_bid, no_ask) is True, (
            "the complement escaped: condition 2 is no longer invariant under "
            "(bid, ask) -> (1 - ask, 1 - bid); the two-bound shape is back"
        )
        # Not one-sided: a book that genuinely bounds something is untouched on
        # either leg, so the above is a statement about EMPTY books, not about
        # the predicate having become indiscriminate.
        real_bid, real_ask = 0.10, 0.93
        real_no_bid, real_no_ask, _ = complementary_book(real_bid, real_ask, None)
        real_prob = (real_bid + real_ask) / 2
        assert is_empty_book_midpoint(real_prob, real_bid, real_ask) is False
        assert is_empty_book_midpoint(1 - real_prob, real_no_bid, real_no_ask) is False

        session = _WriteSession(rows=_pair_rows("0xband"))
        stats: dict = {}
        written = await fpr._write_prices(
            session, 61176445, "polymarket", [item], stats
        )
        assert written == 0
        assert session.updates == 0, (
            "a leg of the pair was written. Under #6727 both legs are caught "
            "reading each alone, so this failing means either the item path "
            "declines only one of the two, or condition 2 has lost its "
            "invariance — check the complement assertion above first"
        )
        assert stats["legs_declined_empty_book"] == 2


class TestTheGuardSparesEveryBookThatIsNotEmpty:
    """Without these the assertions above are satisfied by a writer that
    refuses everything."""

    async def test_a_healthy_two_sided_book_is_written(self):
        session = _WriteSession(rows=_pair_rows("0xlive"))
        stats: dict = {}
        item = {
            "external_id": "0xlive",
            "probability": 0.62,
            "yes_bid": 0.61,
            "yes_ask": 0.63,
            "no": {"probability": 0.38, "yes_bid": 0.37, "yes_ask": 0.39},
        }
        written = await fpr._write_prices(
            session, 61176445, "polymarket", [item], stats
        )
        assert written == 2
        assert session.updates == 2
        assert stats.get("legs_declined_empty_book", 0) == 0

    async def test_a_wide_but_real_kalshi_book_is_still_written(self):
        """THE FENCE. 7,715 honest Kalshi lines depend on this staying green.

        ``bid 0.30 / ask 0.55`` is a 25c spread and 0.425 is its exact midpoint,
        so ``is_fabricated_midpoint`` is True here — but the book is NOT empty
        (there is a real bid at 30c), so the empty-book test spares it. If this
        goes red because someone imported the sibling predicate into this shared
        writer, read the module comment at the guard before changing this file.
        """
        assert is_fabricated_midpoint(0.425, 0.30, 0.55) is True
        assert is_empty_book_midpoint(0.425, 0.30, 0.55) is False

        session = _WriteSession(rows=((11, "KXNFLGAME-26"),))
        stats: dict = {}
        written = await fpr._write_prices(
            session,
            61176445,
            "kalshi",
            [
                {
                    "external_id": "KXNFLGAME-26",
                    "probability": 0.425,
                    "yes_bid": 0.30,
                    "yes_ask": 0.55,
                }
            ],
            stats,
        )
        assert written == 1
        assert (
            session.updates == 1
        ), "a wide but real Kalshi book is an honest line, not a phantom"
        assert stats.get("legs_declined_empty_book", 0) == 0

    async def test_a_model_price_with_no_book_passes_through(self):
        """DataGolf and odds_api carry no order book at all. Both sides NULL is
        'no book', not 'an empty book', and the predicate must not confuse
        them — these rows have no bid/ask keys whatsoever."""
        session = _WriteSession(rows=((11, "dg-scheffler"),))
        stats: dict = {}
        written = await fpr._write_prices(
            session,
            61176445,
            "datagolf",
            [{"external_id": "dg-scheffler", "probability": 0.5}],
            stats,
        )
        assert written == 1
        assert session.updates == 1
        assert stats.get("legs_declined_empty_book", 0) == 0

    async def test_an_extreme_book_priced_off_a_trade_is_written(self):
        """Condition 3 of the predicate, exercised. A both-extremes book whose
        price is FAR from its midpoint got that price from a real trade (Kalshi
        falls back to ``last_price`` on a wide book). 0.97 on a 0.00/1.00 book
        is a blowout line, and must not move."""
        assert is_empty_book_midpoint(0.97, 0.0, 1.0) is False
        session = _WriteSession(rows=((11, "KXCFB-LSU"),))
        stats: dict = {}
        written = await fpr._write_prices(
            session,
            61176445,
            "kalshi",
            [
                {
                    "external_id": "KXCFB-LSU",
                    "probability": 0.97,
                    "yes_bid": 0.0,
                    "yes_ask": 1.0,
                }
            ],
            stats,
        )
        assert written == 1
        assert stats.get("legs_declined_empty_book", 0) == 0


class TestTheRefusalIsVisibleRatherThanSilent:
    async def test_the_counter_is_initialised_so_zero_is_reported(self):
        """#5869's lesson applied to the new counter: a pass that declined
        nothing and a pass whose guard never ran must not read the same.

        The task's stats dict is assembled inline rather than by a factory, so
        this asserts the initialiser the way the existing suite asserts
        ``unknown_outcomes`` — against the module source. A counter that only
        springs into existence when it fires reports absence for the healthy
        steady state, which is the silence this ship exists to end.
        """
        src = inspect.getsource(fpr)
        assert '"legs_declined_empty_book": 0,' in src
        # And it is read back out, not merely initialised.
        assert (
            'stats.get(\n                "legs_declined_empty_book", 0\n            )'
            in src
            or 'stats["legs_declined_empty_book"] = stats.get(' in src
        )

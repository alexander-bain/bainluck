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

THE GUARD IS ASKED OF THE ITEM, NOT THE LEG. ``_legs`` returns the yes leg AND
the no leg, and on the one path that builds a no leg the book is
``complementary_book(bid, ask)`` = ``(1 - ask, 1 - bid)`` — the same CLOB
addressed from the other token. So whether a per-LEG guard is equivalent to a
per-ITEM one depends entirely on whether the predicate answers a book and its
complement the same way, and that has moved twice in one day:

    bounds in force          asymmetric legs   what escapes alone
    bid<=0.02, ask>=0.95           18          0.95 <= ask < 0.98 — 131 of 499
                                               open Polymarket yes-leg
                                               specimens, a quarter of the class
    bid<=0.05, ask>=0.95  (#5333)   6          ``ask == 0.95`` exactly, on the
                                               float boundary: ``1 - 0.95`` is
                                               ``0.050000000000000044``
    ask - bid >= 0.90     (#6727)   0          the SPREAD is invariant under the
                                               flip — but see below: condition 3
                                               was not, and 4 legs escaped there
    + rounded condition 3           0          nothing; the invariance is now the
                                               code's and not only the algebra's

Swept over all 5,050 integer-cent books with the writer's own arithmetic. (A
sweep that tidies the complement with ``round()`` reports the middle row as 0
too, and concludes the guard was never load-bearing. It was, on a quarter of the
class, and it still is on the six.)

THE FOURTH ROW IS #6676's FOURTH WRITER AND IT CORRECTS THE THIRD. Every sweep
above varies the BOOK and holds the price fixed, so none of them can see a
condition-3 boundary, and the "empty by construction" the third row used to
claim was measured by a method that could not have found a counter-example. Over
all 509,949 (bid, ask, price) triples the unrounded predicate disagreed with its
own complement on 10 — and on 4 of those the ITEM passed while the derived no
leg was the phantom, which is the split this file exists to prevent, reachable
through this module's own producer. ``feed_market_quality`` now rounds that
compare; ``test_empty_book_midpoint_tolerance_6676.py`` is where it is pinned.
The item-level guard below still stands, for the reasons at the call site.

SO THE ASYMMETRY IS REAL, IS CLOSING, AND CLOSES ENTIRELY UNDER #6727 — at which
point this guard is defence in depth on this path. IT STAYS, and
``test_a_per_leg_guard_would_split_the_pair`` is what keeps it able to go red.
Two reasons no constant can retire: the equivalence rests on the predicate
staying exactly symmetric under complementation, which is a property of today's
shape rather than an invariant anything enforces; and ``_legs`` writes whatever
``item["no"]`` holds, so a second producer passing the venue's own no-token book
instead of the derived one reopens the split the same day it lands.

Which is why the controls below assert the reader-visible outcome — the pair is
declined WHOLE — and deliberately never assert the complement's own verdict.
That verdict is the thing that moves, and pinning it is what made this file red
against two certed shas on 2026-09-17 (#5333 and #6727, notice 47(a)).

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
        """The production-shaped pair: the derived complement goes with its twin.

        ``ask = 0.96`` sits inside the band this ship measured, and the no leg's
        book is built by the writer's own ``complementary_book`` rather than
        typed, so the specimen is what the Polymarket path actually assembles.

        What is asserted is the reader-visible outcome — neither row moves. The
        complement's OWN verdict is not asserted here: at the bounds this file
        was written against it was False (the leg escaped a per-leg read), under
        #6727's spread form it is True, and pinning either one turns this control
        red on a predicate change that does not touch the ship. The module
        docstring carries that table; ``test_a_per_leg_guard_would_split_the
        _pair`` is what still tells a per-leg guard from a per-item one.
        """
        yes_bid, yes_ask = 0.01, 0.96
        no_bid, no_ask, _ = complementary_book(yes_bid, yes_ask, None)
        item = {
            "external_id": "0xband",
            "probability": 0.485,
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "no": {"probability": 0.515, "yes_bid": no_bid, "yes_ask": no_ask},
        }
        # The yes leg is an empty-book midpoint under every shape the predicate
        # has had: the two-bound pair at either setting, and the spread form.
        assert is_empty_book_midpoint(0.485, yes_bid, yes_ask) is True

        session = _WriteSession(rows=_pair_rows("0xband"))
        stats: dict = {}
        written = await fpr._write_prices(
            session, 61176445, "polymarket", [item], stats
        )
        assert written == 0
        assert session.updates == 0, (
            "the complement leg was written: the guard is per-leg, so the "
            "phantom complement prints on the row beneath the one it declined"
        )
        assert stats["legs_declined_empty_book"] == 2

    async def test_a_per_leg_guard_would_split_the_pair(self):
        """THE CONTROL THAT OUTLIVES THE CONSTANTS. Read the module docstring.

        The no leg here carries a book that BOUNDS SOMETHING — ``0.40 / 0.60``,
        a 20c spread with a real bid on it — so no shape of
        ``is_empty_book_midpoint``, past or present, calls it an empty book. The
        yes leg is an empty book under all three. A guard asked per LEG therefore
        declines the yes leg and WRITES the no leg, splitting the pair; a guard
        asked of the ITEM declines both, which is what this asserts.

        This pairing is not one the Polymarket path can produce today — that path
        derives the no side by identity, so its two books always agree, and after
        #6727 they always get the same verdict. It is constructed on purpose,
        because every specimen that is both production-shaped AND distinguishing
        depends on the empty-book bounds being non-complementary, and #6727 makes
        them complementary. What is pinned here is the SHAPE of the guard, which
        is the thing a later reader would change: ``_legs`` writes whatever
        ``item["no"]`` holds, and a second producer passing the venue's own
        no-token book makes this specimen live rather than constructed.
        """
        yes_bid, yes_ask = 0.01, 0.96
        no_bid, no_ask = 0.40, 0.60
        # Not an assumption: the no leg's book is honest by any reading of the
        # predicate, so only an item-level guard has grounds to decline it.
        assert is_empty_book_midpoint(0.485, yes_bid, yes_ask) is True
        assert is_empty_book_midpoint(0.50, no_bid, no_ask) is False

        item = {
            "external_id": "0xsplit",
            "probability": 0.485,
            "yes_bid": yes_bid,
            "yes_ask": yes_ask,
            "no": {"probability": 0.50, "yes_bid": no_bid, "yes_ask": no_ask},
        }
        session = _WriteSession(rows=_pair_rows("0xsplit"))
        stats: dict = {}
        written = await fpr._write_prices(
            session, 61176445, "polymarket", [item], stats
        )
        assert written == 0
        assert session.updates == 0, (
            "the pair split: the guard read the LEG, so the yes row was "
            "declined and its twin was written anyway"
        )
        assert session.inserts == 0
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

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
``complementary_book(bid, ask)`` = ``(1 - ask, 1 - bid)``. The empty-book
thresholds are not complementary — ``1 - EMPTY_BOOK_MAX_BID`` is 0.98, but
``EMPTY_BOOK_MIN_ASK`` is 0.95 — so a guard applied per LEG fires on yes and
misses no for every book with ``0.95 <= ask < 0.98``. Measured on production the
same day: 131 of 499 open Polymarket yes-leg specimens sit in that band. A
per-leg guard would therefore have half-fixed a quarter of the class and left
the phantom complement printing on the row directly beneath the one it repaired.
That test fails against a per-leg guard and passes against an item-level one; it
is the only test here that can tell the two apart.

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
        """The asymmetric band, and the reason the guard tests the ITEM.

        ``ask = 0.96`` is inside ``[0.95, 0.98)``. The yes leg is an empty-book
        midpoint; the no leg's derived book is ``(0.04, 0.99)``. When this was
        written the predicate read two independent bounds, so a 4c bid was above
        ``EMPTY_BOOK_MAX_BID`` and the predicate was False on that leg READ ALONE
        — a per-leg guard wrote it, 51% on an empty book, sitting under the 49%
        it had just declined. Testing the ITEM is what closed that.

        🔄 AMENDED BY #6727 (2026-09-17), and the amendment is the good news.
        The two bounds became the one statement they were jointly making —
        ``ask - bid >= 0.90`` — so ``(0.04, 0.99)`` is a 95c-wide book and the
        predicate is now True on that leg read alone. **The asymmetry this test
        was built around no longer exists**, which means the item-level guard
        below is belt-and-braces rather than the only thing between a reader and
        a phantom 51%. The test keeps its full value: it still proves the guard
        is per-ITEM, and it now also pins that the complement can no longer slip
        through on its own. CERT-3016 caught this composition — my branch
        pre-dated this file, so exact-sha CI could not see it (notice 47(a)).
        """
        item = {
            "external_id": "0xband",
            "probability": 0.485,
            "yes_bid": 0.01,
            "yes_ask": 0.96,
            "no": {"probability": 0.515, "yes_bid": 0.04, "yes_ask": 0.99},
        }
        # Both legs are now caught on their own; the asymmetry is closed.
        assert is_empty_book_midpoint(0.485, 0.01, 0.96) is True
        assert is_empty_book_midpoint(0.515, 0.04, 0.99) is True
        # The band is still asymmetric in the direction that matters: a book
        # that genuinely bounds something is untouched on either leg.
        assert is_empty_book_midpoint(0.515, 0.10, 0.93) is False

        session = _WriteSession(rows=_pair_rows("0xband"))
        stats: dict = {}
        written = await fpr._write_prices(
            session, 61176445, "polymarket", [item], stats
        )
        assert written == 0
        assert session.updates == 0, (
            "the complement leg was written: the guard is per-leg, and 26% of "
            "the measured class is only half-fixed"
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

"""#5869: the leg this pass declined to price is counted, and the count is split.

WHAT WAS WRONG WITH THE INSTRUMENT. ``futures_price_refresh`` reports
``markets_priced``, ``unknown_outcomes``, ``not_found``, ``unpriceable``,
``venue_settled`` and ``legs_retired``. None of them can express the third
outcome: the venue answered, ``_resolve_market_probability`` refused the answer,
the row kept whatever number it was last given, and the pass reported
``terminal: "complete"``.

Market 57792790's Big Ten ladder is the case that produced this file. On
2026-09-13 the refresh rewrote sixteen of its eighteen rungs in one write
(``last_updated`` identical to the microsecond at ``06:50:44.181499``); Penn
State and Washington kept their ``2026-08-01 11:18:26.445139`` stamp and their
``0.040000``, while the venue was quoting 0.0665 and 0.0680 over live books. The
pass said nothing. The only instrument that found the two frozen rungs was a
screenshot, and by the time anyone asked why, the Gamma payload that justified
the refusal was gone.

WHY THE SPLIT IS THE POINT, and not decoration. A declined leg the venue quotes
NOTHING for is ``_retire_unpriced_legs``' subject — the right response is to
withdraw our number, and if that is not happening the retirement's REACH is
short (it is scoped to negRisk multi-market events). A declined leg the venue IS
quoting is a judgement of ours, on a live book, and is the population worth
reading about. One counter would say neither; two compose with ``legs_retired``.

The specimens below are the measured shapes, not invented ones, and every
"refused" specimen asserts ``_resolves_to_nothing`` at its head — a specimen the
resolver happily prices never reaches the counter, and the test would pass on a
branch it never entered.
"""

import pytest

from app.tasks import futures_price_refresh as fpr
from tests.test_futures_price_refresh_retires_unpriced_4000 import (
    _RetirementHarness,
    _Result,
    _dead_leg,
    _field,
    _leg,
    _priced_leg,
    _resolves_to_nothing,
)

pytestmark = pytest.mark.asyncio


#: Penn State's measured shape: a real two-sided book the resolver still refuses.
#: ``bid 0.11 / ask 1.0`` is untradeable by ``_poly_book_is_untradeable`` and has
#: no trade behind it, so the resolver returns None — and the venue is plainly
#: quoting, which is the whole distinction this file is about.
def _quoted_but_refused(condition_id="0xwide"):
    return _leg(condition_id, yes=None, bid=0.11, ask=1.0, last=None)


#: The same refusal reached by the OTHER fact. Bid at zero so the bid arm cannot
#: be what passes it; it has traded at 0.53, and a trade is evidence.
def _traded_but_refused(condition_id="0xtraded"):
    return _leg(condition_id, yes=0.5, bid=0.0, ask=1.0, last=0.53)


class TestTheQuotedTestReadsBothFactsAndNothingElse:
    """``_venue_quotes_this_leg`` is two facts, so it needs two specimens.

    One specimen would leave half the function deletable with the suite green —
    the mistake ``test_a_leg_with_a_bid_is_refused_not_absent`` calls out in the
    #4000 file, in the same function's mirror image.
    """

    async def test_a_bid_on_the_book_is_the_venue_quoting(self):
        leg = _quoted_but_refused()
        assert _resolves_to_nothing(leg), "specimen never reaches the counter"
        assert not leg.last_trade_price, "the trade arm must not be what passes this"
        assert fpr._venue_quotes_this_leg(leg) is True

    async def test_a_trade_behind_it_is_the_venue_quoting(self):
        leg = _traded_but_refused()
        assert _resolves_to_nothing(leg), "specimen never reaches the counter"
        assert leg.best_bid == 0.0, "the bid arm must not be what passes this"
        assert fpr._venue_quotes_this_leg(leg) is True

    async def test_a_tombstone_is_not(self):
        """``bestBid=0 bestAsk=1 lastTradePrice=0`` — the measured dead shape."""
        assert fpr._venue_quotes_this_leg(_dead_leg("0xperson_bg")) is False

    async def test_a_missing_book_is_not_a_bid(self):
        """``None`` is not zero and must not be coerced to one in either
        direction: an absent bid is not a quote, and it must not raise."""
        assert fpr._venue_quotes_this_leg(_leg("0xnone")) is False


class TestTheFetchCountsWhatItDeclined:
    async def test_a_declined_leg_is_counted(self):
        stats: dict = {}
        event = _field("31552", [_priced_leg("0xvance", 0.241), _quoted_but_refused()])
        await fpr._fetch_polymarket_prices(
            _RetirementHarness(event).service, ["31552"], stats
        )
        assert stats["polymarket_legs_declined"] == 1

    async def test_the_leg_the_venue_is_quoting_lands_in_both_buckets(self):
        stats: dict = {}
        event = _field("31552", [_priced_leg("0xvance", 0.241), _quoted_but_refused()])
        await fpr._fetch_polymarket_prices(
            _RetirementHarness(event).service, ["31552"], stats
        )
        assert stats["polymarket_legs_declined"] == 1
        assert stats["polymarket_legs_declined_quoted"] == 1

    async def test_the_tombstone_lands_in_the_total_only(self):
        """🔴 The pair that makes the split load-bearing. Delete the
        ``_venue_quotes_this_leg`` call and the test above still passes; this one
        does not."""
        stats: dict = {}
        event = _field(
            "31552", [_priced_leg("0xvance", 0.241), _dead_leg("0xperson_bg")]
        )
        await fpr._fetch_polymarket_prices(
            _RetirementHarness(event).service, ["31552"], stats
        )
        assert stats["polymarket_legs_declined"] == 1
        assert stats["polymarket_legs_declined_quoted"] == 0

    async def test_a_priced_leg_counts_nothing(self):
        stats: dict = {}
        event = _field(
            "31552", [_priced_leg("0xvance", 0.241), _priced_leg("0xaoc", 0.084)]
        )
        await fpr._fetch_polymarket_prices(
            _RetirementHarness(event).service, ["31552"], stats
        )
        assert stats.get("polymarket_legs_declined", 0) == 0
        assert stats.get("polymarket_legs_declined_quoted", 0) == 0

    async def test_the_two_shapes_are_counted_apart_in_one_pass(self):
        """Both refusals in one field, because production never sends one shape
        at a time and a counter that is right on a pure batch can still be wrong
        on a mixed one."""
        stats: dict = {}
        event = _field(
            "31552",
            [
                _priced_leg("0xvance", 0.241),
                _quoted_but_refused(),
                _traded_but_refused(),
                _dead_leg("0xperson_bg"),
                _dead_leg("0xperson_cq"),
            ],
        )
        await fpr._fetch_polymarket_prices(
            _RetirementHarness(event).service, ["31552"], stats
        )
        assert stats["polymarket_legs_declined"] == 4
        assert stats["polymarket_legs_declined_quoted"] == 2


class TestTheSplitComposesWithTheRetirement:
    """The docstring's arithmetic, asserted rather than asserted-in-prose.

    ``_venue_quotes_this_leg`` is deliberately the same two facts
    ``_unpriced_leg_external_ids`` excludes a leg from retirement on. So on a
    negRisk field the legs this pass declined and did NOT call quoted are exactly
    the legs offered for retirement — and a later change that adds a third fact to
    one side without the other breaks this test, which is what it is for.
    """

    async def test_the_unquoted_remainder_is_the_retirement_list(self):
        stats: dict = {}
        event = _field(
            "31552",
            [
                _priced_leg("0xvance", 0.241),
                _quoted_but_refused(),
                _traded_but_refused(),
                _dead_leg("0xperson_bg"),
                _dead_leg("0xperson_cq"),
            ],
        )
        _, unpriced = await fpr._fetch_polymarket_prices(
            _RetirementHarness(event).service, ["31552"], stats
        )

        remainder = (
            stats["polymarket_legs_declined"] - stats["polymarket_legs_declined_quoted"]
        )
        assert remainder == 2
        assert sorted(unpriced["31552"]) == ["0xperson_bg", "0xperson_cq"]
        assert remainder == len(unpriced["31552"])


class _WriteSession:
    """The narrowest session ``_write_prices`` can run against.

    One outcome row, and every write recorded, so "the counter fired" and "the
    value was written anyway" are two separate assertions rather than one.
    """

    def __init__(self, rows=((11, "0xvance"),)):
        self.rows = list(rows)
        self.updates = 0
        self.inserts = 0

    async def execute(self, statement, params=None):
        sql = str(statement).lstrip().upper()
        if sql.startswith("SELECT ID, EXTERNAL_ID FROM FUTURES_OUTCOMES"):
            return _Result(self.rows)
        if sql.startswith("INSERT INTO FUTURES_ODDS_SNAPSHOTS"):
            self.inserts += 1
        elif sql.startswith("UPDATE FUTURES_OUTCOMES"):
            self.updates += 1
        return _Result(rowcount=1)


class TestTheWriterCountsTheValueItRefused:
    """The second silent ``continue``, and it is reachable in production.

    ``_resolve_market_probability`` returns ``outcome_prices[0]`` whenever it is
    above zero, and the ``0.05 < p < 0.95`` evidence gate does not apply at the
    ends — so a settled Polymarket field, whose losing legs quote ``1`` on their
    own No token (the #2222 shape), hands ``1.0`` down the price rail. The fetch
    passes it (``prob <= 0`` is the only test there) and the writer refuses it.
    Before this, that refusal left the row's old number standing and said nothing.
    """

    async def test_a_certainty_arriving_down_the_price_rail_is_counted(self):
        session = _WriteSession()
        stats: dict = {}
        written = await fpr._write_prices(
            session, 112897, "polymarket", [{"external_id": "0xvance",
                                             "probability": 1.0}], stats
        )
        assert stats["legs_declined_out_of_range"] == 1
        assert written == 0
        assert session.updates == 0, "a refused value must not reach the row"
        assert session.inserts == 0

    async def test_a_price_inside_the_range_is_written_and_not_counted(self):
        """The control. Without it the assertion above is satisfied by a writer
        that refuses everything."""
        session = _WriteSession()
        stats: dict = {}
        written = await fpr._write_prices(
            session, 112897, "polymarket", [{"external_id": "0xvance",
                                             "probability": 0.241}], stats
        )
        assert stats.get("legs_declined_out_of_range", 0) == 0
        assert written == 1
        assert session.updates == 1


class TestTheRunReportsIt:
    """🔴 The guard that makes the optional ``stats`` argument safe.

    ``_fetch_polymarket_prices`` takes ``stats`` as a keyword with a ``None``
    default so the fifteen existing call sites keep working, and a default like
    that is exactly how a counter ships inert — the #4000 lesson one file over,
    where every helper passed and the run retired nothing. These drive the real
    entry point, so a production path that stopped threading ``stats`` reds here.
    """

    async def test_the_summary_carries_the_decline_it_made(self, monkeypatch):
        harness = _RetirementHarness(
            _field(
                "31552",
                [
                    _priced_leg("0xvance", 0.241),
                    _quoted_but_refused("0xperson_bg"),
                    _dead_leg("0xperson_cq"),
                ],
            )
        )
        summary = await harness.run(monkeypatch)

        assert summary["polymarket_legs_declined"] == 2
        assert summary["polymarket_legs_declined_quoted"] == 1

    async def test_a_pass_that_declined_nothing_reports_zero_not_nothing(
        self, monkeypatch
    ):
        """Gotcha #53, and the reason every refusal counter in this task is
        unconditional: "nothing was declined" and "the counter never ran" must
        not arrive as the same empty summary."""
        harness = _RetirementHarness(
            _field(
                "31552",
                [_priced_leg("0xvance", 0.241), _priced_leg("0xaoc", 0.084)],
            )
        )
        summary = await harness.run(monkeypatch)

        assert summary["polymarket_legs_declined"] == 0
        assert summary["polymarket_legs_declined_quoted"] == 0
        assert summary["legs_declined_out_of_range"] == 0

    async def test_the_counters_do_not_disturb_the_prices_the_pass_wrote(
        self, monkeypatch
    ):
        """A reporting change must be observably inert on the writes. Asserted on
        the write set rather than on the absence of an exception."""
        harness = _RetirementHarness(
            _field(
                "31552",
                [
                    _priced_leg("0xvance", 0.241),
                    _priced_leg("0xaoc", 0.084),
                    _dead_leg("0xperson_bg"),
                ],
            )
        )
        summary = await harness.run(monkeypatch)

        assert sorted(harness.priced_writes) == pytest.approx([0.084, 0.241])
        assert summary["legs_retired"] == 1

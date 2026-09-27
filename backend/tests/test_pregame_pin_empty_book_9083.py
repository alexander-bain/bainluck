"""#9083, the pin half: a Polymarket leg on an empty book is not pinned as THE SCRIPT.

THE SPECIMEN. ``/events/15319167`` led its props rail with "Turner's 1+ hits + runs
+ rbis was marked 1% — and it hit". The 1% was an opening promoted from a book of
bid NULL / ask 1.00 / last 0.01, and PR #9085 guards that promotion. ux found the
sibling path (issue comment 5853980662): the live poller's pregame pin
(``market_metadata["pregame_mark"]``) copies ``current_probability`` with no book
check, and ``_resolve_pregame_mark`` prefers the pin over the opening. Turner's
market had no pin, so this path did not paint that row. The same book pinned would
paint the same 1%, and the pin stores no bid or ask, so nothing downstream could
refuse it. The writer has to.

The rule is imported from ``app.utils.polymarket_empty_book`` and not restated
here. These arms pin how the WRITER uses it: which legs leave the pin, what
happens when every leg leaves, and that Kalshi is untouched.
"""

from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.tasks import prediction_market_matching as pmm
from app.tasks.prediction_market_matching import (
    _PREGAME_MARK_LEAD_MINUTES,
    _pregame_pin_outcome_probs,
)
from tests.test_live_poll_commit_boundary_5682 import (
    _Event,
    _Market,
    _now,
    _Outcome,
    _PolyService,
    _Population,
    _Session,
    _run,
)


def _leg(oid, prob, bid, ask):
    return SimpleNamespace(
        id=oid, current_probability=prob, current_yes_bid=bid, current_yes_ask=ask
    )


# The specimen's two legs as the poller holds them: the Over read off the venue
# (bid absent, ask a dollar, 1c trade) and the Under as its complementary book.
TURNER_OVER = _leg(236480965, 0.01, None, 1.0)
TURNER_UNDER = _leg(236480966, 0.99, 0.0, None)


class TestTheWriterRefusesTheSpecimen:
    def test_neither_leg_of_the_turner_book_is_pinned(self):
        probs, refused = _pregame_pin_outcome_probs(
            "polymarket", [TURNER_OVER, TURNER_UNDER]
        )
        assert probs == {}
        assert refused == 2

    def test_the_same_legs_were_pinned_before_this_change(self):
        """Non-vacuity. The pre-#9083 writer, transcribed: every leg with a
        probability went into the pin. Without this arm the one above could pass
        on legs that no writer would ever have pinned."""
        shipped = {
            str(o.id): round(float(o.current_probability), 6)
            for o in (TURNER_OVER, TURNER_UNDER)
            if o.current_probability is not None
        }
        assert shipped == {"236480965": 0.01, "236480966": 0.99}


class TestWhatTheWriterStillPins:
    def test_a_two_sided_polymarket_book_is_pinned_verbatim(self):
        probs, refused = _pregame_pin_outcome_probs(
            "polymarket", [_leg(1, 0.585, 0.58, 0.59), _leg(2, 0.415, 0.41, 0.42)]
        )
        assert probs == {"1": 0.585, "2": 0.415}
        assert refused == 0

    def test_a_lone_bid_and_a_lone_ask_are_not_this_rule(self):
        """The helper module's census: lone bids grade near their level, and a
        Polymarket lone ask is not this defect. Both stay in the pin."""
        probs, refused = _pregame_pin_outcome_probs(
            "polymarket", [_leg(1, 0.94, 0.93, None), _leg(2, 0.05, None, 0.06)]
        )
        assert probs == {"1": 0.94, "2": 0.05}
        assert refused == 0

    def test_a_leg_with_no_recorded_book_is_not_refused(self):
        """No book recorded is not an empty book (gotcha #53)."""
        probs, refused = _pregame_pin_outcome_probs(
            "polymarket", [_leg(1, 0.3, None, None)]
        )
        assert probs == {"1": 0.3}
        assert refused == 0

    def test_only_the_empty_leg_leaves_a_mixed_market(self):
        """A refused leg is LEFT OUT, not the whole market. The reader falls back
        to that leg's opening while its priced siblings keep their pin."""
        probs, refused = _pregame_pin_outcome_probs(
            "polymarket",
            [_leg(1, 0.62, 0.61, 0.63), _leg(2, 0.01, None, 1.0)],
        )
        assert probs == {"1": 0.62}
        assert refused == 1

    def test_the_tick_bounds_are_pinned_on_both_sides(self):
        """A 1c bid and a 99c ask is empty; a 2c bid or a 98c ask is a quote."""
        assert (
            _pregame_pin_outcome_probs("polymarket", [_leg(1, 0.5, 0.01, 0.99)])[1] == 1
        )
        assert (
            _pregame_pin_outcome_probs("polymarket", [_leg(1, 0.5, 0.02, 0.99)])[1] == 0
        )
        assert (
            _pregame_pin_outcome_probs("polymarket", [_leg(1, 0.5, 0.01, 0.98)])[1] == 0
        )

    def test_kalshi_legs_are_out_of_scope(self):
        """CERT-2508: this is Polymarket's policy. The same columns on a Kalshi
        row are not judged by it."""
        probs, refused = _pregame_pin_outcome_probs("kalshi", [TURNER_OVER])
        assert probs == {"236480965": 0.01}
        assert refused == 0

    def test_a_leg_with_no_probability_is_skipped_as_before(self):
        probs, refused = _pregame_pin_outcome_probs(
            "polymarket", [_leg(1, None, None, 1.0)]
        )
        assert probs == {}
        assert refused == 0

    def test_a_decimal_book_is_read_like_a_float(self):
        """Production hands the Numeric(5,4) columns back as Decimal."""
        from decimal import Decimal

        probs, refused = _pregame_pin_outcome_probs(
            "polymarket", [_leg(1, Decimal("0.010000"), None, Decimal("1.0000"))]
        )
        assert (probs, refused) == ({}, 1)


# --------------------------------------------------------------------------
# through the REAL poll: venue payload in, pin SQL out
# --------------------------------------------------------------------------


def _poly_payload(condition_id, *, prices, last, bid, ask):
    market = {
        "conditionId": condition_id,
        "outcomePrices": prices,
        "outcomes": '["Yes", "No"]',
        "lastTradePrice": last,
        "bestAsk": ask,
    }
    if bid is not None:
        market["bestBid"] = bid
    return {"markets": [market]}


class TestThroughTheLivePoll:
    async def test_the_empty_book_market_gets_no_pin_and_its_sibling_does(
        self, monkeypatch
    ):
        journal = []
        commence = _now() + timedelta(minutes=_PREGAME_MARK_LEAD_MINUTES / 2)
        beat = _Population(
            [
                (
                    _Market(i, "polymarket", f"poly-evt-{i}"),
                    _Event(300 + i, commence=commence),
                )
                for i in (1, 2)
            ],
            [_Outcome(3000 + i, i, f"cond-{i}", "Los Angeles R") for i in (1, 2)],
        )
        session = _Session([beat, beat], journal=journal)
        poly = _PolyService(
            {
                # The specimen's book: no bid, the ask at a dollar, one 1c trade.
                "poly-evt-1": _poly_payload(
                    "cond-1", prices='["0.01", "0.99"]', last=0.01, bid=None, ask=1.0
                ),
                "poly-evt-2": _poly_payload(
                    "cond-2", prices='["0.62", "0.38"]', last=0.62, bid=0.61, ask=0.63
                ),
            },
            journal,
        )

        pins: list[dict] = []
        real_execute = session.execute

        async def _recording_execute(stmt, params=None):
            if "pregame_mark" in str(stmt) and params:
                pins.append(params)
            return await real_execute(stmt, params)

        session.execute = _recording_execute

        stats = await _run(monkeypatch, session, poly=poly)

        # Precondition: the poll DID price the empty-book leg, so the refusal
        # below is the pin guard and not a pricing-side skip.
        empty_leg = [o for o in beat.outcomes if o.market_id == 1][0]
        assert empty_leg.current_probability == pytest.approx(0.01, abs=1e-4)
        assert empty_leg.current_yes_bid is None
        assert float(empty_leg.current_yes_ask) == 1.0

        assert [p["id"] for p in pins] == [2], f"pins written: {pins}"
        assert '"3002": 0.62' in pins[0]["mark"]
        assert stats["pregame_marks_written"] == 1
        assert stats["pregame_mark_empty_book_legs_refused"] == 1

    def test_the_writer_calls_the_guard(self):
        """The helper arms cannot see whether the loop still calls it."""
        import inspect

        src = inspect.getsource(pmm._poll_live_prediction_market_prices)
        assert "_pregame_pin_outcome_probs(" in src

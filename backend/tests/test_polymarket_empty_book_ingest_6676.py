"""#6676 ingest half: an empty Polymarket book is never WRITTEN as a 50% forecast.

The serve half (`test_grouped_feed_empty_book_6676.py`, merged 2026-09-17) stops the
already-stored rows reaching a /sports card. This file is the other end: the writer
that produced them.

WHY THE WRITER ESCAPED ITS OWN GUARD. `_resolve_market_probability_with_source` and
the non-negRisk branch of `_parent_outcome_data` both apply `is_fabricated_midpoint`,
whose midpoint test is an EXACT equality (tolerance 0.0005). Gamma's payload is not one
instant: `outcomePrices` and `bestBid`/`bestAsk` can be a tick apart in the same
response, which puts the price half a cent off the arithmetic mean and past that
tolerance — and the 2c bid then satisfies the #151 evidence gate, so the row is stored
as a 50% `outcome_prices` forecast. The fix pairs the shipped #5247 predicate
`is_empty_book_midpoint` (tolerance 0.01) with it at both sites.

✅ THE 3c REMAINDER IS CLOSED AND `TestWhatThisFixDidNotReachUntil5333` RECORDS THE
FLIP. `EMPTY_BOOK_MAX_BID` was 0.02, so a **3c** bid escaped both predicates; #5333
moved it to 0.05 on its own production measurement (2026-09-17) and those tests now
assert the close instead of the escape. The bound's own guard tests live in
`test_empty_book_bid_bound_5333.py`, including the cost the move pays.

#12658: open quotes now require a usable two-sided book. An undated trade and
24-hour volume cannot prove a current price; the updated controls make that
policy change explicit. Settlement remains a separate, closed-market path.

Nothing is re-implemented here: every case runs the production parser
(`PolymarketAPIService._parse_market` / `_parse_event`) and the production selectors.
The raw-Gamma fixture helper and several payloads are taken from the independent
diagnostic in `artifacts/other-model-sports-price-provenance/`, whose LIVE captures
were served by gamma-api.polymarket.com on 2026-09-17 between 03:41Z and 03:48Z.

RED-FIRST, on master `f257af838` before the fix: the three cases in
`TestAnEmptyBookIsNotAForecast` fail (the selector returns `(0.5, 'outcome_prices')`
and the parent leg is written); every `TestGenuinePricesSurvive` case already passes
and must keep passing.
"""
import inspect
import json

import pytest

from app.services.polymarket_api import PolymarketAPIService
from app.tasks import polymarket
from app.tasks.polymarket import (
    _parent_outcome_data,
    _resolve_market_probability_with_source,
)
from app.utils.feed_market_quality import (
    EMPTY_BOOK_MAX_BID,
    EMPTY_BOOK_MIN_ASK,
    is_empty_book_midpoint,
)


def _gamma(question, prices, bid, ask, last=None, vol24=None, cond="0xtest", **extra):
    """A raw Gamma market dict in the venue's own encoding (stringified arrays)."""
    raw = {
        "conditionId": cond,
        "question": question,
        "outcomes": json.dumps(["Over", "Under"]),
        "outcomePrices": json.dumps([str(p) for p in prices]) if prices is not None else None,
        "clobTokenIds": json.dumps(["1", "2"]),
        "bestBid": bid,
        "bestAsk": ask,
        "lastTradePrice": last,
        "volume24hr": vol24,
        "active": True,
        "closed": False,
        "acceptingOrders": True,
        "negRisk": False,
    }
    raw.update(extra)
    return raw


def _select(raw):
    market = PolymarketAPIService()._parse_market(raw)
    assert market is not None, "the production parser refused the payload"
    return _resolve_market_probability_with_source(market)


def _parent_legs(*markets, title="Cavalry FC vs. Forge FC Hamilton - Total Corners"):
    """Drive the non-negRisk multi-market branch of `_parent_outcome_data`.

    More than one market and `negRisk` false is what selects that branch; it is the
    one that takes Gamma's `outcome_prices[0]` raw, and it is a DIFFERENT call site
    from the resolver above. Outcome 61246705 reached a /sports card through here.
    """
    event = PolymarketAPIService()._parse_event(
        {"id": "1035459", "title": title, "negRisk": False, "active": True,
         "markets": list(markets)}
    )
    assert event is not None, "the production parser refused the event"
    return {leg["external_id"]: leg["prob"] for leg in _parent_outcome_data(event)}


#: The shape actually STORED on the three named outcomes (230498576 / 230496527 /
#: 230475436, read read-only 2026-09-17): probability 0.500000 against a 0.0200 bid and
#: a 0.9700 ask, whose own midpoint is 0.495. Half a cent of skew, and no trade.
STORED_SKEW = dict(bid=0.02, ask=0.97)

#: A real two-sided quote on a market nobody has traded, LIVE market 4629920 / outcome
#: 61260583. It is shown as roughly 28 / 72 and must stay that way: no trade is not no
#: quote. Every declining test below carries it as a same-event control so a pass can
#: never be "the branch dropped everything".
CONTROL = _gamma("control: W15 Sao Luis", [0.28, 0.72], 0.25, 0.31, cond="0xcontrol")


class TestAnEmptyBookIsNotAForecast:
    """The defect, at both write sites. These are the red-first cases."""

    def test_the_stored_skew_is_declined_by_the_resolver(self):
        """Sub-market path — outcomes 61254969 and 61253744 were written here."""
        assert _select(
            _gamma("Jagiellonia: O/U 9.5 Total Corners", [0.5, 0.5], **STORED_SKEW)
        ) == (None, None)

    def test_the_stored_skew_is_declined_on_the_parent_anchor(self):
        """Parent path — outcome 61246705 was written here, NOT by the resolver.

        Guarding only the resolver would have fixed two of the three named rows and
        left the third printing 50% on the same page.
        """
        skew = _gamma(
            "Cavalry: O/U 13.5 Total Corners", [0.5, 0.5], cond="0xskew",
            groupItemTitle="Total Corners: O/U 13.5", **STORED_SKEW,
        )
        assert _parent_legs(skew, CONTROL) == {"0xcontrol": 0.28}

    @pytest.mark.parametrize("bid,ask", [(0.03, 0.97), (0.02, 0.98), (0.01, 0.99)])
    def test_an_exact_empty_book_midpoint_stays_declined(self, bid, ask):
        """Already declined before this fix, by `is_fabricated_midpoint`.

        Pinned because the whole risk of adding a second predicate is that it
        reshuffles what the first one caught. 206 of the 209 wide-book markets in the
        diagnostic's 03:41Z scan of 2,000 were this shape.
        """
        assert _select(_gamma("exact mid", [0.5, 0.5], bid, ask)) == (None, None)


class TestGenuinePricesSurvive:
    """Supported quotes survive; #12658 refuses undated trade controls."""

    def test_a_quoted_coin_flip_on_a_tight_book(self):
        """A real 50%: 49c bid / 51c ask, never traded. The book bounds it."""
        assert _select(_gamma("tight", [0.5, 0.5], 0.49, 0.51)) == (0.5, "outcome_prices")

    def test_recent_volume_does_not_date_an_empty_book_trade(self):
        assert _select(
            _gamma("traded", [0.5, 0.5], last=0.5, vol24=120.0, **STORED_SKEW)
        ) == (None, None)

    def test_the_parent_also_refuses_that_undated_trade(self):
        traded = _gamma(
            "traded parent", [0.5, 0.5], last=0.5, vol24=120.0, cond="0xtraded",
            groupItemTitle="Total Corners: O/U 13.5", **STORED_SKEW,
        )
        assert _parent_legs(traded, CONTROL) == {"0xcontrol": 0.28}

    def test_a_stale_trade_with_no_recent_volume_is_still_declined(self):
        """No volume cannot rescue a trade; positive volume cannot date it either."""
        assert _select(
            _gamma("stale trade", [0.5, 0.5], last=0.5, vol24=None, **STORED_SKEW)
        ) == (None, None)

    def test_a_live_quoted_favourite_that_never_traded(self):
        """LIVE 4629920 / outcome 61260583 — the control the after-check reads."""
        assert _select(CONTROL) == (0.28, "outcome_prices")

    def test_a_raw_line_on_a_wide_book_is_not_a_current_quote(self):
        """0.78 on 8c/97c. Wide, but the price is nowhere near the midpoint."""
        assert _select(_gamma("7+ corners", [0.78, 0.22], 0.08, 0.97)) == (None, None)

    def test_a_real_bid_alone_does_not_make_a_usable_quote(self):
        """0.5 on 20c/98c. A 20c bid is a real one; only the midpoint clause of
        `is_fabricated_midpoint` (0.59 here, not 0.5) can speak to it, and it does not."""
        assert _select(_gamma("real bid", [0.5, 0.5], 0.20, 0.98)) == (None, None)

    def test_a_polymarket_raw_price_with_no_book_is_declined(self):
        """Both sides null — DataGolf, odds_api, a derived complement. Neither
        predicate applies, by construction rather than by exemption. It is declined
        here only by the #151 evidence gate, which is not this fix."""
        assert is_empty_book_midpoint(0.5, None, None) is False

    def test_a_settled_leg_is_untouched(self):
        """0.99 on the empty book: outside the geometric band, so nothing here can
        reach a settled 0/1 price."""
        assert _select(_gamma("settled", [0.99, 0.01], last=0.99, vol24=5.0, closed=True, **STORED_SKEW)) == (
            0.99, "outcome_prices"
        )

    def test_a_lone_ask_is_declined_since_9157(self):
        """🪤 FLIPPED by #9157. This asserted the lone ask KEPT (`(0.36, "best_ask")`).
        `is_empty_book_midpoint` still cannot reach it (it needs BOTH sides) — the
        resolver's ask-only fallback is what published it, and #9157 removed that
        branch under gotcha #19 (no trade and no bid → skip)."""
        assert _select(_gamma("lone ask", None, None, 0.36)) == (None, None)


class TestWhatThisFixDidNotReachUntil5333:
    """🪤 THE FLIP. These three asserted the escape OPEN; #5333 closed it and they
    now assert the close. The class was written so its own remainder could not be
    absorbed silently, and this is the PR coming back to say what it changed.

    Before (#6676, 2026-09-17 0500Z): `EMPTY_BOOK_MAX_BID` 0.02, inclusive — the 2c
    books we stored were caught and the diagnostic's own live specimen (Gamma
    4630453, 03:43Z, price 0.5 on 0.03 / 0.98) was still WRITTEN.
    After (#5333, same day): the bound is 0.05 on its own production measurement —
    1,119 rows in (0.02, 0.05] sitting on their midpoint, price range 0.490-0.525,
    inside the derived band [0.465, 0.535]. The specimen is now declined.
    """

    def test_the_bound_is_five_cents(self):
        assert (EMPTY_BOOK_MAX_BID, EMPTY_BOOK_MIN_ASK) == (0.05, 0.95)

    def test_a_three_cent_bid_no_longer_escapes(self):
        assert is_empty_book_midpoint(0.5, 0.03, 0.98) is True

    def test_the_live_three_cent_specimen_is_no_longer_written(self):
        """The shape #6676 measured live and could not take. It is taken now."""
        assert _select(_gamma("Set Handicap", [0.5, 0.5], 0.03, 0.98)) == (None, None)

    def test_the_bound_is_inclusive_at_five_cents_and_open_at_a_short_spread(self):
        """Where the new edge is, asserted on the side the WIDTH decides.

        Both rows sit EXACTLY on their own midpoint, so the tolerance cannot be
        what separates them — only the bound can. A tolerance-decided pair
        here would be a vacuous boundary test.

        #6727 flipped the second assertion: it read `0.06/0.97 is False`, keeping a
        91-cent-wide book because the bid missed by a cent. The separator is the
        spread now, so the short book is the one that is kept.
        """
        assert is_empty_book_midpoint((0.05 + 0.97) / 2, 0.05, 0.97) is True
        assert is_empty_book_midpoint((0.06 + 0.95) / 2, 0.06, 0.95) is False
        assert is_empty_book_midpoint((0.06 + 0.97) / 2, 0.06, 0.97) is True


class TestTheGuardIsActuallyAtBothCallSites:
    """Reach, not reasoning. Every behavioural case above could pass against a route
    that never calls the new predicate if the payload were declined for some other
    reason — so read the two functions' own source and assert the call is in each.
    """

    def test_the_resolver_calls_both_predicates(self):
        src = inspect.getsource(polymarket._resolve_market_probability_with_source)
        assert "is_fabricated_midpoint(" in src
        assert "is_empty_book_midpoint(" in src

    def test_the_parent_anchor_uses_the_shared_resolver(self):
        src = inspect.getsource(polymarket._parent_outcome_data)
        assert "_resolve_market_probability(market)" in src
        assert "prob = market.outcome_prices[0]" not in src

    def test_the_predicate_is_imported_not_restated(self):
        """One meaning of "untradeable" in this codebase. If a future edit inlines the
        thresholds here, the serve side and the calibration SQL mirror drift from the
        writer and nothing catches it."""
        src = inspect.getsource(polymarket)
        assert "from app.utils.feed_market_quality import" in src
        assert "EMPTY_BOOK_MAX_BID = " not in src
        assert "EMPTY_BOOK_MIN_ASK = " not in src

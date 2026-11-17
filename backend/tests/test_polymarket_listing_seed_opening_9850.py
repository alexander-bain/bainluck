"""#9850 — a 1c bid on a book that bounds nothing does not stamp an opening.

Specimen: market 63386735, "Trammell 1+ home runs" (White Sox @ Astros, WC Game 2),
listed 2026-09-30 06:16:11Z. The listing snapshot reads price 0.475 / 0.525 beside a
0.01 / 0.99 book with no trade. The decomposed sub-market writer counted the 1c bid
as trading, both phantom predicates missed a price 2.5c off the midpoint, and the
pair summed to 1 — so 0.475 became the opening, and "The script" led the event page
with "opened at 47% — it's 5% now".

The rail tests START the real ``_process_event_batch`` over the recording fake
session from the #2027 file (ruling 102). Refused legs keep their current price;
two controls prove the clause is not refusing everything.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.polymarket_api import PolymarketAPIService
from app.tasks import polymarket as poly
from tests.test_polymarket_hindsight_opening_refused_2027 import (
    _insert_values,
    _legs_by_external_id,
    _outcome_inserts,
    _run_batch,
)

# #12252: the venue's end date must stay in the FUTURE for this market to be open.
# It was the literal 2026-12-01, which the calendar reaches (timebomb_confirm: red
# from +31 d on 2026-11-07). Derived from the clock: offset first, then truncate.
OPEN_END_DATE = (datetime.now(timezone.utc) + timedelta(days=90)).replace(
    hour=0, minute=0, second=0, microsecond=0
).strftime("%Y-%m-%dT%H:%M:%SZ")


class TestOpeningBookIsEmpty:
    def test_the_specimen_book_is_empty(self):
        assert poly._opening_book_is_empty(0.01, 0.99, None) is True

    def test_a_trade_exempts(self):
        assert poly._opening_book_is_empty(0.01, 0.99, 0.475) is False

    def test_a_zero_trade_is_no_trade(self):
        assert poly._opening_book_is_empty(0.01, 0.99, 0) is True

    def test_a_tradeable_book_is_not_empty(self):
        assert poly._opening_book_is_empty(0.45, 0.50, None) is False

    def test_a_bid_with_no_ask_is_the_widest_quote(self):
        assert poly._opening_book_is_empty(0.01, None, None) is True

    def test_no_bid_is_left_to_the_trading_test(self):
        # Without a bid or a trade `sub_has_trading` is already False; this helper
        # only narrows what that flag lets through.
        assert poly._opening_book_is_empty(None, 0.99, None) is False

    @pytest.mark.parametrize(
        "bid, ask, empty",
        [
            (0.05, 0.95, True),  # spread exactly 0.90 — the shared constant
            (0.06, 0.95, False),  # 0.89 locates something
        ],
    )
    def test_the_boundary_is_the_shared_constant(self, bid, ask, empty):
        assert poly._opening_book_is_empty(bid, ask, None) is empty


def _venue_game_event(*, bid, ask, last_trade, price=0.475):
    """Two sub-markets, so the writer takes the DECOMPOSED path the specimen took."""

    def _sub(idx, question):
        return {
            "id": f"m-9850-{idx}",
            "conditionId": f"0x9850game{idx}",
            "question": question,
            "slug": f"white-sox-astros-{idx}",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": f'["{price}", "{round(1 - price, 6)}"]',
            "clobTokenIds": f'["{idx}11", "{idx}22"]',
            "bestBid": bid,
            "bestAsk": ask,
            "lastTradePrice": last_trade,
            "closed": False,
        }

    return {
        "id": "evt-9850-game",
        "title": "White Sox vs. Astros",
        "slug": "white-sox-vs-astros-9850",
        "active": True,
        "closed": False,
        "archived": False,
        "endDate": OPEN_END_DATE,
        "startDate": "2026-09-30T23:00:00Z",
        "negRisk": False,
        "markets": [
            _sub(1, "White Sox vs. Astros"),
            _sub(2, "Tyler Trammell: 1+ home runs"),
        ],
    }


def _parsed_game(**kwargs):
    event = PolymarketAPIService()._parse_event(_venue_game_event(**kwargs))
    assert event is not None, "the parser refused a venue-shaped payload"
    assert len(event.markets) > 1 and not event.neg_risk, (
        "this fixture must reach the DECOMPOSED path"
    )
    return event


LEGS = ("0x9850game1_yes", "0x9850game1_no", "0x9850game2_yes", "0x9850game2_no")


class TestTheRailRefusesTheListingSeed:
    @staticmethod
    def _assert_no_price_or_opening(fake, stats):
        # #12658 refuses the unsupported quote before child price/opening
        # writes. Parent placeholders preserve the two known market identities.
        inserts = _outcome_inserts(fake)
        assert inserts
        assert stats["unpriced_legs_recorded"] == 2
        assert stats["events_processed"] == 1
        for statement in inserts:
            values = _insert_values(statement)
            price_fields = {key: value for key, value in values.items() if key.startswith((
                "current_probability", "opening_probability", "opening_captured_at",
                "opening_american_odds",
            ))}
            assert price_fields, values
            assert all(value is None for value in price_fields.values()), price_fields
        assert not any(
            getattr(getattr(statement, "table", None), "name", None) == "futures_odds_snapshots"
            for statement in fake.statements
        )

    async def test_the_specimen_banks_no_opening_on_either_leg(self, monkeypatch):
        event = _parsed_game(bid=0.01, ask=0.99, last_trade=None)
        fake, stats = await _run_batch(monkeypatch, event)
        self._assert_no_price_or_opening(fake, stats)

    async def test_a_tradeable_book_still_opens_both_legs(self, monkeypatch):
        """Non-vacuity: a clause that refused everything would pass the above."""
        event = _parsed_game(bid=0.45, ask=0.50, last_trade=None)
        fake, stats = await _run_batch(monkeypatch, event)
        legs = _legs_by_external_id(fake)
        assert legs["0x9850game2_yes"]["opening_probability"] == 0.475
        assert legs["0x9850game2_no"]["opening_probability"] == 0.525
        assert legs["0x9850game2_no"]["opening_captured_at"] is not None
        assert stats.get("opening_refused_empty_book", 0) == 0

    async def test_an_empty_book_with_an_undated_trade_does_not_open(self, monkeypatch):
        """A last trade without its time does not rescue an unusable book."""
        event = _parsed_game(bid=0.01, ask=0.99, last_trade=0.475)
        fake, stats = await _run_batch(monkeypatch, event)
        self._assert_no_price_or_opening(fake, stats)

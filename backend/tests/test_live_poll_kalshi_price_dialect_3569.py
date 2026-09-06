"""The 2-minute live poll speaks the venue's CURRENT price dialect (#3569).

## the defect

`_poll_live_prediction_market_prices` fetches Kalshi prices with
`KalshiAPIService.get_markets`, which — alone among our Kalshi calls — returns
the venue's RAW JSON rather than parsed `KalshiMarket` objects. The branch read
`mkt_data.get("yes_bid")`, `.get("yes_ask")` and `.get("last_price")` off those
dicts and divided by 100.

The venue does not emit those keys. Not stale ones, not null ones — the keys are
ABSENT. Measured against the live endpoint 2026-09-06 14:40Z (the capture in
`tests/fixtures/kalshi_markets_endpoint_20260906.json` is that response,
verbatim): an open NFL game market carries `yes_bid_dollars` `'0.2200'`,
`yes_ask_dollars` `'0.2300'`, `last_price_dollars` `'0.2300'`, `volume_fp`, and
no cent-based key of any name.

So all three reads returned None on every market, every beat, and the branch
fell straight through to its `else: continue` — silently, while `kalshi_fetched`
went on counting the request it had just wasted. Production, same window, inside
this one function's own scope (markets linked to live or ≤3h-away events):
Polymarket **4,910** snapshots across **54 distinct minutes**; Kalshi **0 rows,
bookmaker absent from the result entirely** — against a live population of 34
Kalshi markets / 19 events / 177 outcomes that the task fetched and discarded.

## what these arms hold down

The repair routes the raw dicts through the service's own parser
(`parse_markets`) and prices them with the 2-hour poll's `_kalshi_yes_probability`
policy, so there is exactly one dialect and one price rule per venue. The risks
that survive that repair are the ones with arms here:

* **The scale.** `*_dollars` are already DECIMAL probabilities — `'0.6200'` is
  0.62, not 62. "Converting cents" a second time yields 0.0062, which is still
  inside `0 < p < 1`, so it stores, charts and blends without ever raising.
* **The fallback.** The cent fields are the documented OLD format. Dropping
  their handling to "simplify" would re-break this the day the venue serves an
  older shape, so an arm pins the cascade in both directions.
* **The dialect returning.** A source scan fails if the cent keys are ever read
  off a raw dict again — and the scan is fired at the pre-fix expression
  verbatim to prove it discriminates rather than merely passing.

The round trip — venue payload in, priced row and chart snapshot out of a real
server — is `tests/integration/test_live_poll_kalshi_prices_real_postgres.py`.
This file is the fast half and runs in the ordinary suite.
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from app.services.kalshi_api import KalshiAPIService
from app.tasks.kalshi import _kalshi_yes_probability

FIXTURE = (
    Path(__file__).parent / "fixtures" / "kalshi_markets_endpoint_20260906.json"
)

#: The venue's own bytes. Keyed by ticker rather than by position — the venue
#: does not promise an order (see `get_markets_candlesticks_raw`'s warning).
CAPTURED = {m["ticker"]: m for m in json.loads(FIXTURE.read_text())["markets"]}

NYG = "KXNFLGAME-26SEP21NYGLAR-NYG"
LAR = "KXNFLGAME-26SEP21NYGLAR-LAR"

#: The pre-fix expression, verbatim from the blame of
#: `_poll_live_prediction_market_prices`. Kept as text so the source scan below
#: can be fired at the shape it exists to block (a scan never run against
#: failing code is only a claim that it would fail).
PRE_FIX_SOURCE = '''
                        for mkt_data in markets_data:
                            yes_bid = mkt_data.get("yes_bid")
                            yes_ask = mkt_data.get("yes_ask")
                            last_price = mkt_data.get("last_price")

                            # Kalshi prices are in cents (0-100)
                            if yes_bid is not None:
                                yes_bid = yes_bid / 100.0
'''

#: A read of a cent-era price key off a raw venue dict.
_CENT_DIALECT = re.compile(r"""\.get\(\s*["'](yes_bid|yes_ask|last_price)["']""")


@pytest.fixture(scope="module")
def service():
    """A real service object. Construction opens an httpx client and touches no
    network; `parse_markets` is pure, so one instance serves every arm."""
    svc = KalshiAPIService(api_key="not-used-by-the-parser")
    yield svc


def _live_poll_source() -> str:
    from app.tasks.prediction_market_matching import (
        _poll_live_prediction_market_prices,
    )

    return inspect.getsource(_poll_live_prediction_market_prices)


class TestTheCapturedPayloadIsWhatTheVenueSends:
    """The premise every other arm rests on, asserted rather than assumed."""

    def test_the_capture_holds_both_legs_of_a_real_event(self):
        assert set(CAPTURED) == {NYG, LAR}, (
            "the capture must be the two-leg NFL event it documents; a re-capture "
            f"that changed shape invalidates the expected prices below. got: {sorted(CAPTURED)}"
        )

    @pytest.mark.parametrize("ticker", [NYG, LAR])
    @pytest.mark.parametrize("cent_key", ["yes_bid", "yes_ask", "last_price"])
    def test_the_cent_era_keys_are_absent_not_null(self, ticker, cent_key):
        assert cent_key not in CAPTURED[ticker], (
            f"{cent_key} is present in the captured venue response — the whole "
            "premise of #3569 is that the venue stopped sending it. If the venue "
            "restored it, this capture is no longer the payload the bug was "
            "measured against and the fixture must be re-dated, not edited."
        )

    def test_the_dollar_fields_are_the_only_price_channel(self):
        m = CAPTURED[NYG]
        assert (m["yes_bid_dollars"], m["yes_ask_dollars"], m["last_price_dollars"]) == (
            "0.2200",
            "0.2300",
            "0.2300",
        ), "the expected probabilities below are derived from these three strings"


class TestTheParserReadsTheVenuesDialect:
    """`parse_markets` is the seam the poll now goes through."""

    def test_the_dollar_strings_become_decimal_probabilities(self, service):
        parsed = {m.ticker: m for m in service.parse_markets(list(CAPTURED.values()))}

        assert parsed[NYG].yes_bid == pytest.approx(0.22)
        assert parsed[NYG].yes_ask == pytest.approx(0.23)
        assert parsed[NYG].last_price == pytest.approx(0.23)
        assert parsed[LAR].yes_bid == pytest.approx(0.76)

    def test_a_dollar_string_is_not_divided_by_a_hundred(self, service):
        """0.0022 is the failure this arm exists for, and it never raises."""
        parsed = service.parse_markets([CAPTURED[NYG]])[0]

        assert parsed.yes_bid > 0.1, (
            f"yes_bid came back {parsed.yes_bid} — a *_dollars string treated as "
            "cents and divided again. It is still inside 0 < p < 1, so nothing "
            "downstream would have complained; a 22% team would just chart at 0.2%."
        )

    def test_the_old_cent_format_still_parses(self, service):
        """The documented fallback. A venue that serves the old shape must still price."""
        old_shape = {
            "ticker": NYG,
            "event_ticker": "KXNFLGAME-26SEP21NYGLAR",
            "title": "New York G wins",
            "status": "active",
            "yes_bid": 22,
            "yes_ask": 23,
            "last_price": 23,
        }
        parsed = service.parse_markets([old_shape])[0]

        assert parsed.yes_bid == pytest.approx(0.22)
        assert parsed.last_price == pytest.approx(0.23)

    def test_an_unparseable_dict_is_dropped_not_positioned(self, service):
        """Short output keyed by ticker — a caller that zipped would mislabel."""
        parsed = service.parse_markets(
            [{"ticker": None, "close_time": "not-a-time-at-all"}, CAPTURED[LAR]]
        )

        assert [m.ticker for m in parsed] == [LAR]


class TestThePricePolicyIsTheOneThe2HourPollUses:
    def test_the_captured_books_price_at_their_midpoints(self, service):
        parsed = {m.ticker: m for m in service.parse_markets(list(CAPTURED.values()))}

        nyg = _kalshi_yes_probability(
            parsed[NYG].yes_bid, parsed[NYG].yes_ask, parsed[NYG].last_price
        )
        lar = _kalshi_yes_probability(
            parsed[LAR].yes_bid, parsed[LAR].yes_ask, parsed[LAR].last_price
        )

        assert nyg == pytest.approx(0.225), "tight two-sided book -> midpoint"
        assert lar == pytest.approx(0.77)
        assert nyg + lar == pytest.approx(0.995, abs=0.02), (
            "the two legs must read as one game's two sides, not as two "
            "independent coin flips — a scale error shows up here first"
        )

    def test_a_wide_one_sided_book_still_refuses(self):
        """The repair must not become 'write any number'."""
        assert _kalshi_yes_probability(0.05, 0.95, None) is None


class TestTheCentDialectCannotComeBack:
    def test_the_scan_fires_on_the_pre_fix_expression(self):
        """Proven against the code that shipped the bug, not only against green code."""
        assert _CENT_DIALECT.search(PRE_FIX_SOURCE), (
            "the scan below cannot testify about the current source if it does "
            "not flag the expression it was written to catch"
        )
        assert "/ 100.0" in PRE_FIX_SOURCE

    def test_the_live_poll_reads_no_cent_era_key_off_a_raw_dict(self):
        hits = _CENT_DIALECT.findall(_live_poll_source())

        assert hits == [], (
            "_poll_live_prediction_market_prices reads "
            f"{hits} off a raw venue dict again. `get_markets` returns the "
            "venue's own JSON and the venue stopped sending those keys — go "
            "through `KalshiAPIService.parse_markets` (#3569)."
        )

    def test_the_live_poll_does_not_rescale_a_parsed_price(self):
        assert "/ 100" not in _live_poll_source(), (
            "parsed Kalshi prices are already decimal probabilities; dividing "
            "again yields 0.0062 for a 62% market and never raises (#3569)."
        )

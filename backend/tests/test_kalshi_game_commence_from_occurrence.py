"""#3433 — a Kalshi game market is dated when it happens, not when it settles.

Every timestamp below was READ FROM THE VENUE on 2026-09-06 by series discovery
(``GET /trade-api/v2/series?category=Sports`` -> every ticker, then
``GET /trade-api/v2/markets?series_ticker=...&status=open``), standing notice 26a.
They are written out as literals on purpose: a test that re-derives its expected
value with production's own expression can never see that the expression is
wrong, so the numbers here are transcribed, never computed.

The defect: ``commence_time`` was ``market.close_time``, which for a game market
is a multi-day settlement backstop (+3d NFL, +4d MLB, +14d UFC/tennis). The fight
``KXUFCFIGHT-26SEP08LOUNAT`` happens Sep 8 and closes Sep 22, so the site showed
"Sep 22 7:00 PM" for a fight two days away.
"""

from datetime import datetime, timezone

import pytest

from app.services.kalshi_api import KalshiMarket
from app.tasks.kalshi import _kalshi_commence_time, _is_kalshi_game_ticker


def _utc(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _market(ticker: str, *, close: str, occurrence: str | None) -> KalshiMarket:
    """A real KalshiMarket — not a stand-in.

    Building the production model is part of the assertion: if
    ``occurrence_datetime`` is ever dropped from it, these tests stop
    constructing rather than quietly falling back to close_time.
    """
    return KalshiMarket(
        ticker=f"{ticker}-YES",
        event_ticker=ticker,
        title="t",
        status="active",
        close_time=_utc(close),
        occurrence_datetime=_utc(occurrence) if occurrence else None,
    )


# (event_ticker, close_time, occurrence_datetime, expected commence_time)
# All four are GAME tickers, all four were dated off close_time before #3433.
VENUE_GAME_SPECIMENS = [
    # The specimen in the issue: a UFC fight on Sep 8, closing Sep 22 (+14d).
    ("KXUFCFIGHT-26SEP08LOUNAT", "2026-09-22T23:00:00", "2026-09-09T04:00:00",
     "2026-09-09T04:00:00"),
    ("KXUFCFIGHT-26SEP08KOZECH", "2026-09-22T23:40:00", "2026-09-09T04:40:00",
     "2026-09-09T04:40:00"),
    # Tennis: the +14d class #3403 fixed by parsing the ticker. Same answer here
    # with no parsing at all, and with a real hour instead of midnight.
    ("KXWTAMATCH-26SEP07OSARYB", "2026-09-21T15:00:00", "2026-09-07T18:00:00",
     "2026-09-07T18:00:00"),
    # NFL +3d and MLB +4d: smaller drift, same defect.
    ("KXNFLGAME-26SEP21NYGLAR", "2026-09-24T00:15:00", "2026-09-22T03:15:00",
     "2026-09-22T03:15:00"),
    ("KXMLBGAME-26SEP082210CINLAD", "2026-09-12T02:10:00", "2026-09-09T05:10:00",
     "2026-09-09T05:10:00"),
]


class TestGameMarketsUseTheOccurrence:
    @pytest.mark.parametrize(
        "ticker,close,occurrence,expected", VENUE_GAME_SPECIMENS
    )
    def test_venue_specimen_is_dated_when_it_happens(
        self, ticker, close, occurrence, expected
    ):
        got = _kalshi_commence_time(
            [_market(ticker, close=close, occurrence=occurrence)], is_game=True
        )
        assert got == _utc(expected)

    @pytest.mark.parametrize(
        "ticker,close,occurrence,expected", VENUE_GAME_SPECIMENS
    )
    def test_venue_specimen_no_longer_carries_the_close_time(
        self, ticker, close, occurrence, expected
    ):
        """The property the bug had, stated directly.

        Without this the parametrized case above would still pass if the helper
        happened to return close_time for a specimen whose two fields agreed —
        so assert the DEFECT is gone, not only that the value is right.
        """
        got = _kalshi_commence_time(
            [_market(ticker, close=close, occurrence=occurrence)], is_game=True
        )
        assert got != _utc(close)

    def test_the_tickers_in_this_file_really_are_game_tickers(self):
        """``is_game`` is production's verdict, not the test's assumption.

        The fix is scoped by ``_is_kalshi_game_ticker``. If a specimen here
        stopped being recognised as a game, every assertion above would still
        pass (they pass ``is_game=True`` by hand) while production quietly
        fell back to close_time. This is the control for that.
        """
        for ticker, _close, _occ, _exp in VENUE_GAME_SPECIMENS:
            assert _is_kalshi_game_ticker(ticker), ticker


class TestTheScopeHolds:
    def test_an_outright_keeps_its_close_time(self):
        """Honey Deuce, read at the venue the same day.

        ``occurrence_datetime`` is populated on outrights too, where it means
        something else entirely — here it is 10 hours AFTER the close. A blanket
        preference would re-time markets that were never broken.
        """
        m = _market(
            "KXHONEYDEUCE-01JAN27",
            close="2027-01-01T04:59:00",
            occurrence="2027-01-01T15:00:00",
        )
        assert _kalshi_commence_time([m], is_game=False) == _utc("2027-01-01T04:59:00")

    def test_occurrence_after_close_is_refused_even_on_a_game_ticker(self):
        """The second bound, independent of the is_game scope.

        An occurrence later than its own settlement backstop is not something we
        understand, so we keep close_time rather than guess. Without this the
        outright shape above would move the moment a ticker prefix was added to
        ``_KALSHI_GAME_TICKERS``.
        """
        m = _market(
            "KXUFCFIGHT-26SEP08LOUNAT",
            close="2026-09-22T23:00:00",
            occurrence="2026-09-23T09:00:00",
        )
        assert _kalshi_commence_time([m], is_game=True) == _utc("2026-09-22T23:00:00")

    def test_a_payload_without_an_occurrence_still_gets_a_date(self):
        """Back-compat: the field is optional and older rows lack it."""
        m = _market(
            "KXUFCFIGHT-26SEP08LOUNAT", close="2026-09-22T23:00:00", occurrence=None
        )
        assert _kalshi_commence_time([m], is_game=True) == _utc("2026-09-22T23:00:00")

    def test_no_markets_yields_no_date_rather_than_raising(self):
        assert _kalshi_commence_time([], is_game=True) is None

    def test_a_market_with_neither_time_is_skipped_not_counted_as_none(self):
        """One dateless sibling must not erase a real start (gotcha #42)."""
        dateless = KalshiMarket(
            ticker="X-YES", event_ticker="KXUFCFIGHT-26SEP08LOUNAT",
            title="t", status="active",
        )
        good = _market(
            "KXUFCFIGHT-26SEP08LOUNAT",
            close="2026-09-22T23:00:00",
            occurrence="2026-09-09T04:00:00",
        )
        assert _kalshi_commence_time([dateless, good], is_game=True) == _utc(
            "2026-09-09T04:00:00"
        )


class TestMultiMarketEvents:
    def test_earliest_start_wins(self):
        """A multi-outcome event starts when its first market does."""
        markets = [
            _market("KXUFCFIGHT-26SEP08PASBER", close="2026-09-23T00:20:00",
                    occurrence="2026-09-09T05:20:00"),
            _market("KXUFCFIGHT-26SEP08LOUNAT", close="2026-09-22T23:00:00",
                    occurrence="2026-09-09T04:00:00"),
        ]
        assert _kalshi_commence_time(markets, is_game=True) == _utc(
            "2026-09-09T04:00:00"
        )

    def test_mixed_availability_still_prefers_the_occurrence_it_has(self):
        markets = [
            _market("KXUFCFIGHT-26SEP08PASBER", close="2026-09-23T00:20:00",
                    occurrence=None),
            _market("KXUFCFIGHT-26SEP08LOUNAT", close="2026-09-22T23:00:00",
                    occurrence="2026-09-09T04:00:00"),
        ]
        assert _kalshi_commence_time(markets, is_game=True) == _utc(
            "2026-09-09T04:00:00"
        )


class TestTheVenueFieldIsActuallyParsed:
    """The producer half. The helper is useless if nothing fills the field.

    This payload is the shape ``GET /markets`` returns, transcribed from the
    live response for ``KXUFCFIGHT-26SEP08LOUNAT-NAT``.
    """

    def test_parse_market_populates_occurrence_datetime(self):
        from app.services.kalshi_api import KalshiAPIService

        payload = {
            "ticker": "KXUFCFIGHT-26SEP08LOUNAT-NAT",
            "event_ticker": "KXUFCFIGHT-26SEP08LOUNAT",
            "title": "Christian Natividad wins",
            "status": "active",
            "open_time": "2026-09-02T12:40:00Z",
            "close_time": "2026-09-22T23:00:00Z",
            "expiration_time": "2026-09-22T23:00:00Z",
            "occurrence_datetime": "2026-09-09T04:00:00Z",
        }
        parsed = KalshiAPIService._parse_market(object.__new__(KalshiAPIService), payload)

        assert parsed is not None
        assert parsed.occurrence_datetime == _utc("2026-09-09T04:00:00")
        # and it is genuinely a different field, not an alias of the close
        assert parsed.close_time == _utc("2026-09-22T23:00:00")

    def test_a_payload_without_the_field_parses_to_none(self):
        from app.services.kalshi_api import KalshiAPIService

        payload = {
            "ticker": "KXUFCFIGHT-26SEP08LOUNAT-NAT",
            "event_ticker": "KXUFCFIGHT-26SEP08LOUNAT",
            "title": "Christian Natividad wins",
            "status": "active",
            "close_time": "2026-09-22T23:00:00Z",
        }
        parsed = KalshiAPIService._parse_market(object.__new__(KalshiAPIService), payload)

        assert parsed is not None
        assert parsed.occurrence_datetime is None

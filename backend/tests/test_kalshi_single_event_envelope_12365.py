"""The native single-event read retains its markets before pricing or repair."""

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import AsyncMock
import asyncio
import importlib

import httpx
import pytest

from app.services.kalshi_api import KalshiAPIService
from app.tasks.futures_price_refresh import VENUE_SETTLED, _fetch_kalshi_prices
from app.tasks.kalshi import _fetch_exact_kalshi_game_event

TICKER = "KXEUROLEAGUEGAME-26OCT081200CZVDUB"


class FixtureDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        instant = cls(2026, 10, 8, 12, tzinfo=timezone.utc)
        return (
            instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)
        )

    @classmethod
    def utcnow(cls):
        return cls.now(timezone.utc).replace(tzinfo=None)


def packet():
    return {
        "event": {
            "event_ticker": TICKER,
            "title": "KK Crvena zvezda Belgrade vs Dubai Basketball",
            "category": "Sports",
            "mutually_exclusive": True,
        },
        "markets": [
            {
                "event_ticker": TICKER,
                "ticker": f"{TICKER}-{code}",
                "title": f"{name} wins",
                "yes_sub_title": name,
                "status": "active",
                "yes_bid_dollars": "0.49",
                "yes_ask_dollars": "0.51",
                "last_price_dollars": "0.50",
                "close_time": "2026-10-10T16:00:00Z",
                "expected_expiration_time": "2026-10-08T19:00:00Z",
                "rules_primary": f"If {name} wins this match, Yes.",
            }
            for code, name in [
                ("DUB", "Dubai Basketball"),
                ("CZV", "KK Crvena zvezda Belgrade"),
            ]
        ],
    }


@asynccontextmanager
async def native_reader(payload=None, *, status=200, transport_error=None):
    calls = []

    def response(request):
        calls.append(request)
        if transport_error:
            raise transport_error
        return httpx.Response(status, json=deepcopy(payload))

    service = KalshiAPIService()
    await service.close()
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        service.client = client
        yield service, calls


@pytest.fixture(autouse=True)
def fixed_fixture_clock(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    # Pin the readers' wall clocks while keeping the event loop's clock real.
    for name in (
        "app.services.kalshi_api",
        "app.tasks.futures_price_refresh",
        "app.tasks.backfill_winners",
    ):
        module = importlib.import_module(name)
        monkeypatch.setattr(module, "datetime", FixtureDateTime)


@pytest.mark.parametrize(
    "shape", ["separate", "nested", "both", "empty_separate", "empty_nested"]
)
async def test_each_native_envelope_retains_all_market_facts(shape):
    raw = packet()
    markets = deepcopy(raw["markets"])
    if shape != "separate":
        raw["event"]["markets"] = deepcopy(markets)
    if shape == "nested":
        raw.pop("markets")
    elif shape == "empty_separate":
        raw["markets"] = []
    elif shape == "empty_nested":
        raw["event"]["markets"] = []
    before = deepcopy(raw)
    async with native_reader(raw) as (service, calls):
        event = await service.get_event(TICKER)
    assert event["markets"] == markets
    assert event["event_ticker"] == TICKER
    assert raw == before
    assert len(calls) == 1


@pytest.mark.parametrize(
    "change,reason",
    [
        (
            lambda p: p["event"].update(event_ticker="KXOTHER-26"),
            "event_identity_mismatch",
        ),
        (
            lambda p: p["markets"][0].update(event_ticker="KXOTHER-26"),
            "market_identity_mismatch",
        ),
        (lambda p: p.update(markets={}), "missing_market_envelope"),
        (lambda p: p.pop("markets"), "missing_market_envelope"),
        (lambda p: p.update(markets=[None]), "market_identity_mismatch"),
        (
            lambda p: p["event"].update(
                markets=[{**p["markets"][0], "title": "Other"}]
            ),
            "conflicting_market_envelopes",
        ),
    ],
)
async def test_ambiguous_or_foreign_input_is_an_explicit_failure(change, reason):
    raw = packet()
    change(raw)
    async with native_reader(raw) as (service, calls):
        with pytest.raises(ValueError, match=reason):
            await service.get_event(TICKER)
    assert len(calls) == 1


async def test_empty_markets_are_distinct_from_an_event_not_found():
    raw = packet()
    raw["markets"] = []
    async with native_reader(raw) as (service, _):
        assert (await service.get_event(TICKER))["markets"] == []
    async with native_reader({}, status=404) as (service, calls):
        assert await service.get_event(TICKER) is None
    assert len(calls) == 1


async def test_metadata_only_read_does_not_require_markets():
    raw = packet()
    raw.pop("markets")
    async with native_reader(raw) as (service, calls):
        assert (
            await service.get_event(TICKER, with_nested_markets=False) == raw["event"]
        )
    assert calls[0].url.params["with_nested_markets"] == "false"


@pytest.mark.parametrize("status", [429, 500])
async def test_a_failed_request_cannot_report_that_the_event_does_not_exist(status):
    async with native_reader({}, status=status) as (service, calls):
        with pytest.raises(httpx.HTTPStatusError):
            await service.get_event(TICKER)
    assert len(calls) == 3


async def test_timeout_is_not_event_absence():
    async with native_reader(transport_error=httpx.ReadTimeout("bounded test")) as (
        service,
        calls,
    ):
        with pytest.raises(httpx.ReadTimeout):
            await service.get_event(TICKER)
    assert len(calls) == 3


async def test_separate_envelope_reaches_the_exact_ingest_gate_with_all_legs():
    async with native_reader(packet()) as (service, calls):
        events = await _fetch_exact_kalshi_game_event(service, TICKER)
    assert [event.event_ticker for event in events] == [TICKER]
    assert {market.ticker for market in events[0].markets} == {
        f"{TICKER}-DUB",
        f"{TICKER}-CZV",
    }
    assert len(calls) == 1


async def test_an_open_separate_envelope_is_priced_instead_of_declared_settled():
    async with native_reader(packet()) as (service, calls):
        prices = await _fetch_kalshi_prices(service, TICKER)
    assert prices is not VENUE_SETTLED
    assert len(prices) == 2
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["source_error", "not_found"])
async def test_one_unreadable_event_leaves_healthy_siblings_grading(
    monkeypatch, failure
):
    from app.utils.kalshi_event_envelope import KalshiEventEnvelopeError
    from tests.test_kalshi_settlement_recency_band_4057 import (
        _FakeKalshi,
        _drive,
        _finalized_event,
    )

    original = _FakeKalshi.get_event

    async def get_event(self, ticker):
        if ticker == "KXBAD" and failure == "source_error":
            self.asked.append(ticker)
            raise KalshiEventEnvelopeError(ticker, "conflicting_market_envelopes")
        return await original(self, ticker)

    monkeypatch.setattr(_FakeKalshi, "get_event", get_event)
    stats, _, venue, _, _ = await _drive(
        monkeypatch,
        fresh=["KXBAD", "KXGOOD"],
        tail=[],
        fast_lane_only=True,
        answers={"KXGOOD": _finalized_event("KXGOOD-YES")},
    )
    assert set(venue.asked) == {"KXBAD", "KXGOOD"}
    assert stats["tickers_queried"] == 2
    assert stats["events_found"] == stats["winners_set"] == 1
    if failure == "source_error":
        assert stats["api_errors"] == 1 and stats["api_miss"] == 0
        assert stats["errors"] == ["KXBAD: conflicting_market_envelopes"]
    else:
        assert stats.get("api_errors", 0) == 0 and stats["api_miss"] == 1
        assert stats["errors"] == []

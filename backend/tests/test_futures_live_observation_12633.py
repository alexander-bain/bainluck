"""A quiet open field gets an honest observation, never an invented price."""

import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.kalshi_api import KalshiAPIService
from app.utils import futures_live_observation as live

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/governor_quote_12633.json").read_text()
)
NOW = datetime(2030, 1, 15, 14, 50, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clock_and_cache(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz else NOW.replace(tzinfo=None)

    monkeypatch.setattr(live, "datetime", Clock)
    # isinstance must still recognize model datetimes under the frozen clock.
    monkeypatch.setattr(live, "_stamp", lambda value: value)
    live._cache.clear()
    live._in_flight.clear()
    live._reads.clear()


def market():
    rows = []
    for row in FIXTURE["stored"]:
        values = dict(row)
        for key in ("last_updated", "price_changed_at"):
            values[key] = datetime.fromisoformat(values[key])
        rows.append(SimpleNamespace(**values))
    return SimpleNamespace(
        id=108629,
        source="kalshi",
        status="open",
        market_type="field",
        external_id=FIXTURE["event"]["event_ticker"],
        event_id=None,
        settled_at=None,
        outcomes=rows,
    )


def detail(m):
    total = sum(o.current_probability for o in m.outcomes)
    return {
        "outcomes": [
            {
                "id": o.id,
                "probability": o.current_probability / total,
                "last_updated": o.last_updated.isoformat(),
                "price_changed_at": o.price_changed_at.isoformat(),
                "is_winner": o.is_winner,
                "resolution_source": o.resolution_source,
            }
            for o in m.outcomes
        ]
    }


def observed(raw=None):
    raw = copy.deepcopy(raw if raw is not None else FIXTURE["event"])
    parser = object.__new__(KalshiAPIService)
    prices = live.venue_prices(parser, raw, FIXTURE["event"]["event_ticker"])
    return live.Observation(FIXTURE["event"]["event_ticker"], prices, NOW)


@pytest.mark.asyncio
async def test_real_governor_field_rechecks_without_repricing_or_regrading(monkeypatch):
    m = market()
    before = copy.deepcopy(m)
    payload = detail(m)
    old = copy.deepcopy(payload)
    receipt = observed()
    assert receipt.prices == live.board_prices(m, NOW)

    async def read(_ticker):
        return live.ReadResult(receipt)

    monkeypatch.setattr(live, "current_observation", read)
    await live.apply_live_observation(payload, m)
    assert m == before
    assert payload["price_observation"]["state"] == "verified"
    assert len(payload["outcomes"]) == 24
    for old_row, row in zip(old["outcomes"], payload["outcomes"]):
        assert row["observed_at"] == row["last_updated"] == NOW.isoformat()
        assert {
            k: v for k, v in row.items() if k not in ("observed_at", "last_updated")
        } == {k: v for k, v in old_row.items() if k != "last_updated"}


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "extra",
        "duplicate",
        "closed",
        "settled",
        "unpriced",
        "wrong_event",
        "wrong_leg_event",
        "malformed",
    ],
)
def test_unverified_venue_field_never_supplies_an_observation(change):
    raw = copy.deepcopy(FIXTURE["event"])
    if change == "missing":
        raw["markets"].pop()
    elif change == "extra":
        extra = dict(raw["markets"][0], ticker="KX-OTHER")
        raw["markets"].append(extra)
    elif change == "duplicate":
        raw["markets"].append(raw["markets"][0])
    elif change == "closed":
        raw["markets"][0]["status"] = "closed"
    elif change == "settled":
        raw["markets"][0]["result"] = "no"
    elif change == "unpriced":
        raw["markets"][0].update(
            yes_bid_dollars="0", yes_ask_dollars="1", last_price_dollars="0"
        )
    elif change == "wrong_event":
        raw["event_ticker"] = "OTHER"
    elif change == "wrong_leg_event":
        raw["markets"][0]["event_ticker"] = "OTHER"
    else:
        raw["markets"][0] = None
    prices = live.venue_prices(
        object.__new__(KalshiAPIService), raw, FIXTURE["event"]["event_ticker"]
    )
    assert prices is None or prices != live.board_prices(market(), NOW)


@pytest.mark.parametrize(
    "changes",
    [
        {"source": "polymarket"},
        {"status": "resolved"},
        {"market_type": "threshold"},
        {"event_id": 7},
        {"settled_at": NOW},
    ],
)
def test_other_boards_never_trigger_a_read(changes):
    m = market()
    for key, value in changes.items():
        setattr(m, key, value)
    assert live.board_prices(m, NOW) is None


@pytest.mark.parametrize(
    "change", ["graded", "winner", "no_price", "duplicate", "too_large", "fresh"]
)
def test_unqualified_stored_boards_never_trigger_a_read(change):
    m = market()
    if change == "graded":
        m.outcomes[0].resolution_source = "api_settlement"
    elif change == "winner":
        m.outcomes[0].is_winner = True
    elif change == "no_price":
        m.outcomes[0].current_probability = None
    elif change == "duplicate":
        m.outcomes.append(m.outcomes[0])
    elif change == "too_large":
        m.outcomes *= 3
    else:
        for row in m.outcomes:
            row.last_updated = NOW
    assert live.board_prices(m, NOW) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["moved", "future", "expired", "error", "composed", "withheld"]
)
async def test_refusals_keep_existing_values_and_their_old_clocks(monkeypatch, change):
    m = market()
    payload = detail(m)
    receipt = observed()
    if change == "moved":
        m.outcomes[0].current_probability += 0.01
    elif change in ("future", "expired"):
        offset = 1 if change == "future" else -live.CACHE_SECONDS - 1
        receipt = live.Observation(
            receipt.ticker, receipt.prices, NOW + timedelta(seconds=offset)
        )
    elif change == "composed":
        payload["representation"] = "verified_title"
    elif change == "withheld":
        payload["outcomes"][0]["probability"] = None
    old = copy.deepcopy(payload)

    async def read(_ticker):
        return (
            live.ReadResult(None, "venue_read_failed")
            if change == "error"
            else live.ReadResult(receipt)
        )

    monkeypatch.setattr(live, "current_observation", read)
    await live.apply_live_observation(payload, m)
    if change == "withheld":
        assert payload["outcomes"][0] == old["outcomes"][0]
    else:
        assert payload["outcomes"] == old["outcomes"]
    if change == "error":
        assert payload["price_observation"]["reason"] == "venue_read_failed"


@pytest.mark.asyncio
async def test_concurrent_reads_share_one_fetch_and_cached_time_never_resets(
    monkeypatch,
):
    calls = []
    receipt = observed()

    async def read(ticker):
        calls.append(ticker)
        await asyncio.sleep(0)
        return live.ReadResult(receipt)

    monkeypatch.setattr(live, "_read", read)
    a, b = await asyncio.gather(
        *(live.current_observation(receipt.ticker) for _ in range(2))
    )
    c = await live.current_observation(receipt.ticker)
    assert a == b == c == live.ReadResult(receipt)
    assert calls == [receipt.ticker]


@pytest.mark.asyncio
async def test_failures_are_named_and_negatively_cached(monkeypatch):
    calls = []

    async def fail(ticker):
        calls.append(ticker)
        raise TimeoutError()

    monkeypatch.setattr(live, "_read", fail)
    for _ in range(2):
        result = await live.current_observation("KX-ONE")
        assert result.reason == "venue_timeout" and result.observation is None
    assert calls == ["KX-ONE"]


@pytest.mark.asyncio
async def test_read_budget_refuses_without_a_fetch(monkeypatch):
    live._reads.extend([live.time.monotonic()] * live.MAX_READS_PER_MINUTE)
    result = await live.current_observation("KX-ONE")
    assert result.reason == "read_budget_full" and result.observation is None


@pytest.mark.asyncio
@pytest.mark.parametrize("hang", [False, True])
async def test_real_fetch_boundary_closes_client_and_enforces_deadline(
    monkeypatch, hang
):
    from app.services import kalshi_api

    calls = []
    ticker = FIXTURE["event"]["event_ticker"]

    class Client(KalshiAPIService):
        def __init__(self):
            pass

        async def get_event(self, requested, *, with_nested_markets):
            assert requested == ticker and with_nested_markets is True
            calls.append("read")
            if hang:
                await asyncio.Event().wait()
            return copy.deepcopy(FIXTURE["event"])

        async def close(self):
            calls.append("closed")

    monkeypatch.setattr(kalshi_api, "KalshiAPIService", Client)
    monkeypatch.setattr(live, "READ_TIMEOUT_S", 0.01)
    result = await asyncio.wait_for(live.current_observation(ticker), 2)
    assert calls == ["read", "closed"]
    assert not live._in_flight
    if hang:
        assert result == live.ReadResult(None, "venue_timeout")
    else:
        assert result.observation == observed()


@pytest.mark.asyncio
@pytest.mark.parametrize("representation", ["source", "verified_title"])
async def test_detail_route_carries_the_verified_observation(
    monkeypatch, representation
):
    from app.routes import futures
    from app.models.models import FuturesMarket, FuturesOutcome

    fixture_market = market()
    m = FuturesMarket(
        id=fixture_market.id,
        name="Closest Governor race in 2026?",
        source="kalshi",
        status="open",
        market_type="field",
        external_id=fixture_market.external_id,
        mutually_exclusive=True,
        outcomes=[FuturesOutcome(**vars(row)) for row in fixture_market.outcomes],
    )
    db = SimpleNamespace()

    async def execute(_stmt):
        result = SimpleNamespace(scalar_one_or_none=lambda: m)
        result.unique = lambda: result
        return result

    db.execute = execute

    async def sources(*_args):
        return ["kalshi"], []

    async def empty(*_args):
        return {}

    async def none(*_args):
        return None

    async def read(_ticker):
        return live.ReadResult(observed())

    monkeypatch.setattr(futures, "_load_market_sources", sources)
    for name in (
        "_withheld_price_outcome_ids",
        "_game_container_leg_sides",
        "out_legs_by_market",
    ):
        monkeypatch.setattr(futures, name, empty)
    for name in (
        "_fleet_newest_observation",
        "_game_container_lead_leg",
        "_game_container_of_event_id",
    ):
        monkeypatch.setattr(futures, name, none)
    monkeypatch.setattr(live, "current_observation", read)
    result = await futures.get_futures_market(
        108629, db=db, representation=representation
    )
    assert result["outcomes"][0]["observed_at"] == NOW.isoformat()
    assert result["outcomes"][0]["name"] == "Kansas"
    assert result["outcomes"][0]["probability"] == pytest.approx(0.91822992)
    assert all(
        row["last_updated"] == NOW.isoformat()
        for row in result["outcomes"]
        if row["probability"] is not None
    )
    assert all(row.last_updated != NOW for row in m.outcomes)

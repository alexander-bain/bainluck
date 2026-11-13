"""The real REST poll dates successful inputs, including cached Gamma replies."""

from datetime import datetime, timedelta, timezone

import pytest

from app.tasks import prediction_market_matching as pmm
from app.utils import aggregation
from tests.test_live_poll_commit_boundary_5682 import (
    _KalshiService, _PolyService, _Population, _Session, _leg, _run,
)
from tests.test_live_poll_refuses_a_reading_older_than_the_stored_stamp_8910 import _beat
from tests.test_live_poll_settled_speaker_call_site_6608 import TICKER, _disable_inversion


def clock_and_stamps(monkeypatch):
    clock = [datetime.now(timezone.utc) - timedelta(minutes=1)]

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0].astimezone(tz) if tz else clock[0].replace(tzinfo=None)

    monkeypatch.setattr(pmm, "datetime", Clock)
    _disable_inversion(monkeypatch)
    stamps = []
    real = aggregation.stamp_source_reading

    def record(existing, source, value, **kwargs):
        result = real(existing, source, value, **kwargs)
        stamps.append((source, value, result))
        return result

    monkeypatch.setattr(aggregation, "stamp_source_reading", record)
    return clock, stamps


@pytest.mark.parametrize("answer", ["priced", "empty", "failed", "rolled_back"])
async def test_kalshi_age_requires_a_successful_committed_price(monkeypatch, answer):
    clock, stamps = clock_and_stamps(monkeypatch)
    started = clock[0]
    population = _beat(last_seen=started - timedelta(hours=1))
    restored = _beat(last_seen=started - timedelta(hours=1))

    class Service(_KalshiService):
        async def get_markets(self, **kwargs):
            clock[0] = started + timedelta(seconds=5)
            return await super().get_markets(**kwargs)

    failed_once = False

    def fail_insert(kind, n, stmt):
        nonlocal failed_once
        if answer == "rolled_back" and kind == "insert" and not failed_once:
            failed_once = True
            return RuntimeError("fixture write refused")

    session = _Session([population, restored], on_execute=fail_insert)
    service = Service(
        {TICKER: [] if answer == "empty" else [_leg(f"{TICKER}-LAR", TICKER)]}, [],
        raises={TICKER: RuntimeError("fixture venue unavailable")} if answer == "failed" else {},
    )
    stats = await _run(monkeypatch, session, kalshi=service, blend={})
    assert len(stamps) == 1, stats
    source, value, bag = stamps[0]
    at = aggregation.source_price_read_time(bag, source, value, now=clock[0])
    assert at == (started + timedelta(seconds=5) if answer == "priced" else None)
    if answer in {"failed", "rolled_back"}:
        assert stats["session_recoveries"] == 1


async def test_two_gamma_rows_share_original_response_time_not_second_apply(monkeypatch):
    clock, stamps = clock_and_stamps(monkeypatch)
    started = clock[0]
    first = _beat(last_seen=started - timedelta(hours=1))
    second = _beat(last_seen=started - timedelta(hours=1))
    for index, population in enumerate((first, second), 1):
        market, event = population.rows[0]
        outcome = population.outcomes[0]
        market.id = index
        market.source = "polymarket"
        market.external_id = f"condition-{index}"
        market.market_metadata = {"polymarket_event_id": "999001"}
        event.id = 100 + index
        outcome.id = 1000 + index
        outcome.market_id = index
        outcome.external_id = f"condition-{index}"
    population = _Population(first.rows + second.rows, first.outcomes + second.outcomes)

    class Session(_Session):
        async def commit(self):
            await super().commit()
            clock[0] += timedelta(seconds=7)

    class Service(_PolyService):
        async def get_event_by_id(self, external_id):
            clock[0] = started + timedelta(seconds=5)
            return await super().get_event_by_id(external_id)

    journal = []
    service = Service({"999001": {"markets": [
        {"conditionId": f"condition-{i}", "outcomePrices": ["0.61", "0.39"],
         "outcomes": ["Yes", "No"], "bestBid": 0.60, "bestAsk": 0.62,
         "lastTradePrice": 0.61}
        for i in (1, 2)
    ]}}, journal)
    stats = await _run(monkeypatch, Session([population]), poly=service, blend={})
    assert len(stamps) == 2, stats
    assert journal == [("fetch", "999001")]
    assert clock[0] > started + timedelta(seconds=5)
    for source, value, bag in stamps:
        assert aggregation.source_price_read_time(bag, source, value, now=clock[0]) == (
            started + timedelta(seconds=5)
        )

"""Open-market quotes retain sports phase through the actual SSE generator."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from fastapi import HTTPException

import pytest

from app.models import Event, FuturesMarket, FuturesOutcome
from app.routes import event_stream as route
from app.utils import live_fanout


class Request:
    async def is_disconnected(self):
        return False


class Hub:
    def __init__(self):
        self.subscriptions = {}
        self.released = []

    async def subscribe(self, channel):
        sub = live_fanout.Subscription(channel)
        self.subscriptions[channel] = sub
        return sub

    def release(self, sub):
        self.released.append(sub.channel)


def frame(event_id, revision, status):
    return {"event_id": event_id, "p": .61, "source": "kalshi",
            "source_value": .62, "rev": {str(event_id): revision},
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": status}


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["scheduled", "suspended"])
async def test_successive_quotes_do_not_end_a_supported_nonlive_stream(monkeypatch, status):
    hub = Hub()
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    stream = route._stream(1, Request())
    try:
        await anext(stream)
        await anext(stream)
        for rev in (11, 12):
            quote = frame(1, rev, status)
            hub.subscriptions["live:event:1"].offer(json.dumps(quote))
            chunk = await asyncio.wait_for(anext(stream), 1)
            assert chunk.startswith("event: probability\n")
            assert json.loads(chunk.split("data: ")[1]) == quote
    finally:
        await stream.aclose()
    assert hub.released == ["live:event:1"]


@pytest.mark.asyncio
@pytest.mark.parametrize("sibling_status", ["live", "scheduled", "suspended", "completed"])
async def test_fold_invalidation_cannot_assign_the_siblings_phase(monkeypatch, sibling_status):
    hub = Hub()
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    stream = route._stream(1, Request(), [1, 2])
    try:
        await anext(stream)
        await anext(stream)
        hub.subscriptions["live:event:2"].offer(json.dumps(frame(2, 20, sibling_status)))
        chunk = await asyncio.wait_for(anext(stream), 1)
        payload = json.loads(chunk.split("data: ")[1])
        assert payload.get("status") is None
        assert payload["invalidation"] is True
        assert payload["p"] is payload["source_value"] is None
        own = frame(1, 30, "scheduled")
        hub.subscriptions["live:event:1"].offer(json.dumps(own))
        assert json.loads((await asyncio.wait_for(anext(stream), 1)).split("data: ")[1]) == own
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_authoritative_final_still_delivers_then_closes(monkeypatch):
    hub = Hub()
    monkeypatch.setattr(live_fanout, "fanout", lambda: hub)
    stream = route._stream(1, Request())
    try:
        await anext(stream)
        await anext(stream)
        own = frame(1, 31, "completed")
        hub.subscriptions["live:event:1"].offer(json.dumps(own))
        assert json.loads((await anext(stream)).split("data: ")[1]) == own
        assert "event: closed" in await anext(stream)
    finally:
        await stream.aclose()


NOW = datetime(2026, 9, 29, tzinfo=timezone.utc)


def market_fixture(source="kalshi", **overrides):
    values = dict(id=100, event_id=1, source=source, status="open",
                  external_id="KXNBAGAME-26SEP28BOSGSW-BOS" if source == "kalshi" else "0xabc",
                  name="Celtics vs. Warriors", market_metadata={},
                  outcomes=[FuturesOutcome(id=101, market_id=100, name="Boston Celtics",
                      external_id="KXNBAGAME-26SEP28BOSGSW-BOS" if source == "kalshi" else "0xabc",
                      current_probability=.6, rank=1),
                      FuturesOutcome(id=102, market_id=100, name="Golden State Warriors",
                      external_id="KXNBAGAME-26SEP28BOSGSW-GSW" if source == "kalshi" else "0xabc_side1",
                      current_probability=.4, rank=2)])
    if source == "polymarket":
        values["market_metadata"] = {"clob_token_ids": ["123", "456"]}
    values.update(overrides)
    return FuturesMarket(**values)


def event_fixture(status="scheduled", **overrides):
    values = dict(id=1, status=status, completed_at=None,
                  commence_time=NOW + timedelta(hours=1),
                  home_team_name="Boston Celtics", away_team_name="Golden State Warriors")
    values.update(overrides)
    return Event(**values)


@pytest.mark.parametrize("source", ["kalshi", "polymarket"])
@pytest.mark.parametrize("status", ["scheduled", "suspended"])
def test_mapped_winner_admitted_independently_of_play_phase(source, status):
    event = event_fixture(status, commence_time=NOW-timedelta(hours=7) if status == "suspended" else NOW)
    assert route._has_mapped_winner(event, [market_fixture(source)], NOW)


@pytest.mark.parametrize("source", ["kalshi", "polymarket"])
@pytest.mark.parametrize("change", ["unmapped", "resolved", "settled", "prop", "wrong_match"])
def test_nonlive_requires_an_unsettled_mapped_moneyline(source, change):
    market = market_fixture(source)
    if change == "unmapped":
        market.market_metadata = {}
        for outcome in market.outcomes:
            outcome.external_id = ""
    elif change == "resolved":
        market.status = "resolved"
    elif change == "settled":
        market.outcomes[0].is_winner = True
    elif change == "prop":
        market.external_id = "KXNBAPOINTS-26SEP28-TATUM" if source == "kalshi" else "0xabc"
        market.name = "Celtics vs. Warriors: Total Points Over 200.5"
        for outcome in market.outcomes:
            outcome.name = "Over 200.5" if outcome.rank == 1 else "Under 200.5"
    else:
        market.name = "Lakers vs. Knicks"
        for outcome in market.outcomes:
            outcome.name = "Los Angeles Lakers" if outcome.rank == 1 else "New York Knicks"
    assert not route._has_mapped_winner(event_fixture(), [market], NOW)


@pytest.mark.parametrize("status,age,source,expected", [
    ("scheduled", 6, "kalshi", True), ("scheduled", 6.01, "kalshi", False),
    ("scheduled", -25, "kalshi", True), ("scheduled", -25, "polymarket", False),
    ("scheduled", -24, "polymarket", True),
    ("suspended", -24, "kalshi", True), ("suspended", -24.01, "kalshi", False),
    ("completed", 0, "kalshi", False), ("postponed", 0, "polymarket", False),
])
def test_initial_producer_cohort_bounds(status, age, source, expected):
    event = event_fixture(status, commence_time=NOW + timedelta(hours=age))
    assert route._has_mapped_winner(event, [market_fixture(source)], NOW) is expected


def test_completed_result_and_missing_start_do_not_open_nonlive_stream():
    for event in (event_fixture(completed_at=NOW), event_fixture(commence_time=None)):
        assert not route._has_mapped_winner(event, [market_fixture()], NOW)


@pytest.mark.parametrize("tokens", [["123"], ["123", "123"], ["123", None], "invalid"])
def test_partial_token_lists_cannot_claim_outcome_cache_coverage(tokens):
    market = market_fixture("polymarket", market_metadata={
        "clob_token_ids": tokens, "clob_yes_token_by_outcome": {"101": "123", "102": "456"}})
    assert not route._has_mapped_winner(event_fixture(), [market], NOW)


def test_persisted_token_cache_and_json_binary_tokens_are_supported():
    for metadata in ({"clob_yes_token_by_outcome": {"101": "123", "102": "456"}},
                     {"clobTokenIds": '["123", "456"]'}):
        assert route._has_mapped_winner(event_fixture(), [market_fixture("polymarket", market_metadata=metadata)], NOW)


@pytest.mark.parametrize("status,eligible,expected", [
    ("scheduled", True, 200), ("suspended", True, 200),
    ("scheduled", False, 409), ("completed", False, 409), (None, False, 404),
])
async def test_connect_admission_releases_database_before_stream(monkeypatch, status, eligible, expected):
    class Maker:
        closed = False
        def __call__(self): return self
        async def __aenter__(self): return self
        async def __aexit__(self, *args): self.closed = True
    maker = Maker()
    monkeypatch.setattr(route, "async_session_maker", maker)
    monkeypatch.setattr(route, "_event_status", AsyncMock(return_value=status))
    monkeypatch.setattr(route, "_fold_stream_ids", AsyncMock(return_value=[1, 2]))
    check = AsyncMock(return_value=eligible)
    monkeypatch.setattr(route, "_nonlive_stream_eligible", check)
    if expected == 200:
        response = await route.stream_event(1, Request())
        assert response.status_code == 200
    else:
        with pytest.raises(HTTPException) as exc:
            await route.stream_event(1, Request())
        assert exc.value.status_code == expected
    assert maker.closed
    assert check.await_count == int(status in {"scheduled", "suspended"})


@pytest.mark.parametrize("canonical_status,completed,has_winner,expected", [
    ("scheduled", False, True, True), ("suspended", False, True, True),
    ("scheduled", False, False, False), ("completed", False, True, False),
    ("scheduled", True, True, False),
])
async def test_fold_connect_uses_publishable_contributor_but_never_overrides_canonical_result(
    canonical_status, completed, has_winner, expected,
):
    from unittest.mock import Mock
    canonical = event_fixture(canonical_status, completed_at=NOW if completed else None)
    sibling = event_fixture("live", id=2)
    market = market_fixture(event_id=2)
    responses = []
    for values in ([canonical, sibling], [market] if has_winner else []):
        result = Mock()
        result.scalars.return_value.all.return_value = values
        responses.append(result)
    db = Mock()
    db.execute = AsyncMock(side_effect=responses)
    assert await route._nonlive_stream_eligible(db, 1, [1, 2]) is expected
    assert db.execute.await_count == (1 if canonical_status == "completed" or completed else 2)

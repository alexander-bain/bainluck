"""Polymarket ceremony evidence shares the bounded, rules-only discovery path."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncio
import httpx
import pytest
from sqlalchemy.dialects import postgresql

from app.services import awards_occasion_source as source
from app.services.polymarket_api import PolymarketAPIService

EVENT_ID = "123456"
RULE = "This market resolves Yes if Film A wins at the 99th Academy Awards."


def envelope(event_id=EVENT_ID):
    return {
        "id": event_id,
        "title": "Best Picture",
        "markets": [{"id": "1001", "description": RULE}],
    }


def database(event_ids):
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: event_ids))
    return SimpleNamespace(execute=AsyncMock(return_value=result))


def test_native_description_is_retained_as_verbatim_primary_evidence():
    payload = envelope()
    normalized = source.polymarket_occasion_event(payload, EVENT_ID)
    assert normalized["provider"] == "polymarket"
    assert normalized["markets"][0]["rules_primary"] == RULE
    assert payload == envelope()


@pytest.mark.parametrize(
    "change,reason",
    [
        (lambda p: p.update(id="999999"), "event_identity_mismatch"),
        (lambda p: p.pop("markets"), "missing_market_envelope"),
        (lambda p: p.update(markets={}), "missing_market_envelope"),
        (lambda p: p["markets"].append(None), "market_identity_mismatch"),
        (lambda p: p["markets"][0].pop("id"), "market_identity_mismatch"),
        (
            lambda p: p["markets"][0].update(events=[{"id": "999999"}]),
            "market_identity_mismatch",
        ),
    ],
)
def test_foreign_or_malformed_envelopes_cannot_establish_membership(change, reason):
    payload = deepcopy(envelope())
    change(payload)
    with pytest.raises(source.AwardsOccasionSourceError, match=reason):
        source.polymarket_occasion_event(payload, EVENT_ID)


async def test_stored_pool_selects_provider_events_without_a_typed_ceremony_list():
    seen = []

    def respond(request):
        seen.append(request)
        if request.url.path == "/events":
            return httpx.Response(200, json=[envelope()])
        return httpx.Response(200, json=envelope())

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
        base_url=PolymarketAPIService.GAMMA_BASE_URL,
    ) as client:
        service = SimpleNamespace(
            get_event_by_id=PolymarketAPIService.get_event_by_id,
            gamma_client=client,
        )

        async def get_event(event_id):
            return await PolymarketAPIService.get_event_by_id(service, event_id)

        async def get_events(event_ids):
            return await PolymarketAPIService.get_events_by_ids(service, event_ids)

        service.get_event_by_id = get_event
        service.get_events_by_ids = get_events
        db = database([EVENT_ID])
        result = await source.read_polymarket_awards_occasions(db, service)

    assert len(seen) == 1
    assert result.refused == ()
    assert result.occasions[0].label == "99th Academy Awards"
    assert result.occasions[0].events[0].evidence == (RULE,)
    assert result.occasions[0].relation == "same_event"
    assert result.occasions[0].level == "member"
    statement = str(
        db.execute.await_args.args[0].compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "futures_markets.source = 'polymarket'" in statement
    assert "futures_markets.status = 'open'" in statement
    assert "polymarket_event_id" in statement
    assert "SELECT DISTINCT" in statement
    assert f"LIMIT {source.MAX_AWARDS_EVENT_CANDIDATES + 1}" in statement
    assert "Academy" not in statement and "Oscars" not in statement


async def test_a_title_or_deadline_cannot_supply_a_missing_primary_rule():
    payload = envelope()
    payload["title"] = "99th Academy Awards, December 2027"
    payload["markets"][0]["description"] = None
    service = SimpleNamespace(
        get_event_by_id=AsyncMock(return_value=payload),
        get_events_by_ids=AsyncMock(return_value=[]),
    )
    result = await source.read_polymarket_awards_occasions(
        database([EVENT_ID]), service
    )
    assert result.occasions == ()
    assert result.refused == (("polymarket", EVENT_ID, "ceremony_identity_unknown"),)


async def test_missing_provider_events_keep_their_reason():
    service = SimpleNamespace(
        get_event_by_id=AsyncMock(return_value=None),
        get_events_by_ids=AsyncMock(return_value=[]),
    )
    result = await source.read_polymarket_awards_occasions(
        database([EVENT_ID, None, "bad/id"]), service
    )
    assert result.occasions == ()
    assert result.refused == (
        ("polymarket", "", "invalid_identity"),
        ("polymarket", EVENT_ID, "provider_event_missing"),
        ("polymarket", "bad/id", "invalid_identity"),
    )
    service.get_event_by_id.assert_awaited_once_with(EVENT_ID)


@pytest.mark.parametrize("status", [429, 500])
async def test_source_failure_aborts_instead_of_returning_partial_evidence(status):
    request = httpx.Request("GET", "https://gamma-api.polymarket.com/events/999")
    failure = httpx.HTTPStatusError(
        "source unavailable",
        request=request,
        response=httpx.Response(status, request=request),
    )
    service = SimpleNamespace(
        get_event_by_id=AsyncMock(side_effect=[envelope(), failure]),
        get_events_by_ids=AsyncMock(return_value=[]),
    )
    with pytest.raises(httpx.HTTPStatusError):
        await source.read_polymarket_awards_occasions(
            database([EVENT_ID, "999"]), service
        )


async def test_candidate_overflow_aborts_before_a_venue_read():
    service = SimpleNamespace(
        get_event_by_id=AsyncMock(), get_events_by_ids=AsyncMock()
    )
    with pytest.raises(
        source.AwardsOccasionSourceError, match="candidate_limit_exceeded"
    ):
        await source.read_polymarket_awards_occasions(
            database([EVENT_ID] * (source.MAX_AWARDS_EVENT_CANDIDATES + 1)), service
        )
    service.get_event_by_id.assert_not_awaited()
    service.get_events_by_ids.assert_not_awaited()


async def test_batches_are_keyed_by_identity_and_omissions_need_a_single_event_read():
    ids = [
        str(1000 + index) for index in range(source.AWARDS_POLYMARKET_BATCH_SIZE + 3)
    ]
    missing = ids[2]

    async def batch(event_ids):
        return [
            envelope(event_id)
            for event_id in reversed(event_ids)
            if event_id != missing
        ]

    service = SimpleNamespace(
        get_events_by_ids=AsyncMock(side_effect=batch),
        get_event_by_id=AsyncMock(return_value=envelope(missing)),
    )
    result = await source.read_polymarket_awards_occasions(database(ids), service)
    assert len(result.occasions[0].events) == len(ids)
    assert result.refused == ()
    assert [
        len(call.args[0]) for call in service.get_events_by_ids.await_args_list
    ] == [20, 3]
    service.get_event_by_id.assert_awaited_once_with(missing)


@pytest.mark.parametrize(
    "payloads", [[envelope("999999")], [envelope(), envelope()], [None]]
)
async def test_a_foreign_duplicate_or_malformed_batch_aborts(payloads):
    service = SimpleNamespace(
        get_events_by_ids=AsyncMock(return_value=payloads), get_event_by_id=AsyncMock()
    )
    with pytest.raises(
        source.AwardsOccasionSourceError, match="batch_identity_mismatch"
    ):
        await source.read_polymarket_awards_occasions(database([EVENT_ID]), service)
    service.get_event_by_id.assert_not_awaited()


async def test_budget_and_cancellation_cover_the_database_read(monkeypatch):
    monkeypatch.setattr(source, "AWARDS_SOURCE_BUDGET_SECONDS", 0.01)

    async def blocked(statement):
        await asyncio.Event().wait()

    with pytest.raises(TimeoutError):
        await source.read_polymarket_awards_occasions(
            SimpleNamespace(execute=blocked), SimpleNamespace()
        )


async def test_two_sources_group_by_ceremony_without_claiming_equivalence(monkeypatch):
    from app.utils.awards_occasion_finder import find_awards_occasions

    kalshi = find_awards_occasions(
        [
            {
                "provider": "kalshi",
                "event_ticker": "KXNEW-PIC27",
                "title": "Best Picture",
                "markets": [{"rules_primary": RULE}],
            }
        ]
    )
    poly = find_awards_occasions(
        [source.polymarket_occasion_event(envelope(), EVENT_ID)]
    )
    monkeypatch.setattr(
        source, "read_kalshi_awards_occasions", AsyncMock(return_value=kalshi)
    )
    monkeypatch.setattr(
        source, "read_polymarket_awards_occasions", AsyncMock(return_value=poly)
    )
    result = await source.read_awards_occasions(object(), object(), object())
    assert len(result.occasions) == 1
    assert [event.provider for event in result.occasions[0].events] == [
        "kalshi",
        "polymarket",
    ]
    assert result.occasions[0].level == "member"

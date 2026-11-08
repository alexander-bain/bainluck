"""Worker inputs retain venue identities, raw rules and explicit source failures."""

from copy import deepcopy
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncio
import httpx
import pytest
from sqlalchemy.dialects import postgresql

from app.services import awards_occasion_source as source
from app.services.kalshi_api import KalshiAPIService


TICKER = "KXGGNOM-SCR26"
RULE = (
    "If Wild Horse Nine is on the list of nominees for Best Screenplay at the "
    "84th Golden Globe Awards, then the market resolves to Yes."
)


def envelope(ticker=TICKER, label="84th Golden Globe Awards"):
    # /events/KXGGNOM-SCR26, read Nov 6, returned markets beside the event.
    return {
        "event": {
            "event_ticker": ticker,
            "title": "Golden Globe Nominations: Best Screenplay",
        },
        "markets": [
            {
                "event_ticker": ticker,
                "ticker": f"{ticker}-WHN",
                "rules_primary": RULE.replace("84th Golden Globe Awards", label),
                "rules_secondary": "The close time is a settlement deadline.",
            }
        ],
    }


def database(tickers):
    result = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: tickers))
    return SimpleNamespace(execute=AsyncMock(return_value=result))


@pytest.mark.parametrize("shape", ["separate", "nested", "both"])
def test_native_market_envelopes_keep_the_verbatim_primary_rule(shape):
    payload = envelope()
    if shape in {"nested", "both"}:
        payload["event"]["markets"] = deepcopy(payload["markets"])
    if shape == "nested":
        del payload["markets"]
    normalized = source.kalshi_occasion_event(payload, TICKER)

    assert normalized["provider"] == "kalshi"
    assert normalized["markets"][0]["rules_primary"] == RULE
    assert "provider" not in payload["event"]


@pytest.mark.parametrize(
    "change,reason",
    [
        (
            lambda payload: payload["event"].update(event_ticker="KXOTHER-26"),
            "event_identity_mismatch",
        ),
        (lambda payload: payload.pop("markets"), "missing_market_envelope"),
        (lambda payload: payload.update(markets={}), "missing_market_envelope"),
        (lambda payload: payload["markets"].append(None), "market_identity_mismatch"),
        (
            lambda payload: payload["markets"][0].update(event_ticker="KXOTHER-26"),
            "market_identity_mismatch",
        ),
        (
            lambda payload: payload["event"].update(markets=[]),
            "conflicting_market_envelopes",
        ),
    ],
)
def test_inconsistent_or_missing_venue_inputs_fail_explicitly(change, reason):
    payload = envelope()
    change(payload)
    with pytest.raises(source.AwardsOccasionSourceError, match=reason):
        source.kalshi_occasion_event(payload, TICKER)


async def test_the_worker_reads_new_ceremonies_from_the_stored_pool_without_a_roster():
    new_ticker = "KXNEW-PIC42"
    requests = []

    def respond(request):
        requests.append(request)
        ticker = request.url.path.rsplit("/", 1)[-1]
        label = (
            "17th New Film Awards"
            if ticker == new_ticker
            else "84th Golden Globe Awards"
        )
        return httpx.Response(200, json=envelope(ticker, label))

    service = KalshiAPIService()
    await service.client.aclose()
    service.client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    db = database([TICKER, new_ticker])
    try:
        discovery = await source.read_kalshi_awards_occasions(db, service)
    finally:
        await service.close()

    assert [occasion.label for occasion in discovery.occasions] == [
        "17th New Film Awards",
        "84th Golden Globe Awards",
    ]
    assert discovery.refused == ()
    assert discovery.occasions[1].events[0].evidence == (RULE,)
    assert all(
        request.url.params["with_nested_markets"] == "true" for request in requests
    )
    statement = str(
        db.execute.await_args.args[0].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "futures_markets.source = 'kalshi'" in statement
    assert "futures_markets.status = 'open'" in statement
    assert "SELECT DISTINCT" in statement
    assert "LIMIT 101" in statement
    assert "Golden" not in statement and "KXGG" not in statement


async def test_missing_and_invalid_provider_ids_keep_their_refusal_reasons():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        service = SimpleNamespace(client=client, BASE_URL=KalshiAPIService.BASE_URL)
        discovery = await source.read_kalshi_awards_occasions(
            database([TICKER, "bad/id", None]),
            service,
        )
    assert discovery.occasions == ()
    assert discovery.refused == (
        ("kalshi", "", "invalid_identity"),
        ("kalshi", TICKER, "provider_event_missing"),
        ("kalshi", "bad/id", "invalid_identity"),
    )
    assert len(requests) == 1


@pytest.mark.parametrize("status", [429, 500])
async def test_transport_failures_never_return_a_partial_discovery(status):
    def respond(request):
        if request.url.path.endswith(TICKER):
            return httpx.Response(200, json=envelope())
        return httpx.Response(status)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        service = SimpleNamespace(client=client, BASE_URL=KalshiAPIService.BASE_URL)
        with pytest.raises(httpx.HTTPStatusError):
            await source.read_kalshi_awards_occasions(
                database([TICKER, "KXNEW-26"]), service
            )


async def test_candidate_overflow_aborts_before_any_venue_request():
    service = SimpleNamespace(client=SimpleNamespace(get=AsyncMock()))
    db = database([TICKER] * (source.MAX_AWARDS_EVENT_CANDIDATES + 1))
    with pytest.raises(
        source.AwardsOccasionSourceError, match="candidate_limit_exceeded"
    ):
        await source.read_kalshi_awards_occasions(db, service)
    service.client.get.assert_not_awaited()


async def test_an_empty_stored_pool_does_not_call_the_venue():
    service = SimpleNamespace(client=SimpleNamespace(get=AsyncMock()))
    discovery = await source.read_kalshi_awards_occasions(database([]), service)
    assert discovery.occasions == discovery.refused == ()
    service.client.get.assert_not_awaited()


async def test_the_total_budget_includes_the_database_read(monkeypatch):
    monkeypatch.setattr(source, "AWARDS_SOURCE_BUDGET_SECONDS", 0.01)

    async def blocked(statement):
        await asyncio.Event().wait()

    db = SimpleNamespace(execute=blocked)
    with pytest.raises(TimeoutError):
        await source.read_kalshi_awards_occasions(db, SimpleNamespace())


async def test_caller_cancellation_propagates_during_the_venue_read():
    entered = asyncio.Event()

    async def blocked(request):
        entered.set()
        await asyncio.Event().wait()

    async with httpx.AsyncClient(transport=httpx.MockTransport(blocked)) as client:
        service = SimpleNamespace(client=client, BASE_URL=KalshiAPIService.BASE_URL)
        task = asyncio.create_task(
            source.read_kalshi_awards_occasions(database([TICKER]), service)
        )
        await asyncio.wait_for(entered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


def test_the_saved_response_entrypoint_outputs_a_reproducible_proposal(
    tmp_path, monkeypatch, capsys
):
    path = tmp_path / "venue-event.json"
    path.write_text(json.dumps(envelope()), encoding="utf-8")
    script = (
        Path(__file__).resolve().parents[1] / "scripts" / "propose_awards_occasions.py"
    )
    monkeypatch.setattr(sys, "argv", [str(script), "--source-file", str(path)])
    runpy.run_path(str(script), run_name="__main__")

    price, proposal = map(json.loads, capsys.readouterr().out.splitlines())
    assert price == {"model_cost_usd": 0, "state": "proposed"}
    assert proposal["source_scope"] == "saved_venue_responses"
    assert proposal["model_cost_usd"] == 0
    assert proposal["occasions"][0]["label"] == "84th Golden Globe Awards"
    assert proposal["occasions"][0]["events"][0]["evidence"] == [RULE]
    assert proposal["occasions"][0]["ceremony_date"] is None
    assert proposal["occasions"][0]["selector"] == {
        "evidence": "primary_rules_ordinal_awards",
        "label": "84th Golden Globe Awards",
    }
    assert proposal["refused"] == []


@pytest.mark.parametrize("failed_read", [False, True])
async def test_live_entrypoint_enforces_connection_bounds_and_always_disposes(
    monkeypatch, failed_read
):
    from sqlalchemy.ext import asyncio as sqlalchemy_async
    from app.services import database as database_service, kalshi_api

    script = (
        Path(__file__).resolve().parents[1] / "scripts" / "propose_awards_occasions.py"
    )
    read_live = runpy.run_path(str(script))["read_live"]
    engine = SimpleNamespace(dispose=AsyncMock())
    service = SimpleNamespace(close=AsyncMock())
    db = object()
    captured = {}

    def create_engine(url, **kwargs):
        captured.update(kwargs)
        return engine

    class Session:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *error):
            return False

    monkeypatch.setattr(
        database_service, "DATABASE_URL", "postgresql+asyncpg://localhost/awards_test"
    )
    monkeypatch.setattr(sqlalchemy_async, "create_async_engine", create_engine)
    monkeypatch.setattr(
        sqlalchemy_async, "async_sessionmaker", lambda *args, **kwargs: Session
    )
    monkeypatch.setattr(kalshi_api, "KalshiAPIService", lambda: service)
    reader = AsyncMock(
        side_effect=TimeoutError("source deadline") if failed_read else None
    )
    monkeypatch.setitem(read_live.__globals__, "read_kalshi_awards_occasions", reader)

    if failed_read:
        with pytest.raises(TimeoutError, match="source deadline"):
            await read_live()
    else:
        assert await read_live() is reader.return_value

    settings = captured["connect_args"]["server_settings"]
    assert settings["default_transaction_read_only"] == "on"
    assert int(settings["statement_timeout"]) == 750
    assert int(settings["lock_timeout"]) == 250
    assert captured["hide_parameters"] is True
    reader.assert_awaited_once_with(db, service)
    service.close.assert_awaited_once()
    engine.dispose.assert_awaited_once()

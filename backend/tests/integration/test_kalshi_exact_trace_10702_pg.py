"""#10702: actual tennis socket->writer->blend->encoded publication on local PG.

Reuse #8129's isolated eight-table schema and #10667's socket fixture. Only
provider transport/auth and Redis transport are recorded. The consumer, task
sessions, statement, rank, blend resolver, revision trigger, snapshot, commit
hooks and frame encoder run unchanged. This is no browser-delivery receipt.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import json
import time

import pytest
from sqlalchemy import event as sa_event

from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport
import app.tasks.base as task_base
import app.tasks.kalshi_ws as task
from app.tasks.live_blend_refresh import LiveBlendRefresher
from tests.integration.test_live_blend_grouped_commit_8129_pg import (
    DB_URL,
    rig as pg_rig,
)
from tests.test_event_frame_batching_10659 import ProtocolRedis
from tests.test_kalshi_ws_lifecycle_dispatch_10667 import (
    Feed,
    connect as socket_connect,
)

rig = pg_rig
connect = socket_connect
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]

EVENT = 15326313
MARKET = 64627535
OUTCOME = 243069703
MARKET_TICKER = "KXATPCHALLENGERDOUBLES-26OCT07BARVOCMARWAL"
TICKER = MARKET_TICKER + "-BARVOC"


@pytest.mark.parametrize("fail_stage", [None, "price", "event"])
async def test_existing_full_path_and_outer_rollback_marks(
    rig, connect, monkeypatch, caplog, fail_stage
):
    now = datetime.now(timezone.utc)
    async with rig.maker() as session:
        sport = Sport(key="tennis_atp", name="ATP")
        session.add(sport)
        await session.flush()
        session.add(
            Event(
                id=EVENT,
                sport_id=sport.id,
                home_team_name="Barrientos / Vocel",
                away_team_name="Martos Gornes / Walkow",
                commence_time=now - timedelta(minutes=1),
                status="live",
                win_probability_sources={},
                opening_home_probability=0.5,
            )
        )
        session.add(
            FuturesMarket(
                id=MARKET,
                sport_id=sport.id,
                event_id=EVENT,
                source="kalshi",
                external_id=MARKET_TICKER,
                name="Barrientos / Vocel vs Martos Gornes / Walkow",
                category="game",
                status="open",
                market_type="duel",
            )
        )
        await session.flush()
        session.add(
            FuturesOutcome(
                id=OUTCOME,
                market_id=MARKET,
                external_id=TICKER,
                name="Barrientos / Vocel",
                current_probability=0.5,
                rank=1,
                last_updated=now,
            )
        )
        await session.commit()

    if fail_stage:

        @sa_event.listens_for(rig.engine.sync_engine, "before_cursor_execute")
        def changed(conn, _cursor, statement, _parameters, _context, _many):
            if statement.startswith("UPDATE futures_outcomes"):
                conn.info["trace10702_stage"] = "price"
            elif statement.startswith("UPDATE events"):
                conn.info["trace10702_stage"] = "event"

        @sa_event.listens_for(rig.engine.sync_engine, "commit")
        def refused(conn):
            if conn.info.pop("trace10702_stage", None) == fail_stage:
                raise RuntimeError("injected outer COMMIT failure")

        @sa_event.listens_for(rig.engine.sync_engine, "rollback")
        def rolled_back(conn):
            conn.info.pop("trace10702_stage", None)

    frame = json.dumps(
        {
            "type": "ticker",
            "msg": {
                "market_ticker": TICKER,
                "price_dollars": ".80",
                "yes_bid_dollars": ".66",
                "yes_ask_dollars": ".70",
                "ts": 1791391849,
            },
        }
    )
    feed = Feed([frame])
    connect(feed)
    client = ProtocolRedis()
    monkeypatch.setattr(task_base, "_get_task_engine", lambda: rig.engine)
    monkeypatch.setattr(LiveBlendRefresher, "_client", lambda _self: client)
    monkeypatch.setattr(task, "SUBSCRIPTION_REFRESH_SECONDS", 0.4)
    monkeypatch.setattr(task, "PRICE_FLUSH_SECONDS", 0.02)
    monkeypatch.setenv("KALSHI_API_KEY_ID", "fixture-id")
    monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "fixture-secret")
    monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "0")
    monkeypatch.setenv("WS_KALSHI_TRACE_TICKERS", TICKER)
    monkeypatch.setenv("WS_KALSHI_TRACE_EXPIRES_AT", str(time.time() + 60))
    caplog.set_level("INFO")
    await asyncio.wait_for(task._run_kalshi_ws_consumer(), 5)
    records = [
        json.loads(r.message.split("kalshi-exact-trace ", 1)[1])
        for r in caplog.records
        if r.message.startswith("kalshi-exact-trace ")
    ]
    decision = next(r for r in records if r["stage"] == "DECISION")
    assert decision["reason"] == "ACCEPTED" and decision[
        "probability"
    ] == pytest.approx(0.68)
    async with rig.maker() as session:
        stored = await session.get(FuturesOutcome, OUTCOME)
        event = await session.get(Event, EVENT)
        price, observed_at, source, revision = (
            float(stored.current_probability),
            stored.last_updated,
            event.win_probability_sources,
            event.win_probability_sources_rev,
        )
    if fail_stage == "price":
        assert price == 0.5 and not source
        assert any(r["stage"] == "PRICE_NOT_COMMITTED" for r in records)
        assert not any(
            r["stage"] in ("PRICE_COMMITTED", "EVENT_COMMITTED", "EVENT_PUBLICATION")
            for r in records
        )
        return
    commit = next(r for r in records if r["stage"] == "PRICE_COMMITTED")
    assert (
        price == pytest.approx(0.68) and commit["stored_at"] == observed_at.isoformat()
    )
    assert (
        commit["input_seq"] == decision["input_seq"]
        and commit["receive_id"] == decision["receive_id"]
    )
    if fail_stage == "event":
        assert not source
        assert not any(
            r["stage"] in ("EVENT_COMMITTED", "EVENT_PUBLICATION") for r in records
        )
        return
    publication = next(r for r in records if r["stage"] == "EVENT_PUBLICATION")
    assert source["kalshi"]["value"] == pytest.approx(0.68)
    assert (
        publication["input_seq"] == decision["input_seq"]
        and publication["revision"] == revision
    )
    assert publication["publication"] == "REDIS_ACK"
    event_frames = [
        json.loads(payload)
        for _verb, channel, payload in client.commands
        if channel == f"live:event:{EVENT}"
    ]
    assert len(event_frames) == 1 and event_frames[0]["p"] == pytest.approx(0.68)
    assert event_frames[0]["rev"] == {str(EVENT): revision}

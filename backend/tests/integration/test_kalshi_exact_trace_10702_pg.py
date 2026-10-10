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
from app.utils.kalshi_exact_trace import ExactKalshiTrace
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


def _published(commands):
    """(channel, payload) per recorded publication: a bare PUBLISH, or the
    retain-and-publish EVAL a revisioned frame takes (88a4a5cad3)."""
    return [
        (cmd[4], cmd[5]) if cmd[0] == "EVAL" else (cmd[1], cmd[2])
        for cmd in commands
    ]


@pytest.mark.parametrize("fail_stage", [None, "price", "event"])
@pytest.mark.parametrize("repeat_race", [False, True])
@pytest.mark.parametrize("trace_enabled", [True, False])
async def test_existing_full_path_and_outer_rollback_marks(
    rig, connect, monkeypatch, caplog, fail_stage, repeat_race, trace_enabled
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
    expected = 0.465 if repeat_race else 0.68
    if repeat_race:
        # Real consumer snapshot/PG-dispatch race: 100 identical newer inputs
        # evict the original from accepted64 before its actual COMMIT. Then a
        # moving input is itself superseded by its identical latest repeat.
        release, consumed = asyncio.Event(), asyncio.Event()
        moved = json.dumps(
            {
                "type": "ticker",
                "msg": {
                    "market_ticker": TICKER,
                    "price_dollars": ".47",
                    "yes_bid_dollars": ".46",
                    "yes_ask_dollars": ".47",
                },
            }
        )

        class RacingFeed(Feed):
            async def __anext__(self):
                if self.read == 1:
                    await release.wait()
                if self.read == len(self.frames):
                    consumed.set()
                return await super().__anext__()

        feed = RacingFeed([frame] * 101 + [moved, moved])
        injected = False

        @sa_event.listens_for(rig.engine.sync_engine, "before_cursor_execute")
        def repeat_burst(conn, _cursor, statement, _parameters, _context, _many):
            nonlocal injected
            if not injected and statement.startswith("UPDATE futures_outcomes"):
                injected = True
                release.set()

                async def await_inputs(_driver):
                    await asyncio.wait_for(consumed.wait(), 1)

                conn.connection.dbapi_connection.run_async(await_inputs)

        # Simulate the elapsed receive clock, never delay the consumer itself.
        factory = ExactKalshiTrace.from_env
        clock = [time.time(), time.monotonic()]

        def configured(env, **kwargs):
            trace = factory(env, **kwargs, wall=lambda: clock[0], mono=lambda: clock[1])
            if trace is None:
                return None
            original = trace.received

            def received(connection, msg):
                clock[0] += 0.61
                clock[1] += 0.61
                original(connection, msg)

            trace.received = received
            return trace

        monkeypatch.setattr(ExactKalshiTrace, "from_env", configured)
    else:
        feed = Feed([frame])
    connect(feed)
    client = ProtocolRedis()
    # The consumer's one shared engine asks the real factory signature for its
    # retained pool (b74d99451b); the rig's engine stands in for what it builds.
    engine_requests = []

    def task_engine(*, statement_timeout_ms=None, lock_timeout_ms=None,
                    retain_full_pool=False):
        engine_requests.append(
            (statement_timeout_ms, lock_timeout_ms, retain_full_pool)
        )
        return rig.engine

    monkeypatch.setattr(task_base, "_get_task_engine", task_engine)
    monkeypatch.setattr(LiveBlendRefresher, "_client", lambda _self: client)
    monkeypatch.setattr(
        task, "SUBSCRIPTION_REFRESH_SECONDS", 2.5 if repeat_race else 0.4
    )
    monkeypatch.setattr(task, "PRICE_FLUSH_SECONDS", 0.02)
    # d1a2bcb366: an unchanged routine refresh no longer recycles the run.
    # These sockets never acknowledge a subscription, so the first routine
    # refresh rebuilds them — ending the run where the old timer recycle did.
    monkeypatch.setattr(task, "SUBSCRIBE_ACK_DEADLINE_SECONDS", 0.0)
    monkeypatch.setenv("KALSHI_API_KEY_ID", "fixture-id")
    monkeypatch.setenv("KALSHI_RSA_PRIVATE_KEY", "fixture-secret")
    monkeypatch.setenv("WS_OPEN_CONTRACT_PRICES", "0")
    monkeypatch.setenv("WS_KALSHI_TRACE_TICKERS", TICKER if trace_enabled else "")
    monkeypatch.setenv("WS_KALSHI_TRACE_EXPIRES_AT", str(time.time() + 120))
    caplog.set_level("INFO")
    await asyncio.wait_for(task._run_kalshi_ws_consumer(), 5)
    assert engine_requests == [(None, None, True)]
    records = [
        json.loads(r.message.split("kalshi-exact-trace ", 1)[1])
        for r in caplog.records
        if r.message.startswith("kalshi-exact-trace ")
    ]
    if not trace_enabled:
        assert not records
        async with rig.maker() as session:
            stored = await session.get(FuturesOutcome, OUTCOME)
            event = await session.get(Event, EVENT)
            assert float(stored.current_probability) == pytest.approx(
                0.5 if fail_stage == "price" else expected
            )
            if fail_stage is not None:
                assert not event.win_probability_sources
            else:
                assert event.win_probability_sources["kalshi"][
                    "value"
                ] == pytest.approx(expected)
                frames = [
                    json.loads(payload)
                    for channel, payload in _published(client.commands)
                    if channel == f"live:event:{EVENT}"
                ]
                assert len(frames) == (2 if repeat_race else 1)
                assert frames[-1]["p"] == pytest.approx(expected)
                assert frames[-1]["rev"] == {
                    str(EVENT): event.win_probability_sources_rev
                }
        return
    decisions = [r for r in records if r["stage"] == "DECISION"]
    decision = (
        max(decisions, key=lambda r: r["input_seq"]) if repeat_race else decisions[0]
    )
    assert decision["reason"] == "ACCEPTED" and decision[
        "probability"
    ] == pytest.approx(expected)
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
    commit = next(
        r
        for r in records
        if r["stage"] == "PRICE_COMMITTED" and r["input_seq"] == decision["input_seq"]
    )
    assert (
        price == pytest.approx(expected)
        and commit["stored_at"] == observed_at.isoformat()
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
    publication = next(
        r
        for r in records
        if r["stage"] == "EVENT_PUBLICATION" and r["input_seq"] == decision["input_seq"]
    )
    assert source["kalshi"]["value"] == pytest.approx(expected)
    assert (
        publication["input_seq"] == decision["input_seq"]
        and publication["revision"] == revision
    )
    assert publication["publication"] == "REDIS_ACK"
    event_frames = [
        json.loads(payload)
        for channel, payload in _published(client.commands)
        if channel == f"live:event:{EVENT}"
    ]
    assert len(event_frames) == (2 if repeat_race else 1)
    assert event_frames[-1]["p"] == pytest.approx(expected)
    assert event_frames[-1]["rev"] == {str(EVENT): revision}
    if repeat_race:
        assert decision["input_seq"] == decision["receive_id"] == 103
        assert publication["input_seq"] == 103
        early_commit = next(r for r in records if r["stage"] == "PRICE_COMMITTED")
        assert early_commit["input_seq"] == early_commit["receive_id"] == 1
        received = next(
            r for r in records if r["stage"] == "RECEIVED" and r["receive_id"] == 103
        )
        assert received["receive_wall"] - records[0]["receive_wall"] > 60
        assert len(records) < 40 and not any(r["stage"] == "STOP" for r in records)

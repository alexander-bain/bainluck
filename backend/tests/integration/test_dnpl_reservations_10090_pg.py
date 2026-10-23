"""Fresh canonical graph and locked reservation migration on actual PG/Redis."""

from datetime import datetime, timezone
import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils import blend_preview as bp
from app.utils.preview_reservations import ReservationPolicy
from tests.integration.test_live_blend_grouped_commit_8129_pg import (
    DB_URL,
    rig as _rig_fixture,
    seed,
)  # noqa: F401
from tests.test_blend_preview_ledger_tsp1_10090 import (
    redis_kwargs as _redis_fixture,
    SOURCES,
)  # noqa: F401

# Imported fixture objects remain available under the harness names.
rig = _rig_fixture
redis_kwargs = _redis_fixture

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL, reason="requires disposable SEARCH_TEST_DATABASE_URL"
    ),
]


@pytest.fixture
async def actors(rig, redis_kwargs, monkeypatch):
    client = Redis(**redis_kwargs)
    registry = bp.LedgerRegistry(
        sources=SOURCES, policy=ReservationPolicy((1, 0, 1, 0, 1, 0))
    )
    await registry.claim(client.execute_command, "polymarket")
    await registry.claim(client.execute_command, "kalshi")
    monkeypatch.setattr(bp, "registry", lambda: registry)
    worker = LiveBlendRefresher("polymarket", session_factory=rig.maker)
    monkeypatch.setattr(worker, "_client", lambda: client)
    # Cases invoke bounded maintenance explicitly, avoiding unrelated timers.
    worker._owns_preview_maintenance = False
    try:
        yield worker, registry, client
    finally:
        await worker._close_preview_maintenance()
        await client.aclose()


async def graph(rig, worker, ids):
    async with rig.maker() as session:
        return await worker._read_groups(session, ids)


async def admit(worker, registry, client, event, eid=1):
    ops = registry.propose(
        eid,
        "polymarket",
        value=0.7,
        event=event,
        row_sources=event.preview_sources,
        row_rev=event.preview_rev,
        stamped_at=datetime.now(timezone.utc),
    )
    assert ops
    assert await registry.prepare(ops, client.execute_command, worker.preview_stats)


async def h(client, key):
    v = await client.hget(bp.LEDGER_KEY, key)
    return None if v is None else v.decode()


async def test_actual_graph_projects_canonical_sport_and_db_clock(rig, actors):
    worker, registry, client = actors
    await seed(rig, 1)
    async with rig.engine.begin() as conn:
        await conn.execute(text("UPDATE sports SET key='americanfootball_nfl'"))
    grouped = await graph(rig, worker, [1])
    event = grouped[1][0]
    assert event.sport_key == "americanfootball_nfl"
    assert event.preview_context_at.tzinfo is not None
    assert event.preview_read_ticket == 0
    await admit(worker, registry, client, event)
    assert await h(client, "e:1:r_bucket") == "0"


async def test_bounded_legacy_classification_progress_survives_restart(rig, actors):
    worker, registry, client = actors
    await seed(rig, 35)
    values = {"nevents": "35", "r:unclassified": "35"}
    for eid in range(1, 36):
        values.update({f"e:{eid}:gen": "2", f"e:{eid}:seq": "1"})
    await client.hset(bp.LEDGER_KEY, mapping=values)
    ticket, candidates, _ = await registry.capacity_ticket(
        client.execute_command, "polymarket"
    )
    await worker._classify_preview_residents(ticket, candidates)
    assert await h(client, "r:unclassified") == "3"
    replacement = bp.LedgerRegistry(sources=SOURCES, policy=registry.policy)
    await replacement.claim(client.execute_command, "polymarket")
    ticket, candidates, _ = await replacement.capacity_ticket(
        client.execute_command, "polymarket"
    )
    assert set(candidates[:3]) == {33, 34, 35}
    # Same worker caller, current source owner: adopt replacement explicitly.
    registry.claims["polymarket"] = replacement.claims["polymarket"]
    await worker._classify_preview_residents(ticket, candidates[:3])
    assert await h(client, "r:unclassified") == "0"
    assert await h(client, "r:count:0") == "35"
    assert await h(client, "e:1:gen") == "2" and await h(client, "e:1:seq") == "1"
    await registry.capacity_ticket(client.execute_command, "polymarket")
    assert (
        registry.capacity_status["debt"] == 34 and not registry.capacity_status["ready"]
    )


async def test_policy_retirement_skips_locked_active_row_then_reclaims_clean_context(
    rig, actors
):
    worker, registry, client = actors
    await seed(rig, 1)
    event = (await graph(rig, worker, [1]))[1][0]
    await admit(worker, registry, client, event)
    await registry.prepare(
        registry.refused(1, "polymarket", "settled"),
        client.execute_command,
        worker.preview_stats,
    )
    ticket, _ = await registry.read_ticket(client.execute_command, "polymarket")
    async with rig.maker() as held:
        await held.execute(text("SELECT id FROM events WHERE id=1 FOR UPDATE"))
        await worker._retire_policy_preview_event(1, ticket)
        assert await h(client, "e:1:gen") is not None
        await held.rollback()
    await worker._retire_policy_preview_event(1, ticket)
    assert await h(client, "e:1:gen") is None
    async with rig.maker() as session:
        assert (
            await session.execute(text("SELECT status FROM events WHERE id=1"))
        ).scalar_one() == "live"
    assert await h(client, "r:count:0") == "0"


async def test_locked_policy_proof_rechecks_sibling_pending_and_holds_lock_through_ack(
    rig, actors, monkeypatch
):
    worker, registry, client = actors
    await seed(rig, 1)
    event = (await graph(rig, worker, [1]))[1][0]
    await admit(worker, registry, client, event)
    await registry.prepare(
        registry.refused(1, "polymarket", "settled"),
        client.execute_command,
        worker.preview_stats,
    )
    original = worker._prepare_ledger_previews
    witnessed = []

    async def race(items):
        if items and items[0].get("ledger_op") == "retire_policy":
            async with rig.maker() as independent:
                with pytest.raises(Exception, match="could not obtain lock"):
                    await independent.execute(
                        text("SELECT id FROM events WHERE id=1 FOR UPDATE NOWAIT")
                    )
                await independent.rollback()
            witnessed.append(True)
            # Sibling's valid pending metadata arrives after the idle hint.
            ticket, _ = await registry.read_ticket(client.execute_command, "kalshi")
            event.preview_read_ticket = ticket
            await registry.prepare(
                registry.propose(
                    1,
                    "kalshi",
                    value=0.61,
                    event=event,
                    row_sources=event.preview_sources,
                    row_rev=event.preview_rev,
                ),
                client.execute_command,
                worker.preview_stats,
            )
        return await original(items)

    monkeypatch.setattr(worker, "_prepare_ledger_previews", race)
    ticket, _ = await registry.read_ticket(client.execute_command, "polymarket")
    await worker._retire_policy_preview_event(1, ticket)
    assert witnessed == [True]
    assert await h(client, "e:1:gen") is not None
    assert await h(client, "e:1:m:kalshi") is not None


async def test_complete_maintenance_preserves_held_reader_while_reclaiming_clean_neighbor(
    rig, actors
):
    """Both maintenance paths run, with real delivery and nonvacuous reclamation."""
    import json
    from app.utils.live_push import event_channel
    from tests.test_blend_preview_ledger_tsp1_10090 import Reader

    worker, registry, client = actors
    await seed(rig, 2)
    async with rig.engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sports (id, key, name, active) VALUES (99, 'basketball_wnba', 'WNBA', true)"
            )
        )
        await conn.execute(text("UPDATE events SET sport_id=99 WHERE id=2"))
    grouped = await graph(rig, worker, [1, 2])
    subscriber = client.pubsub()
    await subscriber.subscribe(event_channel(1), event_channel(2))
    await subscriber.get_message(timeout=1)
    await subscriber.get_message(timeout=1)
    try:
        for eid in (1, 2):
            event = grouped[eid][0]
            await registry.execute(
                registry.propose(
                    eid,
                    "polymarket",
                    value=0.7,
                    event=event,
                    row_sources=event.preview_sources,
                    row_rev=event.preview_rev,
                ),
                client.execute_command,
                event_channel,
                worker.preview_stats,
            )
            message = await subscriber.get_message(
                ignore_subscribe_messages=True, timeout=1
            )
            assert message is not None
            if eid == 1:
                held = json.loads(message["data"])
        reader = Reader()
        reader.after(held)
        before = {
            key: await h(client, "e:1:" + key) for key in ("m:polymarket", "gen", "seq")
        }
        event = grouped[2][0]
        await registry.prepare(
            registry.committed(
                2,
                "polymarket",
                seq=registry.pending_seq(2, "polymarket"),
                sources=event.preview_sources,
                rev=event.preview_rev,
            ),
            client.execute_command,
            worker.preview_stats,
        )
        assert await h(client, "nevents") == "2"
        await worker._maintain_preview_capacity()
        assert {key: await h(client, "e:1:" + key) for key in before} == before
        assert await h(client, "e:2:gen") is None
        assert await h(client, "r:count:0") == "1"
        assert await h(client, "r:count:2") == "0"
        assert await h(client, "nevents") == "1"
        message = await subscriber.get_message(
            ignore_subscribe_messages=True, timeout=1
        )
        assert message is not None
        revoked = json.loads(message["data"])
        assert revoked["event_id"] == 2 and revoked["preview"]["kind"] == "revoke"
        assert (
            await subscriber.get_message(ignore_subscribe_messages=True, timeout=0.05)
            is None
        )
        assert reader.held is not None
        assert worker.preview_stats["publish_errors"] == 0
    finally:
        await subscriber.aclose()

"""Actual hub dispatch: guarded previews, committed bypass, receipt and cleanup."""

import asyncio
from dataclasses import replace
import json
from time import monotonic

import pytest

from app.utils.dnpl_authority_fanout import AuthorityFanout
from app.utils.dnpl_authority_transport import encode_preview
from app.utils.dnpl_redis_authority import namespace_keys, validate_namespace
from app.utils.live_fanout import CLOSED, LiveFanout, Subscription, mailbox_age_ms
from app.utils.live_push import event_channel, parse_frame
from tests.test_dnpl_authority_fanout_10090 import authority
from tests.test_dnpl_redis_authority_10090 import rig, initial, call  # noqa: F401
from tests.test_blend_preview_ledger_tsp1_10090 import redis_kwargs  # noqa: F401

pytestmark = pytest.mark.asyncio


def frame():
    return {
        "event_id": 42,
        "p": 0.6,
        "status": "live",
        "provisional": True,
        "preview": {
            "kind": "blend",
            "epoch": 2,
            "seq": 1,
            "base_rev": 10,
            "ttl_ms": 60000,
        },
    }


def attach(hub, channel, *, v3):
    sub = Subscription(channel, authority_v3=v3)
    hub._subscribers.setdefault(channel, set()).add(sub)
    return sub


async def test_real_redis_validated_hub_keeps_legacy_readers_isolated(
    rig,  # noqa: F811 - imported pytest fixture
):  # noqa: F811
    client, preparing = rig
    await initial(client, preparing)
    await call(client, preparing, "claim", "kalshi")
    ready = replace(preparing, state="ready")
    hub = LiveFanout()
    new = attach(hub, event_channel(42), v3=True)
    old = attach(hub, event_channel(42), v3=False)
    reads = []

    async def read():
        reads.append(1)
        return ready

    hub._new_authority_validator = lambda: AuthorityFanout(
        read,
        lambda a: validate_namespace(client, a),
        hub._authority_deliver,
        hub._authority_reconnect,
    )
    try:
        wire = encode_preview(ready, frame())
        assert parse_frame(wire) is None, "old hubs must never parse a v3 preview"
        before = monotonic()
        hub._dispatch({"channel": event_channel(42), "data": wire})
        received = await new.next(1)
        assert json.loads(received) == frame()
        assert received.authority == ready
        assert before <= received.received_at <= monotonic()
        assert old._queue.empty()
        assert len(reads) == 1
    finally:
        await hub.aclose()


async def test_validation_never_blocks_committed_dispatch_or_restarts_receipt():
    a = authority()
    hub = LiveFanout()
    new = attach(hub, event_channel(42), v3=True)
    old = attach(hub, event_channel(42), v3=False)
    started, release = asyncio.Event(), asyncio.Event()

    async def read():
        started.set()
        await release.wait()
        return a

    async def verify(a):
        return True

    hub._new_authority_validator = lambda: AuthorityFanout(
        read, verify, hub._authority_deliver, hub._authority_reconnect
    )
    try:
        before = monotonic()
        hub._dispatch(
            {"channel": event_channel(42), "data": encode_preview(a, frame())}
        )
        await asyncio.wait_for(started.wait(), 1)
        committed = '{"event_id":42,"rev":{"42":11},"p":0.7}'
        hub._dispatch({"channel": event_channel(42), "data": committed})
        assert str(await new.next(0.01)) == committed
        assert str(await old.next(0.01)) == committed
        after_queue = monotonic()
        release.set()
        received = await new.next(1)
        assert before <= received.received_at <= after_queue
        assert mailbox_age_ms(received) >= (after_queue - received.received_at) * 1000
    finally:
        await hub.aclose()


@pytest.mark.parametrize(
    "mutation", ["duplicate", "wrong_channel", "uuid_type", "committed", "oversize"]
)
async def test_bad_v3_input_reconnects_only_opted_in_reader(mutation):
    hub = LiveFanout()
    new = attach(hub, event_channel(42), v3=True)
    old = attach(hub, event_channel(42), v3=False)
    wire = encode_preview(authority(), frame())
    if mutation == "duplicate":
        wire = wire.replace('"event_id":42', '"event_id":42,"event_id":42')
    elif mutation == "wrong_channel":
        wire = wire.replace('"event_id":42', '"event_id":43')
    elif mutation == "uuid_type":
        packet = json.loads(wire[6:])
        packet["authority"]["namespace"] = 123
        wire = "DNPL3 " + json.dumps(packet)
    elif mutation == "committed":
        wire = wire.replace('"event_id":42', '"event_id":42,"rev":{"42":10}')
    else:
        wire += " " * 16384
    try:
        hub._dispatch({"channel": event_channel(42), "data": wire})
        assert await new.next(0.01) is CLOSED
        assert not new.authority_v3
        assert old._queue.empty()
        assert hub._authority_validator is None
    finally:
        await hub.aclose()


async def test_close_joins_validator_before_releasing_shared_client():
    a = authority()
    hub = LiveFanout()
    attach(hub, event_channel(42), v3=True)
    started = asyncio.Event()

    async def read():
        started.set()
        await asyncio.Event().wait()

    async def verify(a):
        pytest.fail("cancelled read must not reach Redis")

    hub._new_authority_validator = lambda: AuthorityFanout(
        read, verify, hub._authority_deliver, hub._authority_reconnect
    )
    hub._dispatch({"channel": event_channel(42), "data": encode_preview(a, frame())})
    await asyncio.wait_for(started.wait(), 1)
    worker = hub._authority_validator._worker
    await hub.aclose()
    assert worker.done()
    assert hub._authority_validator is None


@pytest.mark.parametrize(
    "damage", ["guard", "ledger", "marker", "epoch", "identity", "policy"]
)
async def test_atomic_namespace_validation_refuses_damage_without_writes(
    rig, damage  # noqa: F811 - imported pytest fixture
):  # noqa: F811
    client, a = rig
    await initial(client, a)
    await call(client, a, "claim", "kalshi")
    a = replace(a, state="ready")
    assert await validate_namespace(client, a)
    keys = namespace_keys(a)
    if damage == "guard":
        await client.set(keys[5], "dirty")
    elif damage in ("ledger", "marker", "epoch"):
        await client.delete(keys[{"ledger": 0, "marker": 1, "epoch": 2}[damage]])
    elif damage == "identity":
        a = replace(a, redis_run_id="0" * 40)
    else:
        await client.hset(keys[0], "reservation_policy", "wrong")
    before = {key: await client.dump(key) for key in keys}
    assert not await validate_namespace(client, a)
    assert before == {key: await client.dump(key) for key in keys}

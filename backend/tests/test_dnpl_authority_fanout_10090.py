"""Deciding local controls for the bounded authority fanout worker."""

import asyncio
from dataclasses import replace
from time import monotonic
from uuid import uuid4

import pytest

from app.services.dnpl_authority import Authority
from app.utils.dnpl_authority_fanout import AuthorityFanout, PreviewReceipt

pytestmark = pytest.mark.asyncio


def authority():
    return Authority(3, 1, uuid4(), uuid4(), "ready", "1" * 40, "2" * 40, "policy")


class Rig:
    def __init__(self):
        self.authority = authority()
        self.reads = 0
        self.redis_checks = 0
        self.delivered = []
        self.reconnections = []
        self.changed = asyncio.Event()
        self.read_started = asyncio.Event()
        self.release_read = asyncio.Event()
        self.release_read.set()
        self.redis_ok = True
        self.gate = AuthorityFanout(
            self.read, self.verify, self.deliver, self.reconnect
        )
        self.gate.start()

    async def read(self):
        self.reads += 1
        self.read_started.set()
        await self.release_read.wait()
        return self.authority

    async def verify(self, authority):
        self.redis_checks += 1
        return self.redis_ok

    def deliver(self, receipt):
        self.delivered.append(receipt)
        self.changed.set()

    def reconnect(self, channels):
        self.reconnections.append(channels)
        self.changed.set()

    def receipt(self, index=0, **kwargs):
        return PreviewReceipt(
            str(index),
            str(index),
            self.authority,
            kwargs.get("received_at", monotonic()),
        )


async def wait(event):
    await asyncio.wait_for(event.wait(), 1)


async def test_fifo_batches_share_fresh_reads_and_preserve_receipt():
    r = Rig()
    try:
        records = [r.receipt(i) for i in range(33)]
        for record in records:
            assert r.gate.offer(record)
        await wait(r.changed)
        assert r.delivered == records
        assert all(a is b for a, b in zip(r.delivered, records))
        assert r.reads == r.redis_checks == 3
        assert not r.reconnections
    finally:
        await r.gate.aclose()


async def test_arrival_during_read_requires_next_read():
    r = Rig()
    try:
        r.release_read.clear()
        first, second = r.receipt(1), r.receipt(2)
        r.gate.offer(first)
        await wait(r.read_started)
        r.gate.offer(second)
        r.release_read.set()
        await wait(r.changed)
        assert r.delivered == [first, second]
        assert r.reads == 2
    finally:
        await r.gate.aclose()


async def test_overflow_invalidates_inflight_and_queue_without_replay():
    r = Rig()
    try:
        r.release_read.clear()
        r.gate.offer(r.receipt(0))
        await wait(r.read_started)
        for i in range(1, 65):
            assert r.gate.offer(r.receipt(i))
        assert not r.gate.offer(r.receipt(65))
        assert r.reconnections == [frozenset(str(i) for i in range(66))]
        # Let the previously running read complete; it must not deliver its
        # revoked batch after overflow. The same worker handles later input.
        r.gate.offer(r.receipt(66))
        r.changed.clear()
        r.release_read.set()
        await wait(r.changed)
        assert [x.channel for x in r.delivered] == ["66"]
        assert r.reads == 2
    finally:
        await r.gate.aclose()


@pytest.mark.parametrize("failure", ["disabled", "new_domain", "redis", "timeout"])
async def test_uncertain_authority_reconnects_and_never_delivers(failure):
    r = Rig()
    try:
        record = r.receipt()
        if failure == "disabled":
            r.authority = replace(r.authority, state="disabled")
        elif failure == "new_domain":
            r.authority = replace(r.authority, incarnation=2, namespace=uuid4())
        elif failure == "redis":
            r.redis_ok = False
        else:
            r.release_read.clear()
        r.gate.offer(record)
        await wait(r.changed)
        assert not r.delivered
        assert r.reconnections == [frozenset((record.channel,))]
    finally:
        await r.gate.aclose()


async def test_expired_queue_budget_does_not_start_database_read():
    r = Rig()
    try:
        r.gate.offer(r.receipt(received_at=monotonic() - 0.151))
        await wait(r.changed)
        assert r.reads == 0
        assert not r.delivered
        assert r.reconnections
    finally:
        await r.gate.aclose()


async def test_shutdown_cancels_and_joins_inflight_read():
    r = Rig()
    r.release_read.clear()
    r.gate.offer(r.receipt())
    await wait(r.read_started)
    await r.gate.aclose()
    assert r.gate._worker.done()
    assert not r.delivered
    assert r.reconnections == [frozenset(("0",))]
    assert not r.gate.offer(r.receipt(1))
    with pytest.raises(RuntimeError, match="cannot be restarted"):
        r.gate.start()


@pytest.mark.parametrize("payload", [b"x" * 16385, "é" * 8193], ids=["bytes", "utf8"])
async def test_oversize_payload_is_refused_before_queueing(payload):
    r = Rig()
    try:
        record = replace(r.receipt(), payload=payload)
        assert not r.gate.offer(record)
        assert r.reads == 0
        assert not r.delivered
        assert r.reconnections == [frozenset(("0",))]
    finally:
        await r.gate.aclose()


async def test_redis_verification_is_inside_same_operation_budget():
    r = Rig()
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def blocked_redis(authority):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    r.gate._verify_redis = blocked_redis
    try:
        r.gate.offer(r.receipt())
        await wait(entered)
        await wait(r.changed)
        assert cancelled.is_set()
        assert not r.delivered
        assert r.reconnections == [frozenset(("0",))]
    finally:
        await r.gate.aclose()

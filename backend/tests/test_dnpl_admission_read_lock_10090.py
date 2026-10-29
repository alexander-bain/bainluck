"""A busy publisher must not consume a claimed producer's read-ticket budget.

Use the existing private Redis authority rig. Publication retains its lock;
the only new concurrency is an already-claimed, fenced admission read.
"""
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.tasks.live_blend_refresh import LiveBlendRefresher
from app.utils import blend_preview
from tests.test_dnpl_authority_registry_10090 import registry, proposal
from tests.test_dnpl_redis_authority_10090 import rig as _rig_fixture, initial
from tests.test_blend_preview_ledger_tsp1_10090 import redis_kwargs  # noqa: F401

pytestmark = pytest.mark.asyncio
rig = _rig_fixture


async def setup_worker(rig, monkeypatch, *, claimed=True, source="kalshi"):
    client, authority = rig
    await initial(client, authority)
    now = datetime.now(timezone.utc)
    reg = registry(authority, now)
    reg.claim_lock = asyncio.Lock()
    if claimed:
        await reg.claim(client.execute_command, source)
    worker = LiveBlendRefresher(source)
    monkeypatch.setattr(blend_preview, "registry", lambda: reg)
    monkeypatch.setattr(worker, "_client", lambda: client)
    monkeypatch.setattr(worker, "_start_preview_maintenance", lambda: None)
    return client, authority, now, reg, worker


@pytest.mark.parametrize("source", ["kalshi", "polymarket"])
async def test_claimed_admission_survives_busy_publication(rig, monkeypatch, source):
    client, _, now, reg, worker = await setup_worker(rig, monkeypatch, source=source)
    entered, release = asyncio.Event(), asyncio.Event()
    original = reg.execute

    async def held_publication(*args, **kwargs):
        # Represent a publication batch between Redis calls. A fresh admission
        # needs a different socket, not the publisher's local mutation lock.
        # (kwargs: the send's read-only observer, #10090 preview receipt.)
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)

    monkeypatch.setattr(reg, "execute", held_publication)
    ops = await proposal(reg, client.execute_command, source, now=now)
    publishing = asyncio.create_task(worker._publish_previews(ops))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        ticket = await worker._preview_admission_read()
        assert ticket is not None, "publisher consumed the 250ms admission budget"
        assert not publishing.done() and reg.claim_lock.locked()
        assert ticket.owner == reg.claims[source]
        assert ticket.authority == reg.authority
        # Freshly read eligible NBA event, no existing chain that could hide a
        # lost ticket by continuing an already admitted preview.
        new_ops = reg.propose(
            43, source, value=.7,
            event=SimpleNamespace(
                status="live", sport_key="basketball_nba", commence_time=now,
                completed_at=None, preview_context_at=now, preview_read_ticket=ticket,
                espn_win_prob_home=None, opening_home_probability=None,
            ),
            row_sources={s: {"value": .5, "updated_at": now.isoformat()}
                         for s in ("kalshi", "polymarket")},
            row_rev=10, observed_basis={"1": now.timestamp()}, stamped_at=now,
        )
        assert new_ops, "eligible new event lost its preview admission"
    finally:
        release.set()
        await publishing
    assert worker.preview_stats["published"] == 1
    await worker._publish_previews(new_ops)
    assert worker.preview_stats["published"] == 2


async def test_unclaimed_reader_still_waits_for_claim_lock(rig, monkeypatch):
    _, _, _, reg, worker = await setup_worker(rig, monkeypatch, claimed=False)
    async with reg.claim_lock:
        assert await worker._preview_admission_read() is None
        assert reg.claims == {}


async def test_concurrent_first_reads_claim_only_once(rig, monkeypatch):
    _, _, _, reg, worker = await setup_worker(rig, monkeypatch, claimed=False)
    original = worker._claim_preview_epoch
    calls = []

    async def claim(connection, preview):
        calls.append(True)
        await asyncio.sleep(0)
        await original(connection, preview)

    monkeypatch.setattr(worker, "_claim_preview_epoch", claim)
    tickets = await asyncio.gather(*(worker._preview_ticket() for _ in range(3)))
    assert len(calls) == 1
    assert all(ticket is not None and ticket.owner == reg.claims["kalshi"]
               for ticket, _ in tickets)


async def test_fenced_claimed_reader_is_refused_by_redis(rig, monkeypatch):
    client, authority, now, reg, worker = await setup_worker(rig, monkeypatch)
    successor = registry(authority, now)
    await successor.claim(client.execute_command, "kalshi")
    assert await worker._preview_ticket() == (None, [])
    assert not reg.unclaimed("kalshi"), "fencing must not automatically reclaim ownership"


async def test_capacity_read_retains_serialization(rig, monkeypatch):
    _, _, _, reg, worker = await setup_worker(rig, monkeypatch)
    async with reg.claim_lock:
        with pytest.raises(TimeoutError):
            async with asyncio.timeout(.02):
                await worker._preview_ticket(include_candidates=True)
    ticket, _, _, _ = await worker._preview_ticket(include_candidates=True)
    assert ticket is not None

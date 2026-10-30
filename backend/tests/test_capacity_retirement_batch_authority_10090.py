"""#10090: a capacity retirement batch runs on the production ticket type.

PILLARS: TRUTH / FORMATTING. SHIP: idle and finished games stop holding preview
slots, so a busy live game in the full "Other" group gets the sub-second preview.

Production builds `AuthorityLedgerRegistry`, whose tickets are `AuthorityTicket`
dataclasses (authority, source, owner, barrier), not ints. v5963 (#11760) sent
item k with ``ticket + acknowledged`` and every capacity pass on both venues
ended ``end=error`` on ``TypeError: ... 'AuthorityTicket' and 'int'``; it was
rolled back as v5964. The batch tests beside this file pass int tickets, so
they could not see it. These cases run the batch through the real authority
registry, its real tickets and the guarded Lua on a private Redis.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.utils import blend_preview as bp
from app.utils.dnpl_authority_registry import AuthorityTicket
from app.utils.dnpl_redis_authority import namespace_keys
from tests.test_blend_preview_ledger_tsp1_10090 import BASE10, redis_kwargs  # noqa: F401
from tests.test_dnpl_authority_registry_10090 import registry
from tests.test_dnpl_redis_authority_10090 import initial, rig  # noqa: F401

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def ledger(rig):  # noqa: F811 - imported pytest fixture
    client, a = rig
    await initial(client, a)
    now = datetime.now(timezone.utc)
    k, p = registry(a, now), registry(a, now)
    call = client.execute_command
    await k.claim(call, "kalshi")
    await p.claim(call, "polymarket")
    return client, call, k, p, now, namespace_keys(replace(a, state="ready"))[0]


async def idle_resident(call, reg, eid, now):
    """A future-scheduled resident whose preview's commit already landed."""
    ticket, _ = await reg.read_ticket(call, "kalshi")
    event = type("Row", (), dict(
        status="scheduled", sport_key="new_unknown_league",
        commence_time=now + timedelta(hours=1), completed_at=None,
        preview_context_at=now, preview_read_ticket=ticket,
        espn_win_prob_home=None, opening_home_probability=None))()
    stats = {}
    ops = reg.propose(eid, "kalshi", value=0.7, event=event, row_sources=BASE10, row_rev=10,
                      observed_basis={"1": (now - timedelta(seconds=1)).timestamp()},
                      stamped_at=now)
    assert ops
    assert await reg.prepare(ops, call, stats)
    await reg.prepare(reg.committed(eid, "kalshi", seq=reg.pending_seq(eid, "kalshi"),
                                    sources=BASE10, rev=10), call, stats)


async def batch(call, reg, ids, *, ticket=None):
    fresh, _, _, redis_ms = await reg.capacity_ticket(call, "kalshi")
    ticket = fresh if ticket is None else ticket
    assert isinstance(ticket, AuthorityTicket)
    items = [reg.retire_idle(eid, "kalshi", 10, ticket, redis_ms + 1000) for eid in ids]
    assert all(item is not None for item in items)
    stats = {}
    return await reg.prepare_retirements(items, call, stats), stats


async def test_one_authority_ticket_reclaims_every_idle_resident_of_the_batch(ledger):
    client, call, k, _, now, key = ledger
    for eid in (1, 2, 3):
        await idle_resident(call, k, eid, now)
    before = int(await client.hget(key, "retired"))
    frames, stats = await batch(call, k, [1, 2, 3])
    assert stats.get("capacity_reclaimed") == 3, stats
    assert int(await client.hget(key, "retired")) == before + 3
    assert all([await client.hget(key, f"e:{eid}:gen") is None for eid in (1, 2, 3)])
    assert [(f["event_id"], f["preview"]["kind"], f["preview"]["reason"]) for f in frames] == [
        (1, "revoke", "idle"), (2, "revoke", "idle"), (3, "revoke", "idle")]


async def test_a_foreign_retirement_mid_batch_still_refuses_the_later_items(ledger):
    client, call, k, p, now, key = ledger
    for eid in (1, 2, 3):
        await idle_resident(call, k, eid, now)
    fresh, _, _, redis_ms = await k.capacity_ticket(call, "kalshi")
    items = [k.retire_idle(eid, "kalshi", 10, fresh, redis_ms + 1000) for eid in (1, 2, 3)]
    sent = []

    async def sends(*args):
        reply = await call(*args)
        if "retire_idle" in args:
            sent.append(bp._ledger_text(reply[0]))
            if len(sent) == 1:
                # The other venue's ordered absence invalidation moves the barrier.
                ticket, _ = await p.read_ticket(call, "polymarket")
                await p.prepare([p.terminal_read(999, "polymarket", 1, ticket)], call, {})
        return reply

    stats = {}
    await k.prepare_retirements(items, sends, stats)
    assert sent == ["ok", "read_required"]
    assert stats.get("capacity_reclaimed") == 1
    assert await client.hget(key, "e:1:gen") is None
    assert await client.hget(key, "e:2:gen") is not None


async def test_a_stale_authority_ticket_retires_nothing(ledger):
    client, call, k, _, now, key = ledger
    for eid in (1, 2):
        await idle_resident(call, k, eid, now)
    stale, _, _, _ = await k.capacity_ticket(call, "kalshi")
    await idle_resident(call, k, 3, now)
    await batch(call, k, [3], ticket=stale)       # moves the barrier past `stale`
    _, stats = await batch(call, k, [1, 2], ticket=stale)
    assert "capacity_reclaimed" not in stats
    assert await client.hget(key, "e:1:gen") is not None
    assert await client.hget(key, "e:2:gen") is not None


async def test_a_batch_still_carries_one_authority_ticket(ledger):
    _, call, k, _, now, _ = ledger
    for eid in (1, 2):
        await idle_resident(call, k, eid, now)
    ticket, _, _, redis_ms = await k.capacity_ticket(call, "kalshi")
    items = [k.retire_idle(1, "kalshi", 10, ticket, redis_ms + 1000),
             k.retire_idle(2, "kalshi", 10, replace(ticket, barrier=ticket.barrier + 1),
                           redis_ms + 1000)]
    with pytest.raises(ValueError):
        await k.prepare_retirements(items, call, {})

"""#10090: one capacity retirement batch per proof, on the real ledger script.

PILLARS: TRUTH / FORMATTING. SHIP: idle and finished games stop holding preview
slots, so a busy live game in the full "Other" group gets the sub-second preview.

`LedgerRegistry.prepare_retirements` sends a batch proved by ONE locked DB
read after ONE ticket. Each acknowledged retirement advances the barrier by
exactly one, so item k is sent with ticket + (acknowledgements so far). These
cases pin the protections that counting must keep: a foreign retirement still
refuses every later item, a refusal never counts, a late batch stops.
"""
from datetime import timedelta

import pytest

from app.utils import blend_preview as bp
from tests.test_blend_preview_ledger_tsp1_10090 import BASE10, NOW
from tests.test_preview_reservations_redis_10090 import deadline, prepare, redis_kwargs, rig  # noqa: F401

L = bp.LEDGER_KEY
START = NOW + timedelta(hours=1)


async def idle_resident(rig, eid):
    """A future-scheduled resident whose preview's commit already landed."""
    assert await prepare(rig, rig.k, "kalshi", eid, status="scheduled", start=START)
    await rig.k.prepare(
        rig.k.committed(eid, "kalshi", seq=rig.k.pending_seq(eid, "kalshi"),
                        sources=BASE10, rev=10),
        rig.call, rig.stats)


async def resident(rig, eid):
    return await rig.hget(f"e:{eid}:gen") is not None


async def barrier(rig):
    return int(await rig.hget("retired"))


class Sends:
    """The batch's Redis calls; `after_first` runs once the first retire is answered."""

    def __init__(self, rig, after_first=None):
        self.rig, self.after_first, self.retires = rig, after_first, []

    async def __call__(self, *args):
        reply = await self.rig.call(*args)
        if "retire_idle" in args or "retire_policy" in args:
            self.retires.append(bp._ledger_text(reply[0]))
            if self.after_first is not None and len(self.retires) == 1:
                await self.after_first()
        return reply


async def batch(rig, ids, *, ticket=None, late=False, call=None):
    if ticket is None:
        ticket, _ = await rig.k.read_ticket(rig.call, "kalshi")
    cutoff = await deadline(rig)
    items = [rig.k.retire_idle(eid, "kalshi", 10, ticket, 0 if late else cutoff) for eid in ids]
    return await rig.k.prepare_retirements(items, call or rig.call, rig.stats)


async def test_one_ticket_reclaims_every_idle_resident_of_the_batch(rig):
    for eid in (1, 2, 3):
        await idle_resident(rig, eid)
    before = await barrier(rig)
    sends = Sends(rig)
    frames = await batch(rig, [1, 2, 3], call=sends)
    assert sends.retires == ["ok", "ok", "ok"]
    assert not any([await resident(rig, e) for e in (1, 2, 3)])
    assert await barrier(rig) == before + 3
    assert rig.stats["capacity_reclaimed"] == 3
    assert [(f["event_id"], f["preview"]["kind"], f["preview"]["reason"]) for f in frames] == [
        (1, "revoke", "idle"), (2, "revoke", "idle"), (3, "revoke", "idle")]


async def test_a_foreign_retirement_mid_batch_refuses_every_later_item(rig):
    for eid in (1, 2, 3):
        await idle_resident(rig, eid)

    async def foreign():
        # The other venue's ordered absence invalidation moves the barrier.
        ticket, _ = await rig.p.read_ticket(rig.call, "polymarket")
        await rig.p.prepare([rig.p.terminal_read(999, "polymarket", 1, ticket)],
                            rig.call, rig.stats)

    sends = Sends(rig, after_first=foreign)
    await batch(rig, [1, 2, 3], call=sends)
    # Item 2 is refused exactly as a stale single ticket would be; the batch
    # stops there and never sends item 3.
    assert sends.retires == ["ok", "read_required"]
    assert not await resident(rig, 1)
    assert await resident(rig, 2) and await resident(rig, 3)
    assert rig.stats["capacity_reclaimed"] == 1


async def test_a_refused_item_is_not_counted_and_its_siblings_still_retire(rig):
    await idle_resident(rig, 1)
    # Event 2 keeps a valid preview a reader can see: Redis refuses it.
    assert await prepare(rig, rig.k, "kalshi", 2, status="scheduled", start=START)
    await idle_resident(rig, 3)
    sends = Sends(rig)
    await batch(rig, [1, 2, 3], call=sends)
    assert sends.retires == ["ok", "pending", "ok"]
    assert await resident(rig, 2) and await rig.hget("e:2:m:kalshi") is not None
    assert not await resident(rig, 1) and not await resident(rig, 3)
    assert rig.stats["capacity_reclaimed"] == 2


async def test_a_batch_past_its_redis_deadline_stops_at_the_first_item(rig):
    for eid in (1, 2):
        await idle_resident(rig, eid)
    before = await rig.client.hgetall(L)
    sends = Sends(rig)
    assert await batch(rig, [1, 2], late=True, call=sends) == []
    assert sends.retires == ["late"]
    assert await rig.client.hgetall(L) == before


async def test_a_batch_carries_one_proof_ticket(rig):
    for eid in (1, 2):
        await idle_resident(rig, eid)
    ticket, _ = await rig.k.read_ticket(rig.call, "kalshi")
    cutoff = await deadline(rig)
    items = [rig.k.retire_idle(1, "kalshi", 10, ticket, cutoff),
             rig.k.retire_idle(2, "kalshi", 10, ticket + 1, cutoff)]
    before = await rig.client.hgetall(L)
    with pytest.raises(ValueError):
        await rig.k.prepare_retirements(items, rig.call, rig.stats)
    assert await rig.client.hgetall(L) == before


async def test_a_stale_proof_ticket_retires_nothing(rig):
    for eid in (1, 2):
        await idle_resident(rig, eid)
    ticket, _ = await rig.k.read_ticket(rig.call, "kalshi")
    await idle_resident(rig, 3)
    await batch(rig, [3], ticket=ticket)          # moves the barrier past `ticket`
    sends = Sends(rig)
    await batch(rig, [1, 2], ticket=ticket, call=sends)
    assert sends.retires == ["read_required"]
    assert await resident(rig, 1) and await resident(rig, 2)

"""#10090: the observation drain's price-buffer scan reads only the legs it asks about.

`flush_observations.owners()` walked every buffered Polymarket leg on each
observation flush (and again in every send-time recheck) — the top self frame
in production, 7.1–7.4 % at 23:43Z on `942ccaf4`. Only the pending events'
ownership is ever read, so the scan now reads only their legs, and none at all
when something cheaper (a withdrawal, a stamp, a write) already owns them.

Executed consumer closures (`consumer_rig`); a leg value that counts its own
`float()` reads stands in for the scan's per-leg work.
"""

import pytest

from tests.test_blend_preview_display_before_persist_195 import _blends
from tests.test_fresh_observation_preview_10090 import preview_enabled  # noqa: F401
from tests.test_pm_observation_beside_price_10090 import consumer_rig, start_unrelated, warm


class Counted(float):
    """A buffered price that records every time the scan reads it."""

    reads = 0

    def __float__(self):
        Counted.reads += 1
        return float.__float__(self)


def acknowledged_leg(rig, oid, event, value):
    """A buffered leg whose value is acknowledged and uninterrupted, so the
    scan reaches its `float()` read and still finds it owns nothing."""
    token = (object(), round(float.__float__(value), 6))
    rig.ns['event_id_by_outcome'][oid] = event
    rig.ns['observation_continuity'][oid] = token
    rig.boundary.observation_ack[oid] = token
    rig.ns['price_buffer'][oid] = value


@pytest.fixture(autouse=True)
def reset_reads():
    Counted.reads = 0


async def test_unrelated_buffered_legs_are_never_read(monkeypatch):
    rig = consumer_rig(monkeypatch)
    await warm(rig)
    for oid in range(5000, 5050):
        acknowledged_leg(rig, oid, 500 + oid % 5, Counted(.25))
    await rig.feed()
    await rig.ns['flush_observations']()
    assert _blends(rig.frames), 'the free event still advances'
    assert Counted.reads == 0, f'{Counted.reads} unrelated legs were read'


async def test_an_event_a_withdrawal_already_owns_skips_the_scan(monkeypatch):
    rig = consumer_rig(monkeypatch)
    await warm(rig)
    await rig.feed()
    acknowledged_leg(rig, 102, 1, Counted(rig.values[102]))
    rig.ns['withdraw_buffer'][101] = (.01, .99)
    await rig.ns['flush_observations']()
    assert not _blends(rig.frames)
    assert 101 in rig.boundary.observation_pending
    assert Counted.reads == 0, 'an owned event needs no price-buffer scan'


@pytest.mark.parametrize('partner', ['unacknowledged', 'no-continuity', 'changed', 'acknowledged', 'non-blend'])
@pytest.mark.parametrize('noise', [False, True])
async def test_only_the_same_events_partner_decides_and_unrelated_noise_never_does(monkeypatch, partner, noise):
    """Equivalence guard: green before and after the cut."""
    rig = consumer_rig(monkeypatch)
    await warm(rig)
    task = await start_unrelated(rig)  # event 90 is buffered and mid-write throughout
    try:
        await rig.feed()
        if noise:
            # Unrelated legs that would own their own events.
            for oid in range(7000, 7020):
                rig.ns['event_id_by_outcome'][oid] = 700
                rig.ns['price_buffer'][oid] = .3
        # A fresh partner leg of event 1, buffered beside the pending pair.
        rig.ns['event_id_by_outcome'][103] = 1
        if partner == 'no-continuity':
            rig.ns['price_buffer'][103] = .5
        else:
            acknowledged_leg(rig, 103, 1, .5)
            if partner == 'unacknowledged':
                rig.boundary.observation_ack[103] = (object(), .5)
            elif partner == 'changed':
                rig.ns['price_buffer'][103] = .55
            elif partner == 'non-blend':
                rig.ns['non_blend_outcome_ids'].add(103)
                rig.boundary.observation_ack.pop(103)
        await rig.ns['flush_observations']()
        if partner in ('acknowledged', 'non-blend'):
            assert _blends(rig.frames)
            assert 101 not in rig.boundary.observation_pending
        else:
            assert not _blends(rig.frames)
            assert 101 in rig.boundary.observation_pending
        assert not task.done()
    finally:
        rig.release.set()
        await task


async def test_a_stamp_with_unknown_membership_still_refuses_everything(monkeypatch):
    rig = consumer_rig(monkeypatch)
    await warm(rig)
    await rig.feed()
    owner = rig.boundary.stamp_owner(rig.r)
    owner.task = type('Running', (), {'done': lambda self: False})()
    owner.events = None
    try:
        await rig.ns['flush_observations']()
    finally:
        owner.task = None
    assert not _blends(rig.frames)
    assert 101 in rig.boundary.observation_pending

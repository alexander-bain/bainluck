"""Failing recovery cohort beside healthy reads on one projector's 2 slots / 8 pending.

Recovery may hold 1 slot and 4 pending entries, leaving the four healthy readers theirs.

Injected authority with a fixed per-load cost; measures what the cohort costs the
healthy normal path, not production SQL latency or PG capacity.

Runs on `VirtualClockLoop`: the loads' fixed cost and the latency bound read one
clock that a loaded runner cannot stretch.
"""
import asyncio
import json
import statistics
import pytest
from app.routes import event_stream as route
from app.utils import live_fanout, folded_live_quote as fq
from tests.test_normal_recovery_projection159 import notice, quote, stop
from tests.test_folded_event_stream_invalidation_837 import Hub, Request
from tests.test_event_stream_recovery_read_controls_10090 import data, until
from tests._virtual_clock_loop import VirtualClockPolicy

pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def event_loop_policy():
    return VirtualClockPolicy()

LOAD_S = 0.02
HEALTHY = range(21, 25)
COHORT = range(1, 13)


@pytest.mark.parametrize('failure', ['none', 'fast', 'blocked'])
async def test_failing_cohort_beside_healthy_reads(monkeypatch, failure):
    hub = Hub(); projector = fq.FoldedQuoteProjector(); restored = asyncio.Event()
    calls = []; active = 0; peak = 0; max_pending = 0; recovering = 0; recovery_peak = 0; recovery_pending = 0
    recovery_waiting = 0
    async def load(eid, origin, rev):
        nonlocal active, peak, max_pending, recovering, recovery_peak, recovery_pending, recovery_waiting
        active += 1; peak = max(peak, active); max_pending = max(max_pending, len(projector._pending))
        recovering += eid in COHORT; recovery_peak = max(recovery_peak, recovering)
        recovery_pending = max(recovery_pending, sum(1 for key in projector._pending if key[-1]))
        recovery_waiting = max(recovery_waiting, projector._recovery_waiting)
        calls.append((eid, restored.is_set()))
        try:
            await asyncio.sleep(LOAD_S)
            if eid in COHORT and not restored.is_set():
                if failure == 'blocked':
                    await restored.wait()
                else:
                    return None
            return {**quote(), 'event_id': eid, 'blend_fold_revision': {str(eid): rev}}
        finally:
            active -= 1; recovering -= eid in COHORT
    async def project(eid, frame): return await projector.project(eid, frame, fresh=True)
    async def coverage(eid, ids): return {'event_id': eid, 'custody_id': 'state:test', 'removal_rev': {str(i): 2 for i in ids}}
    monkeypatch.setattr(fq, 'load_folded_quote', load)
    monkeypatch.setattr(live_fanout, 'fanout', lambda: hub)
    monkeypatch.setattr(route, '_current_reconcile', coverage)
    monkeypatch.setattr(route, 'latest_frames', lambda ids: asyncio.sleep(0, result=[]))
    hub.project_recovery_quote = project
    chunks = {eid: [] for eid in COHORT}; delivered = {}
    async def collect(eid):
        async for item in route._stream(eid, Request()):
            chunks[eid].append(item)
            if 'event: folded_probability\n' in item: delivered[eid] = asyncio.get_running_loop().time()
    latencies = []; refused = []
    async def healthy(eid):
        rev = 3
        while True:
            began = asyncio.get_running_loop().time()
            # A new revision each read: every read is a real load, never a cache hit.
            result = await projector.project(eid, notice(eid, rev))
            latencies.append(asyncio.get_running_loop().time() - began)
            if result is None: refused.append(eid)
            rev += 1
            await asyncio.sleep(.1)
    tasks = [asyncio.create_task(collect(eid)) for eid in chunks] if failure != 'none' else []
    readers = []
    try:
        if tasks:
            await until(lambda: all(data(x, 'reconcile') for x in chunks.values()), tasks[0], 'all streams open')
        readers = [asyncio.create_task(healthy(eid)) for eid in HEALTHY]
        for eid in chunks if tasks else ():
            hub.subscriptions[f'live:event:{eid}'].offer(json.dumps(notice(eid)))
        await asyncio.sleep(4.1)
        for reader in readers: await stop(reader)
        failing = sum(eid in COHORT and not ok for eid, ok in calls)
        restored_at = asyncio.get_running_loop().time(); restored.set()
        if tasks:
            await until(lambda: len(delivered) == len(COHORT), tasks[0], 'cohort recovers beside healthy reads', within=1.0)
        ordered = sorted(latencies)
        result = {
            'failure': failure, 'healthy_reads': len(latencies), 'healthy_refused': len(refused),
            'healthy_p50_s': statistics.median(ordered), 'healthy_p95_s': ordered[int(.95 * (len(ordered) - 1))],
            'healthy_max_s': ordered[-1], 'failing_loads': failing, 'max_active': peak,
            'max_pending': max_pending, 'max_recovery_active': recovery_peak,
            'max_recovery_pending': recovery_pending, 'max_recovery_waiting': recovery_waiting,
            'restoration_s': max(delivered.values()) - restored_at if delivered else None,
        }
        print(json.dumps(result))
        assert peak <= 2 and max_pending <= fq.MAX_PENDING
        # The repair's reservation: recovery never holds both slots or the pending budget.
        assert recovery_peak <= fq.RECOVERY_MAX_SLOTS == 1
        assert recovery_pending <= fq.RECOVERY_MAX_PENDING == fq.MAX_PENDING - len(HEALTHY)
        # Waiting recovery reads hold nothing and stay counted inside MAX_PENDING.
        assert recovery_pending + recovery_waiting <= fq.MAX_PENDING
        assert all(len(data(x, 'folded_probability')) == 1 for x in chunks.values()) if tasks else True
        assert not refused, f'{len(refused)} healthy reads refused beside the failing cohort'
        # Healthy work waits for at most both slots' current loads plus its own.
        assert ordered[-1] < 3 * LOAD_S + .05, 'healthy read held behind failing recovery work'
    finally:
        restored.set()
        for reader in readers: await stop(reader)
        for task in tasks: await stop(task)
        assert not projector._pending and active == 0

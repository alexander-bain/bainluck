"""Controlled orchestration only: no PG/browser/HTTP acceptance."""
import asyncio
import json
import pytest
from app.routes import event_stream as route
from app.utils import live_fanout, folded_live_quote as fq
from tests.test_normal_recovery_projection159 import notice, quote, stop
from tests.test_folded_event_stream_invalidation_837 import Hub, Request
from tests.test_event_stream_recovery_read_controls_10090 import data, until
pytestmark = pytest.mark.asyncio

async def test_distinct_twelve_events_restore_without_ticks_with_bounded_reads(monkeypatch):
    hub=Hub(); projector=fq.FoldedQuoteProjector(); restored=asyncio.Event()
    attempted=set(); calls=[]; active=0; peak=0; max_pending=0
    async def load(eid, origin, rev):
        nonlocal active, peak, max_pending
        active+=1; peak=max(peak,active); max_pending=max(max_pending,len(projector._pending))
        calls.append((eid,asyncio.get_running_loop().time(),restored.is_set()))
        try:
            await asyncio.sleep(.05)
            attempted.add(eid)
            if not restored.is_set(): return None
            return {**quote(),'event_id':eid,'blend_fold_revision':{str(eid):rev}}
        finally: active-=1
    async def project(eid, frame): return await projector.project(eid,frame,fresh=True)
    async def coverage(eid,ids):
        return {'event_id':eid,'custody_id':'state:test','removal_rev':{str(i):2 for i in ids}}
    monkeypatch.setattr(fq,'load_folded_quote',load)
    monkeypatch.setattr(live_fanout,'fanout',lambda:hub)
    monkeypatch.setattr(route,'_current_reconcile',coverage)
    monkeypatch.setattr(route,'latest_frames',lambda ids:asyncio.sleep(0,result=[]))
    hub.project_recovery_quote=project
    chunks={eid:[] for eid in range(1,13)}; delivered={}
    async def collect(eid):
        async for item in route._stream(eid,Request()):
            chunks[eid].append(item)
            if 'event: folded_probability\n' in item: delivered[eid]=asyncio.get_running_loop().time()
    tasks=[asyncio.create_task(collect(eid)) for eid in chunks]
    try:
        await until(lambda:all(data(c,'reconcile') for c in chunks.values()),tasks[0],'all open',within=2)
        for eid in chunks: hub.subscriptions[f'live:event:{eid}'].offer(json.dumps(notice(eid)))
        await until(lambda:len(attempted)==12,tasks[0],'all initially refused',within=2)
        assert not delivered
        restored_at=asyncio.get_running_loop().time(); restored.set()
        await until(lambda:len(delivered)==12,tasks[0],'all twelve recover',within=1)
        worst=max(delivered.values())-restored_at
        assert worst<1 and peak<=2 and max_pending<=8
        assert len(projector._recovery_retry_after)<=64 and not projector._cached
        assert all(len(data(c,'folded_probability'))==1 for c in chunks.values())
        print(json.dumps({'controlled_seconds_after_restoration':worst,'events':12,
                          'load_attempts':len(calls),'max_active':peak,'max_pending':max_pending}))
    finally:
        for t in tasks: await stop(t)
        assert not projector._pending and active==0

async def test_failed_event_cooldown_is_shared_across_revisions_and_bounded(monkeypatch):
    calls=[]
    async def load(*args): calls.append(args); return None
    monkeypatch.setattr(fq,'load_folded_quote',load)
    projector=fq.FoldedQuoteProjector()
    assert await projector.project(1,notice(),fresh=True) is None
    for rev in range(4,16): assert await projector.project(1,notice(rev=rev),fresh=True) is None
    assert len(calls)==1
    await asyncio.sleep(.26)
    assert await projector.project(1,notice(rev=16),fresh=True) is None
    assert len(calls)==2
    for eid in range(2,70): await projector.project(eid,notice(eid),fresh=True)
    assert len(projector._recovery_retry_after)==64 and not projector._pending

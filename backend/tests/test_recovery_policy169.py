"""Finite sustained-failure cost control; injected authority, not PG capacity."""
import asyncio
import collections
import math
import json
import pytest
from app.routes import event_stream as route
from app.utils import live_fanout, folded_live_quote as fq
from tests.test_normal_recovery_projection159 import notice, quote, stop
from tests.test_folded_event_stream_invalidation_837 import Hub, Request
from tests.test_event_stream_recovery_read_controls_10090 import data, until

pytestmark = pytest.mark.asyncio

def ladder_bound(window):
    # No reader churn: counted cancelled loads do not earn backoff.
    # Count the initial load and all earliest possible ladder fenceposts.
    count=1; elapsed=0.0; failures=1
    while True:
        elapsed += min(fq.RECOVERY_MAX_RETRY_S, fq.RECOVERY_RETRY_S * 2 ** (failures-1))
        if elapsed > window: return count
        count += 1; failures += 1

def probe_bound(window):
    return math.floor(window / fq.RECOVERY_PROBE_S) + 1

@pytest.mark.parametrize('failure',['fast','active','blocked'])
async def test_twelve_events_reduce_failure_work_preserve_subsecond_restoration(monkeypatch,failure):
    hub=Hub();projector=fq.FoldedQuoteProjector();restored=asyncio.Event()
    calls=[];active=0;peak=0;max_pending=0;max_cooldown=0
    async def load(eid,origin,rev):
        nonlocal active,peak,max_pending,max_cooldown
        active+=1;peak=max(peak,active);max_pending=max(max_pending,len(projector._pending));max_cooldown=max(max_cooldown,len(projector._recovery_retry_after))
        calls.append({'event':eid,'time':asyncio.get_running_loop().time(),'restored':restored.is_set()})
        try:
            if not restored.is_set():
                if failure=='blocked':await restored.wait()
                else:return None
            return {**quote(),'event_id':eid,'blend_fold_revision':{str(eid):rev}}
        finally:active-=1
    async def project(eid,frame):return await projector.project(eid,frame,fresh=True)
    async def coverage(eid,ids):return {'event_id':eid,'custody_id':'state:test','removal_rev':{str(i):2 for i in ids}}
    monkeypatch.setattr(fq,'load_folded_quote',load)
    monkeypatch.setattr(live_fanout,'fanout',lambda:hub)
    monkeypatch.setattr(route,'_current_reconcile',coverage)
    monkeypatch.setattr(route,'latest_frames',lambda ids:asyncio.sleep(0,result=[]))
    hub.project_recovery_quote=project;chunks={eid:[] for eid in range(1,13)};delivered={}
    async def collect(eid):
        async for item in route._stream(eid,Request()):
            chunks[eid].append(item)
            if 'event: folded_probability\n' in item:delivered[eid]=asyncio.get_running_loop().time()
    tasks=[asyncio.create_task(collect(eid)) for eid in chunks]
    updater=None
    async def update():
        rev=3
        while True:
            await asyncio.sleep(.5)
            rev+=1
            for eid in chunks:hub.subscriptions[f'live:event:{eid}'].offer(json.dumps(notice(eid,rev)))
    try:
        await until(lambda:all(data(x,'reconcile') for x in chunks.values()),tasks[0],'all streams open')
        began=asyncio.get_running_loop().time()
        for eid in chunks:hub.subscriptions[f'live:event:{eid}'].offer(json.dumps(notice(eid)))
        if failure=='active':updater=asyncio.create_task(update())
        await asyncio.sleep(4.1)
        if updater:await stop(updater)
        assert not delivered
        failure_calls=list(calls);counts=collections.Counter(x['event'] for x in failure_calls)
        assert peak<=2 and max_pending<=8 and max_cooldown<=12
        for eid in chunks:
            times=[x['time'] for x in failure_calls if x['event']==eid]
            assert all(b-a>=.249 for a,b in zip(times,times[1:])),times
        restored_at=asyncio.get_running_loop().time();restored.set()
        await until(lambda:len(delivered)==12,tasks[0],'all final states recover under silence',within=1.0)
        worst=max(delivered.values())-restored_at
        assert all(len(data(x,'folded_probability'))==1 for x in chunks.values())
        print(json.dumps({'failure':failure,'failure_duration_s':restored_at-began,'authority_load_attempts':len(failure_calls),'attempts_per_event':dict(counts),'max_active':peak,'max_pending':max_pending,'max_cooldown_entries':max_cooldown,'restoration_to_last_frame_s':worst}))
        window=restored_at-began
        count_limit=12*ladder_bound(window)+probe_bound(window)
        short_gaps=sum(sum(b-a<.45 for a,b in zip(times,times[1:])) for times in
            [[x['time'] for x in failure_calls if x['event']==eid] for eid in chunks])
        gap_limit=12+probe_bound(window)
        print(json.dumps({'policy':'cap500_no_reader_churn','window_s':window,'count':len(failure_calls),
                         'count_bound':count_limit,'short_gaps':short_gaps,'short_gap_bound':gap_limit}))
        assert len(failure_calls)<=count_limit, 'new revisions must not reset the failure ladder'
        assert short_gaps<=gap_limit, 'one short ladder gap per event plus bounded global probes'

    finally:
        if updater:await stop(updater)
        restored.set()
        for task in tasks:await stop(task)
        assert not projector._pending and not projector._cached and active==0
        count=len(calls);await asyncio.sleep(.3);assert len(calls)==count


async def test_persistent_failure_beside_healthy_traffic_keeps_backoff(monkeypatch):
    projector=fq.FoldedQuoteProjector();calls=[]
    async def load(eid,origin,rev):
        calls.append((eid,asyncio.get_running_loop().time()))
        return None if eid==1 else {**quote(), 'event_id':eid, 'blend_fold_revision':{str(eid):rev}}
    monkeypatch.setattr(fq,'load_folded_quote',load)
    started=asyncio.get_running_loop().time()
    while asyncio.get_running_loop().time()-started<4.1:
        # Successful primary traffic is also an authority-health signal.
        revision=len(calls)+3
        assert await projector.project(2,notice(2,revision)) is not None
        assert await projector.project(1,notice(1,revision),fresh=True) is None
        await asyncio.sleep(.05)
    failures=[t for eid,t in calls if eid==1]
    window=asyncio.get_running_loop().time()-started
    limit=ladder_bound(window)
    print(json.dumps({'arm':'isolated_failure','attempts':len(failures),'window_s':window,'bound':limit}))
    # Continuous healthy traffic prevents darkness: no probe or opening.
    assert len(failures)<=limit
    assert not projector._pending


async def test_lone_event_restores_within_one_second_after_four_second_outage(monkeypatch):
    from tests.test_normal_recovery_projection159 import start
    projector=fq.FoldedQuoteProjector();restored=asyncio.Event();calls=[]
    async def load(eid,origin,rev):
        calls.append(asyncio.get_running_loop().time())
        return quote() if restored.is_set() else None
    async def project(eid,incoming):return await projector.project(eid,incoming,fresh=True)
    monkeypatch.setattr(fq,'load_folded_quote',load)
    hub,chunks,task=await start(monkeypatch,project)
    try:
        began=asyncio.get_running_loop().time()
        hub.subscriptions['live:event:1'].offer(json.dumps(notice()))
        await asyncio.sleep(4.1)
        assert not data(chunks,'folded_probability')
        restored_at=asyncio.get_running_loop().time();restored.set()
        await until(lambda:bool(data(chunks,'folded_probability')),task,'lone final state restores',within=1.0)
        worst=asyncio.get_running_loop().time()-restored_at
        print(json.dumps({'arm':'lone','failure_s':restored_at-began,'restoration_s':worst,'calls':len(calls)}))
        assert len(data(chunks,'folded_probability'))==1
    finally:
        restored.set();await stop(task)
        assert not projector._pending


async def test_many_waiters_count_one_failure_and_cancel_does_not_add_backoff(monkeypatch):
    projector=fq.FoldedQuoteProjector();release=asyncio.Event();calls=0
    async def load(*args):
        nonlocal calls
        calls+=1
        await release.wait()
        return None
    monkeypatch.setattr(fq,'load_folded_quote',load)
    tasks=[asyncio.create_task(projector.project(1,notice(),fresh=True)) for _ in range(12)]
    try:
        await until(lambda:calls==1,tasks[0],'coalesced load entered')
        release.set();await asyncio.gather(*tasks)
        state=projector._recovery_retry_after[1]
        assert state.failures==1 and .249<=state.after-asyncio.get_running_loop().time()<=.25
        assert not projector._pending
        release.clear()
        cancelled=asyncio.create_task(projector.project(2,notice(2),fresh=True))
        await until(lambda:calls==2,cancelled,'second load entered')
        await stop(cancelled)
        assert 2 not in projector._recovery_retry_after
    finally:
        release.set()
        for task in tasks:await stop(task)

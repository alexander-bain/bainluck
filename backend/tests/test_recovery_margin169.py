import asyncio,json,collections
import pytest
from app.utils import folded_live_quote as fq,live_fanout
from app.routes import event_stream as route
from tests.test_normal_recovery_projection159 import notice,quote,stop
from tests.test_folded_event_stream_invalidation_837 import Hub,Request
from tests.test_event_stream_recovery_read_controls_10090 import data,until
pytestmark=pytest.mark.asyncio

async def test_second_restoration_is_subsecond(monkeypatch):
    p=fq.FoldedQuoteProjector();restored=False;calls=0
    async def load(eid,origin,rev):
        nonlocal calls
        if eid==1:calls+=1
        return quote() if eid==2 or restored else None
    monkeypatch.setattr(fq,'load_folded_quote',load)
    for _ in range(3):
        assert await p.project(1,notice(),fresh=True) is None
        await asyncio.sleep(.25)
    assert await p.project(2,notice(2)) is not None
    assert await p.project(1,notice(),fresh=True) is None
    assert p._recovery_retry_after[1].spent
    restored=True;start=asyncio.get_running_loop().time()
    while await p.project(1,notice(),fresh=True) is None:await asyncio.sleep(.25)
    delay=asyncio.get_running_loop().time()-start
    print(json.dumps({'arm':'second_restoration','cap':fq.RECOVERY_MAX_RETRY_S,'restoration_s':delay,'calls':calls}))
    assert delay<1.0

async def test_never_dark_partial_restoration_is_subsecond(monkeypatch):
    p=fq.FoldedQuoteProjector();restored=False;calls=[]
    async def load(eid,origin,rev):
        calls.append((eid,asyncio.get_running_loop().time()))
        return quote() if eid==2 or restored else None
    monkeypatch.setattr(fq,'load_folded_quote',load)
    async def healthy():
        rev=3
        while True:
            assert await p.project(2,notice(2,rev)) is not None
            rev+=1;await asyncio.sleep(.05)
    task=asyncio.create_task(healthy())
    try:
        # Observe five actual failures; restore immediately after the last,
        # rather than choosing a favorable point in its retry interval.
        while len([x for x in calls if x[0]==1])<5:
            assert await p.project(1,notice(),fresh=True) is None
            if len([x for x in calls if x[0]==1])<5:await asyncio.sleep(.25)
        assert not p._dark(asyncio.get_running_loop().time())
        restored=True;start=asyncio.get_running_loop().time()
        while await p.project(1,notice(),fresh=True) is None:await asyncio.sleep(.25)
        delay=asyncio.get_running_loop().time()-start
        print(json.dumps({'arm':'never_dark','cap':fq.RECOVERY_MAX_RETRY_S,'restoration_s':delay,'failure_calls':5}))
        assert delay<1.0
    finally:await stop(task)

async def test_twelve_spent_events_drain_subsecond(monkeypatch):
    hub=Hub();p=fq.FoldedQuoteProjector();restored=False;calls=[];active=0;peak=0
    async def load(eid,origin,rev):
        nonlocal active,peak
        active+=1;peak=max(peak,active)
        calls.append((eid,asyncio.get_running_loop().time(),restored))
        try:
            await asyncio.sleep(0)
            if not restored and eid!=13:return None
            return {**quote(),'event_id':eid,'blend_fold_revision':{str(eid):rev}}
        finally:active-=1
    async def project(eid,frame):return await p.project(eid,frame,fresh=True)
    async def coverage(eid,ids):return {'event_id':eid,'custody_id':'state:test','removal_rev':{str(i):2 for i in ids}}
    monkeypatch.setattr(fq,'load_folded_quote',load);monkeypatch.setattr(live_fanout,'fanout',lambda:hub)
    monkeypatch.setattr(route,'_current_reconcile',coverage);monkeypatch.setattr(route,'latest_frames',lambda ids:asyncio.sleep(0,result=[]))
    hub.project_recovery_quote=project;chunks={eid:[] for eid in range(1,13)};delivered={}
    async def collect(eid):
        async for item in route._stream(eid,Request()):
            chunks[eid].append(item)
            if 'event: folded_probability\n' in item:delivered[eid]=asyncio.get_running_loop().time()
    tasks=[asyncio.create_task(collect(eid)) for eid in chunks]
    try:
        await until(lambda:all(data(x,'reconcile') for x in chunks.values()),tasks[0],'all streams open')
        for eid in chunks:hub.subscriptions[f'live:event:{eid}'].offer(json.dumps(notice(eid)))
        await until(lambda:all(p._recovery_retry_after.get(eid) and p._recovery_retry_after[eid].failures>=3 for eid in chunks),tasks[0],'all retry ladders formed',within=3)
        assert await p.project(13,notice(13)) is not None
        await until(lambda:all(p._recovery_retry_after.get(eid) and p._recovery_retry_after[eid].spent for eid in chunks),tasks[0],'all opening attempts spent',within=2)
        assert not delivered
        # No more successful sibling traffic; do not reset the failure streak.
        restored=True;start=asyncio.get_running_loop().time()
        await until(lambda:len(delivered)==12,tasks[0],'spent cohort drains',within=1.0)
        delays=[t-start for t in delivered.values()]
        print(json.dumps({'arm':'spent_cohort','cap':fq.RECOVERY_MAX_RETRY_S,'restoration_s':max(delays),'first_s':min(delays),'drain_s':max(delays)-min(delays),'failure_calls':sum(not restored_ and eid<=12 for eid,_,restored_ in calls),'max_active':peak,'delivered':len(delivered)}))
        assert all(len(data(x,'folded_probability'))==1 for x in chunks.values())
    finally:
        restored=True
        for task in tasks:await stop(task)
        assert not p._pending and active==0

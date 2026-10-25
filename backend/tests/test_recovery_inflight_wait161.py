"""R1: pending control cannot spin the stream while authority is in flight."""
import asyncio
import json
import pytest
from app.routes import event_stream as route
from app.utils import live_fanout
from tests.test_folded_event_stream_invalidation_837 import Hub
from tests.test_event_stream_recovery_read_controls_10090 import data, until
from tests.test_normal_recovery_projection159 import notice, quote, stop

pytestmark = pytest.mark.asyncio

async def test_two_origins_wait_for_owned_projection_without_busy_loop(monkeypatch):
    hub=Hub();chunks=[];calls=[];checks=[];mailbox=[]
    entered=asyncio.Event();release=asyncio.Event()
    class Request:
        async def is_disconnected(self):
            checks.append(asyncio.get_running_loop().time())
            return False
    async def project(eid,incoming):
        calls.append(incoming['event_id'])
        if len(calls)==1:
            entered.set()
            await release.wait()
        return {**quote(),'blend_fold_revision':{'1':3,'2':3}}
    async def coverage(eid,ids):
        return {'event_id':eid,'custody_id':'state:test','removal_rev':{str(i):2 for i in ids}}
    hub.project_recovery_quote=project
    monkeypatch.setattr(live_fanout,'fanout',lambda:hub)
    monkeypatch.setattr(route,'_current_reconcile',coverage)
    monkeypatch.setattr(route,'latest_frames',lambda ids:asyncio.sleep(0,result=[]))
    original_next=live_fanout.Subscription.next
    async def counted_next(self,*args,**kwargs):
        mailbox.append(asyncio.get_running_loop().time())
        return await original_next(self,*args,**kwargs)
    monkeypatch.setattr(live_fanout.Subscription,'next',counted_next)
    async def collect():
        async for item in route._stream(1,Request(),contributor_ids=[1,2]):chunks.append(item)
    task=asyncio.create_task(collect())
    try:
        await until(lambda:bool(data(chunks,'reconcile')),task,'initial coverage')
        hub.subscriptions['live:event:1'].offer(json.dumps(notice(1)))
        await until(entered.is_set,task,'first projection held')
        hub.subscriptions['live:event:2'].offer(json.dumps(notice(2)))
        await until(lambda:len(data(chunks,'reconcile'))==3,task,'both origin controls delivered')
        before_checks=len(checks);before_mailbox=len(mailbox)
        await asyncio.sleep(.3)
        during_checks=len(checks)-before_checks;during_mailbox=len(mailbox)-before_mailbox
        assert calls==[1],calls
        release.set()
        await until(lambda:len(data(chunks,'folded_probability'))==2,task,'pending control projected once')
        assert calls==[1,2],calls
        print(json.dumps({'held_seconds':.3,'loop_checks':during_checks,'mailbox_next_calls':during_mailbox,'projection_origins':calls}))
        assert during_checks<=3, f'{during_checks} loop passes during one held projection'
        assert during_mailbox<=3, f'{during_mailbox} mailbox waits during one held projection'
    finally:
        release.set()
        await stop(task)
        assert set(hub.released)=={'live:event:1','live:event:2'}

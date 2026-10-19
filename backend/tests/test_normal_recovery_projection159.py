"""Local159: normal-price controls recover committed quotes without blocking prices."""
import asyncio
import json
import pytest
from app.routes import event_stream as route
from app.utils import live_fanout, folded_live_quote as fq
from tests.test_folded_event_stream_invalidation_837 import Hub, Request, frame
from tests.test_event_stream_recovery_read_controls_10090 import data, until

pytestmark = pytest.mark.asyncio

def notice(origin=1, rev=3):
    return {"event_id":origin,"p":None,"rev":{str(origin):rev},"reconcile_only":True,
            "reconcile":{"event_id":origin,"custody_id":f"normal-price:{origin}:{rev}","removal_rev":{str(origin):rev}}}

def quote(rev=3, status="live"):
    return {"event_id":1,"status":status,"blend_fold_revision":{"1":rev},
            "hero_probability":0.673696,"hero_probability_observed_at":"2026-10-19T00:00:00+00:00",
            "win_probability_sources":{"polymarket":{"value":0.78}}}

async def start(monkeypatch, project):
    hub, chunks = Hub(), []
    hub.project_recovery_quote = project
    async def coverage(eid,ids):
        return {"event_id":eid,"custody_id":"state:test","removal_rev":{str(i):2 for i in ids}}
    monkeypatch.setattr(live_fanout,"fanout",lambda:hub)
    monkeypatch.setattr(route,"_current_reconcile",coverage)
    monkeypatch.setattr(route,"latest_frames",lambda ids:asyncio.sleep(0,result=[]))
    async def collect():
        async for item in route._stream(1,Request()):chunks.append(item)
    task=asyncio.create_task(collect())
    await until(lambda:bool(data(chunks,"reconcile")),task,"initial coverage")
    return hub,chunks,task

async def stop(task):
    task.cancel()
    await asyncio.gather(task,return_exceptions=True)

async def test_final_normal_control_recovers_without_new_tick_or_rest(monkeypatch):
    calls=[]
    async def project(eid, incoming):calls.append(incoming);return quote()
    hub,chunks,task=await start(monkeypatch,project)
    try:
        hub.subscriptions["live:event:1"].offer(json.dumps(notice()))
        await until(lambda:bool(data(chunks,"folded_probability")),task,"final committed quote")
        projected=data(chunks,"folded_probability")
        assert len(projected)==1 and projected[0]["folded_quote"]==quote()
        assert len(calls)==1 and not data(chunks,"probability")
        control=data(chunks,"reconcile")[-1]
        assert control==notice()["reconcile"] and "p" not in control
    finally:await stop(task)

@pytest.mark.parametrize("result",[None,quote(rev=2),quote(status="completed")])
async def test_unavailable_stale_or_terminal_projection_preserves_control_only(monkeypatch,result):
    finished=asyncio.Event()
    async def project(*args):finished.set();return result
    hub,chunks,task=await start(monkeypatch,project)
    try:
        hub.subscriptions["live:event:1"].offer(json.dumps(notice()))
        await until(finished.is_set,task,"projection attempted")
        if result is not None and result.get("status") == "completed":
            await asyncio.wait_for(task, 1)
            assert data(chunks,"closed") == [{"reason":"not_live"}]
            assert not data(chunks,"folded_probability")
            assert data(chunks,"reconcile")[-1] == notice()["reconcile"]
            return
        # Feed an ordinary later frame as an explicit processing barrier.
        hub.subscriptions["live:event:1"].offer(json.dumps(frame(1,rev={"1":4})))
        await until(lambda:bool(data(chunks,"probability")),task,"later frame")
        assert not data(chunks,"folded_probability")
        assert data(chunks,"reconcile")[-1]==notice()["reconcile"]
    finally:await stop(task)

@pytest.mark.parametrize("terminal",[False,True])
async def test_pending_projection_does_not_block_prices_and_is_joined_on_exit(monkeypatch,terminal):
    entered,cleaned=asyncio.Event(),asyncio.Event()
    async def project(*args):
        entered.set()
        try:await asyncio.Event().wait()
        finally:cleaned.set()
    hub,chunks,task=await start(monkeypatch,project)
    try:
        hub.subscriptions["live:event:1"].offer(json.dumps(notice()))
        await until(entered.is_set,task,"projection entered")
        hub.subscriptions["live:event:1"].offer(json.dumps(frame(1,status="completed" if terminal else "live",rev={"1":4})))
        if terminal:
            await asyncio.wait_for(task,1)
            assert data(chunks,"closed") and cleaned.is_set()
        else:
            await until(lambda:bool(data(chunks,"probability")),task,"price while projection held")
            assert not cleaned.is_set()
        assert not data(chunks,"folded_probability")
    finally:
        await stop(task)
        assert cleaned.is_set() and hub.released==["live:event:1"]

async def test_recovery_never_reuses_completed_live_cache_after_terminal(monkeypatch):
    state=[quote()];calls=[]
    async def load(*args):calls.append(args);return state[0]
    monkeypatch.setattr(fq,"load_folded_quote",load)
    projector=fq.FoldedQuoteProjector()
    assert (await projector.project(1,notice()))["status"]=="live"
    state[0]=quote(status="completed")
    assert (await projector.project(1,notice(),fresh=True))["status"]=="completed"
    state[0]=quote(rev=4)
    assert (await projector.project(1,notice(),fresh=True))["blend_fold_revision"]=={"1":4}
    assert len(calls)==3 and not projector._pending

async def test_twelve_recipients_share_fresh_read_and_one_cancel_keeps_others(monkeypatch):
    calls=[];release=asyncio.Event()
    async def load(*args):calls.append(args);await release.wait();return quote()
    monkeypatch.setattr(fq,"load_folded_quote",load)
    projector=fq.FoldedQuoteProjector()
    tasks=[asyncio.create_task(projector.project(1,notice(),fresh=True)) for _ in range(12)]
    try:
        await asyncio.wait_for(asyncio.sleep(0.01),1)
        assert len(calls)==1 and len(projector._pending)==1
        tasks[0].cancel()
        await asyncio.gather(tasks[0],return_exceptions=True)
        assert not tasks[1].done()
        release.set()
        assert await asyncio.gather(*tasks[1:])==[quote()]*11
        assert not projector._pending and not projector._cached
    finally:
        release.set()
        await asyncio.gather(*tasks,return_exceptions=True)

async def test_failed_projection_then_authority_recovers_during_venue_silence(monkeypatch):
    # Argon's pre-restoration one-shot counterexample: recovery authority itself
    # is initially unavailable, then becomes healthy without another control.
    attempted,restored=asyncio.Event(),asyncio.Event()
    calls=[]
    async def project(*args):
        calls.append(args)
        attempted.set()
        return quote() if restored.is_set() else None
    hub,chunks,task=await start(monkeypatch,project)
    try:
        hub.subscriptions["live:event:1"].offer(json.dumps(notice()))
        await until(attempted.is_set,task,"initial refused projection")
        await asyncio.sleep(0)
        restored.set()
        await until(lambda:bool(data(chunks,"folded_probability")),task,
                    "final quote within one second after authority restores",within=1.0)
        assert data(chunks,"folded_probability")[-1]["folded_quote"]==quote()
    finally:await stop(task)

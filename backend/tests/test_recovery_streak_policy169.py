"""Failure-streak isolation; authority injected, no production capacity claim."""
import asyncio
import json
import pytest
from app.utils import folded_live_quote as fq
from tests.test_normal_recovery_projection159 import notice, quote
pytestmark = pytest.mark.asyncio

@pytest.mark.parametrize('gap',[.3,1.0])
async def test_intermittent_healthy_success_preserves_failing_budget(monkeypatch,gap):
    p=fq.FoldedQuoteProjector();calls=[]
    async def load(eid,origin,rev):
        calls.append((eid,asyncio.get_running_loop().time()))
        return None if eid==1 else {**quote(),'event_id':eid,'blend_fold_revision':{str(eid):rev}}
    monkeypatch.setattr(fq,'load_folded_quote',load)
    start=asyncio.get_running_loop().time()
    async def healthy():
        rev=3
        await asyncio.sleep(.05)
        while True:
            assert await p.project(2,notice(2,rev)) is not None
            rev+=1
            await asyncio.sleep(gap)
    task=asyncio.create_task(healthy())
    try:
        while asyncio.get_running_loop().time()-start<4.1:
            assert await p.project(1,notice(1,len(calls)+3),fresh=True) is None
            await asyncio.sleep(.25)
    finally:
        task.cancel();await asyncio.gather(task,return_exceptions=True)
    times=[t-start for eid,t in calls if eid==1]
    print(json.dumps({'arm':'intermittent','gap':gap,'attempts':len(times),'times':times}))
    # These no-churn fixtures have asks every .25s for a fixed4.1s input window.
    # gap .3: first opening .35, next ask .5 spends it; no preopening probe.
    # gap1: asks .5/.75/1 may probe; success1.05 opens once, then spent sticks.
    # Scheduling drift only removes asks. Bounds count phase-specific maxima.
    limit = 10 if gap == .3 else 11
    print(json.dumps({'policy':'cap500_no_reader_churn','gap':gap,'attempts':len(times),'bound':limit}))
    assert len(times)<=limit
    assert not p._pending

async def test_healthy_success_without_dark_period_does_not_open_retry(monkeypatch):
    p=fq.FoldedQuoteProjector();now=asyncio.get_running_loop().time()
    p._last_success_at=now
    retry=fq._RecoveryRetry(4,now+2,now+.25);p._recovery_retry_after[1]=retry
    async def load(eid,origin,rev):return quote()
    monkeypatch.setattr(fq,'load_folded_quote',load)
    assert await p.project(2,notice(2)) is not None
    assert retry.after==now+2 and retry.opened_at is None

async def test_inflight_before_opening_does_not_spend_it(monkeypatch):
    p=fq.FoldedQuoteProjector();entered=asyncio.Event();release=asyncio.Event()
    async def load(eid,origin,rev):
        if eid==1:
            entered.set();await release.wait();return None
        return quote()
    monkeypatch.setattr(fq,'load_folded_quote',load)
    now=asyncio.get_running_loop().time();p._first_load_at=now-1
    p._recovery_retry_after[1]=fq._RecoveryRetry(2,now-1,now-1)
    task=asyncio.create_task(p.project(1,notice(),fresh=True))
    try:
        await entered.wait()
        assert await p.project(2,notice(2)) is not None
        assert p._recovery_retry_after[1].opened_at is not None
        release.set();await task
        assert not p._recovery_retry_after[1].spent
        assert await p.project(1,notice(),fresh=True) is None
        assert p._recovery_retry_after[1].spent
    finally:
        release.set();await asyncio.gather(task,return_exceptions=True)

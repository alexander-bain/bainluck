/* Real React hook, deterministic clocks, stubbed transport boundary. No browser/network. */
const test=require('node:test');
const assert=require('node:assert/strict');
const {harness}=require('./hook_harness.cjs');
function frame(wall=100750,seq=1,base=0) {return {event_id:1,p:.73,status:'live',provisional:true,
  display_observed_at:'2026-10-21T00:00:00Z',preview:{kind:'blend',epoch:7,seq,base_rev:base,
    ttl_ms:1000,original_expires_at_ms:wall+1000,recovery_emitted_at_ms:wall,
    clock_uncertainty_ms:250,lease_id:'chain-fixed-deadline'}};}
function envelope(remaining=600,f=frame()){return {control:{event_id:1,custody_id:'same-floor',removal_rev:{'1':0}},
  snapshot:{event_id:1,owner_epoch:7,committed_floor:0,seq_floor:f.preview.seq,frame:f,lease_remaining_ms:remaining}};}
async function start(r){await r.act(()=>r.controller.onStatusChange('retrying'));await r.tick(750);assert.equal(r.requests.length,1);assert.equal(r.requests[0].atMono,750);}
async function respond(r,packet=envelope()){await r.act(()=>r.requests[0].response.resolve({ok:true,json:async()=>packet}));}
function noErrors(r){assert.deepEqual(r.logs.filter(x=>x.event==='error').map(x=>String(x.error)),[]);}

for(const clientWall of [-1e12,0,100000,1e12])test(`actual hook GET admission ignores wall offset ${clientWall}`,async()=>{
  const r=await harness();try{
    await r.wall(clientWall);await start(r);await r.tick(100);await respond(r);
    noErrors(r);assert.equal(r.value.blendPreview?.expiresAt,1350);assert.equal(r.visible(),true);
    await r.tick(501);assert.equal(r.visible(),false);
  }finally{await r.close();}
});

test('fetch body parsing delay is charged to original dispatch, not headers or JSON completion',async()=>{
  const r=await harness();try{
    await start(r);let release;const body=new Promise(resolve=>release=resolve);
    await r.act(()=>r.requests[0].response.resolve({ok:true,json:()=>body}));
    await r.tick(500);await r.act(()=>release(envelope()));
    noErrors(r);assert.equal(r.value.blendPreview?.expiresAt,1350);
    assert.equal(r.value.blendPreviewNow,1250);
  }finally{await r.close();}
});

for(const jump of [-1e12,1e12])test(`wall jump ${jump} while GET is in flight neither rejects nor extends lease`,async()=>{
  const r=await harness();try{
    await start(r);await r.wall(jump);await r.tick(100);await respond(r);
    assert.equal(r.value.blendPreview?.expiresAt,1350);
    await r.wall(-jump);await r.tick(500);await r.rerender();
    assert.equal(r.value.blendPreviewNow,1350);assert.equal(r.visible(),false);
  }finally{await r.close();}
});

test('response exactly at request-start lease expiry cannot adopt',async()=>{
  const r=await harness();try{await start(r);await r.tick(300);await respond(r,envelope(300));assert.equal(r.value.blendPreview,null);}
  finally{await r.close();}
});
test('stalled timers cannot admit lease-expired response before probe lifetime ends',async()=>{
  const r=await harness();try{
    await start(r);await r.stall(300);await respond(r,envelope(300));
    assert.equal(r.value.blendPreview,null);assert.equal(r.monotonicNow(),1050);
  }finally{await r.close();}
});
test('stalled probe expiry timer still aborts and rejects response at original arm deadline',async()=>{
  const r=await harness();try{
    await start(r);await r.stall(750);await respond(r,envelope(60000));
    assert.equal(r.requests[0].opts.signal.aborted,true);assert.equal(r.value.blendPreview,null);
    assert.ok(r.logs.some(x=>x.event==='expired'));
  }finally{await r.close();}
});
test('unrelated render after stalled expiry timer cannot redisplay expired GET authority',async()=>{
  const r=await harness();try{
    await start(r);await r.tick(100);await respond(r);
    assert.equal(r.visible(),true);await r.stall(500);await r.rerender();
    assert.equal(r.value.blendPreviewNow,1350);assert.equal(r.visible(),false);
  }finally{await r.close();}
});

for(const reason of ['hidden','navigation','native-open','terminal','rollover'])test(`${reason} invalidates inflight result even when fetch ignores abort`,async()=>{
  const r=await harness();try{
    await start(r);
    if(reason==='hidden')await r.hide();
    else if(reason==='navigation')await r.navigate(2);
    else await r.act(()=>r.controller.onStatusChange(reason==='native-open'?'open':reason==='terminal'?'closed':'rollover'));
    assert.equal(r.requests[0].opts.signal.aborted,true);
    await respond(r);assert.equal(r.value.blendPreview,null);
  }finally{await r.close();}
});
test('unmount invalidates inflight result without touching retired hook',async()=>{
  const r=await harness();await start(r);const request=r.requests[0];await r.close();
  assert.equal(request.opts.signal.aborted,true);
  request.response.resolve({ok:true,json:async()=>envelope()});await Promise.resolve();await Promise.resolve();
});
test('newer revoke received while GET is inflight fences captured response',async()=>{
  const r=await harness();try{
    await start(r);await r.act(()=>r.controller.onPreview({event_id:1,p:null,provisional:true,
      preview:{kind:'revoke',epoch:7,seq:2,through_seq:1}}));
    await respond(r);assert.equal(r.value.blendPreview,null);
  }finally{await r.close();}
});
test('newer committed frame cancels and fences captured GET response',async()=>{
  const r=await harness();try{
    await start(r);await r.act(()=>r.controller.onFrame({event_id:1,p:.81,status:'live',rev:{'1':1}}));
    assert.equal(r.requests[0].opts.signal.aborted,true);await respond(r);assert.equal(r.value.blendPreview,null);
  }finally{await r.close();}
});
test('newer reconcile floor fences captured response without presenting a probability',async()=>{
  const r=await harness();try{
    await start(r);await r.act(()=>r.controller.onReconcile({eventId:1,custodyId:'floor1',floor:{'1':1}}));
    await respond(r);assert.equal(r.value.blendPreview,null);
  }finally{await r.close();}
});
test('actual committed page adoption cancels probe without restoring lifetime credit',async()=>{
  const r=await harness();try{
    await start(r);await r.adopt(1);assert.equal(r.requests[0].opts.signal.aborted,true);await respond(r);
    await r.act(()=>{r.controller.onStatusChange('open');r.controller.onStatusChange('retrying');});await r.tick(1000);
    assert.equal(r.requests.length,1);assert.equal(r.value.blendPreview,null);
  }finally{await r.close();}
});

test('pending duplicate OPEN does not extend 250 ms no-probability deadline',async()=>{
  const r=await harness();try{
    await r.act(()=>r.controller.onPreview(frame(100000)));
    await r.act(()=>r.controller.onPreviewReset('open'));assert.equal(r.value.previewRecoveryPending,'pending');assert.equal(r.value.blendPreview,null);
    await r.tick(200);await r.act(()=>r.controller.onPreviewReset('open'));await r.tick(51);
    assert.equal(r.value.previewRecoveryPending,'unavailable');assert.equal(r.value.blendPreview,null);
  }finally{await r.close();}
});
test('pending unavailable resolves only after actual newer page adoption, not receipt',async()=>{
  const r=await harness();try{
    await r.act(()=>r.controller.onPreview(frame(100000)));await r.act(()=>r.controller.onPreviewReset('open'));await r.tick(251);
    assert.equal(r.value.previewRecoveryPending,'unavailable');
    await r.act(()=>r.controller.onFrame({event_id:1,p:.81,status:'live',rev:{'1':1}}));assert.equal(r.value.previewRecoveryPending,'unavailable');
    await r.adopt(1);assert.equal(r.value.previewRecoveryPending,null);assert.equal(r.value.blendPreview,null);
  }finally{await r.close();}
});
test('late same-transport snapshot retains existing pending recovery semantics',async()=>{
  const r=await harness();try{
    await r.act(()=>r.controller.onPreview(frame(100000)));await r.act(()=>r.controller.onPreviewReset('open'));await r.tick(251);
    assert.equal(r.value.previewRecoveryPending,'unavailable');
    await r.act(()=>r.transport.emit('preview_state',envelope(600,frame(100000))));
    assert.equal(r.value.previewRecoveryPending,null);assert.equal(r.value.blendPreview?.expiresAt,750);assert.equal(r.visible(),true);
  }finally{await r.close();}
});

test('expired GET response fences later same-chain live packet after wall rollback',async()=>{
  const r=await harness();try{
    await start(r);await r.tick(300);await respond(r,envelope(300));assert.equal(r.value.blendPreview,null);
    await r.wall(100750);await r.act(()=>r.controller.onPreview(frame(100750,2)));
    assert.equal(r.value.blendPreview,null);
  }finally{await r.close();}
});
test('frame-null zero-budget GET fences late same-chain live under wall rollback',async()=>{
  const r=await harness();try{
    await start(r);await r.tick(300);const packet=envelope(0);
    packet.snapshot.frame=null;packet.snapshot.lease_id='chain-fixed-deadline';packet.snapshot.reason='expired_or_uncertain';
    await respond(r,packet);assert.equal(r.value.blendPreview,null);
    await r.wall(100750);await r.act(()=>r.controller.onPreview(frame(100750,2)));
    assert.equal(r.value.blendPreview,null);
  }finally{await r.close();}
});

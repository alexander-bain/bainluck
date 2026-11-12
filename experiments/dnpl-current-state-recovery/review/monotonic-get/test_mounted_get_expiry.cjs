const test=require('node:test');
const assert=require('node:assert/strict');
const {harness,deferred}=require('./mounted-harness.cjs');
function preview(seq=1,extra={}) {return {event_id:1,p:.73,status:'live',provisional:true,
 display_observed_at:'2026-10-21T00:00:00Z',preview:{kind:'blend',epoch:7,seq,base_rev:0,ttl_ms:1000,
 original_expires_at_ms:101750,recovery_emitted_at_ms:100750,clock_uncertainty_ms:250,lease_id:'chain-A',...extra}};}
function envelope(remaining=1000,frame=preview(1,{ttl_ms:remaining,original_expires_at_ms:100750+remaining}),extra={}) {return {control:{event_id:1,custody_id:'same-floor',removal_rev:{'1':0}},snapshot:{event_id:1,owner_epoch:7,seq_floor:frame?.preview.seq??1,committed_floor:0,frame,lease_remaining_ms:remaining,...extra}};}
async function request(r){await r.act(()=>r.controller.onStatusChange('retrying'));await r.tick(750);assert.equal(r.requests.length,1);}
async function respond(r,data){await r.act(()=>r.requests[0].response.resolve({ok:true,json:async()=>data}));}

for(const wallMs of [-2e12,100000,2e12]) test(`GET lease ignores initial wall clock ${wallMs}`,async()=>{
 const r=await harness({wallMs});try{await request(r);await r.tick(100);await respond(r,envelope());
 assert.equal(r.value.blendPreview?.p,.73);assert.equal(r.value.blendPreview.expiresAt,1750);
 assert.equal(r.value.blendPreviewNow,850);assert.equal(r.visible(),true);
 await r.tick(901);assert.equal(r.visible(),false);
 }finally{await r.close();}
});

test('wall jumps during request and after adoption do not change deadline',async()=>{
 const r=await harness();try{await request(r);await r.act(()=>r.clock.setSystemTime(2e12));await r.tick(100);await respond(r,envelope());
 assert.equal(r.value.blendPreview.expiresAt,1750);await r.act(()=>r.clock.setSystemTime(-2e12));await r.tick(900);
 await r.act(()=>r.controller.onFrame({event_id:1,p:.2,status:'live',rev:{'1':0}}));
 assert.equal(r.value.blendPreviewNow,1750);assert.equal(r.visible(),false);
 }finally{await r.close();}
});

test('slow JSON/body settlement consumes original request budget',async()=>{
 const r=await harness();try{await request(r);const body=deferred();await r.act(()=>r.requests[0].response.resolve({ok:true,json:()=>body.promise}));
 await r.tick(400);await r.act(()=>body.resolve(envelope(300)));assert.equal(r.visible(),false);assert.equal(r.value.blendPreview,null);
 }finally{await r.close();}
});

test('exact conservative lease boundary is rejected before adoption',async()=>{
 const r=await harness();try{await request(r);await r.tick(300);await respond(r,envelope(300));assert.equal(r.value.blendPreview,null);
 }finally{await r.close();}
});

test('same-chain higher live sequence cannot extend GET expiry after wall rollback',async()=>{
 const r=await harness();try{await request(r);await respond(r,envelope());await r.tick(600);await r.act(()=>r.clock.setSystemTime(100800));
 await r.act(()=>r.controller.onPreview(preview(2)));assert.equal(r.value.blendPreview?.seq,2);assert.equal(r.value.blendPreview.expiresAt,1750);
 await r.tick(401);assert.equal(r.visible(),false);await r.act(()=>r.controller.onPreview(preview(3)));assert.equal(r.value.blendPreview,null);
 }finally{await r.close();}
});

test('native-open equal-sequence envelope retains original monotonic cap',async()=>{
 const r=await harness();try{await request(r);await respond(r,envelope());await r.tick(300);
 await r.act(()=>{r.controller.onPreviewReset('open');r.controller.onStatusChange('open');});assert.equal(r.value.previewRecoveryPending,'pending');
 await r.act(()=>r.clock.setSystemTime(-2e12));await r.act(()=>r.transport.emit('preview_state',envelope(59000,preview())));
 assert.equal(r.value.blendPreview?.expiresAt,1750);assert.equal(r.value.previewRecoveryPending,null);await r.tick(701);assert.equal(r.visible(),false);
 }finally{await r.close();}
});

test('expiry survives same-base update and replay after held reset',async()=>{
 const r=await harness();try{await request(r);await respond(r,envelope(500));await r.tick(501);assert.equal(r.visible(),false);
 await r.act(()=>r.clock.setSystemTime(100800));await r.act(()=>r.controller.onFrame({event_id:1,p:.2,status:'live',rev:{'1':0}}));assert.equal(r.visible(),false);
 await r.act(()=>r.controller.onPreviewReset('open'));await r.act(()=>r.transport.emit('preview_state',envelope(59000,preview(1,{ttl_ms:500,original_expires_at_ms:101250}))));assert.equal(r.value.blendPreview,null);
 }finally{await r.close();}
});

test('revoke watermark survives native reset and earlier same-chain replay',async()=>{
 const r=await harness();try{await request(r);await respond(r,envelope());
 await r.act(()=>r.controller.onPreview({event_id:1,p:null,preview:{kind:'revoke',epoch:7,seq:2,through_seq:1}}));assert.equal(r.value.blendPreview,null);
 await r.act(()=>r.controller.onPreviewReset('open'));await r.act(()=>r.transport.emit('preview_state',envelope()));assert.equal(r.value.blendPreview,null);
 }finally{await r.close();}
});

test('new commit and snapshot floors beat a valid remaining lease',async()=>{
 const r=await harness();try{await request(r);await r.act(()=>r.controller.onReconcile({eventId:1,custodyId:'floor1',floor:{'1':1}}));
 await respond(r,envelope());assert.equal(r.value.blendPreview,null);
 }finally{await r.close();}
});

test('actual page adoption cancels request despite a valid server lease',async()=>{
 const r=await harness();try{await request(r);await r.adopt(1);assert.equal(r.requests[0].opts.signal.aborted,true);await respond(r,envelope());assert.equal(r.value.blendPreview,null);
 }finally{await r.close();}
});

test('hidden queued callback cannot adopt',async()=>{
 const r=await harness();try{await request(r);await r.hide();await respond(r,envelope());assert.equal(r.value.blendPreview,null);
 }finally{await r.close();}
});

test('wire-supplied local deadline cannot forge the private request binding',async()=>{
 const r=await harness({wallMs:2e12});try{await r.act(()=>r.controller.onPreview(preview(1,{request_deadline:999999,deadline:999999,recovered:true})));assert.equal(r.value.blendPreview,null);
 }finally{await r.close();}
});

test('expired GET must not leave a later same-chain live escape through wall fallback',async()=>{
 const r=await harness();try{await request(r);await r.tick(500);await respond(r,envelope(400));assert.equal(r.value.blendPreview,null);
 // Snapshot at server100750 had400 ms left; seq2 was emitted at100800 with350 ms left.
 // Both retain original chain deadline101150. Callback arrives at client mono1250,
 // beyond its request-bound deadline1150. A wall rollback must not revive it.
 await r.act(()=>r.clock.setSystemTime(100800));await r.act(()=>r.controller.onPreview(preview(2,{ttl_ms:350,original_expires_at_ms:101150,recovery_emitted_at_ms:100800})));assert.equal(r.value.blendPreview,null);
 }finally{await r.close();}
});

test('same-sequence GET tightens an already held live lease',async()=>{
 const r=await harness();try{
 const f=preview(1,{ttl_ms:3000,original_expires_at_ms:103000,recovery_emitted_at_ms:100000});
 await r.act(()=>r.controller.onPreview(f));assert.equal(r.value.blendPreview?.expiresAt,2750);
 await request(r);await r.tick(700);
 // Server snapshot at101400 leaves1600 ms of the fixed103000 deadline.
 // Conservative request anchor is750+1600=2350, earlier than held2750.
 await respond(r,envelope(1600,{...f,preview:{...f.preview,ttl_ms:1600,recovery_emitted_at_ms:101400}}));
 assert.equal(r.value.blendPreview?.expiresAt,2350);await r.tick(901);assert.equal(r.visible(),false);
 }finally{await r.close();}
});

test('expired empty snapshot retains same-chain non-renewal cap',async()=>{
 const r=await harness();try{await request(r);await r.tick(400);await respond(r,envelope(0,null,{lease_id:'chain-A',reason:'expired_or_uncertain'}));
 await r.act(()=>r.clock.setSystemTime(100800));await r.act(()=>r.controller.onPreview(preview(2)));assert.equal(r.value.blendPreview,null);
 }finally{await r.close();}
});

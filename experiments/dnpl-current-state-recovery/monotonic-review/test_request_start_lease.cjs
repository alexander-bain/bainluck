/* Independent deterministic contract checks; candidate sources bundled in memory only. */
const test = require('node:test');
const assert = require('node:assert/strict');
const m = require('./load_candidate.cjs')();
const EID=1, EPOCH=7, OBS='2026-10-21T00:00:00Z';
const committed={id:EID,status:'live',hero_probability_source:'blend',blend_fold_revision:{'1':10}};
function frame(seq=5, changes={}) { return {event_id:EID,p:.73,status:'live',provisional:true,
  display_observed_at:OBS,preview:{kind:'blend',epoch:EPOCH,seq,base_rev:10,ttl_ms:600,
    original_expires_at_ms:11000,recovery_emitted_at_ms:10400,clock_uncertainty_ms:250,
    lease_id:'stable-producer-chain-deadline',...changes}}; }
function envelope(remaining=600, f=frame(), snapshot={}) {return {
  control:{event_id:EID,custody_id:'same-floor',removal_rev:{'1':10}},
  snapshot:{event_id:EID,owner_epoch:EPOCH,committed_floor:10,seq_floor:f?.preview.seq??5,
    frame:f,lease_id:f?.preview.lease_id,lease_remaining_ms:remaining,...snapshot}};}
function accept(packet, now=10500, start=10400, reader=m.EMPTY_BLEND_PREVIEW_READER) {
  return m.acceptCurrentPreview(reader,packet,EID,now,{requestStart:start});
}
function wall(value, fn){const original=Date.now;Date.now=()=>value;try{return fn();}finally{Date.now=original;}}

for(const clientWall of [-1e15,-60000,0,10400,1e15]) {
  test(`request-start admission is independent of wall offset ${clientWall}`,()=>wall(clientWall,()=>{
    const reader=accept(envelope());
    assert.equal(reader.held?.expiresAt,11000);
    assert.equal(m.displayedPreview(reader.held,committed,10999.999),.73);
    assert.equal(m.displayedPreview(reader.held,committed,11000),null);
    assert.equal(reader.held.observedAt,OBS);
  }));
}

test('transit consumes budget, never granting receipt plus remaining',()=>{
  const reader=accept(envelope(600),10990,10400);
  assert.equal(reader.held?.expiresAt,11000);
  assert.ok(reader.held.expiresAt<10990+600);
  assert.equal(m.displayedPreview(reader.held,committed,11000),null);
});
for(const arrival of [11000,11000.001,11500,1e8]) {
  test(`response at or beyond anchored deadline ${arrival} fails closed`,()=>{
    assert.equal(accept(envelope(),arrival).held,null);
  });
}

test('independent end-to-end delay matrix never crosses true original server deadline',()=>{
  let checked=0;
  for(const outbound of [0,1,30,250])for(const serverWork of [0,1,50])for(const inbound of [0,1,30,250,700]) {
    const clientStart=12345.5,serverLife=900;
    const remaining=serverLife-outbound-serverWork;
    const arrival=clientStart+outbound+serverWork+inbound;
    const actualOriginalExpiry=clientStart+serverLife;
    const result=accept(envelope(remaining),arrival,clientStart);
    if(arrival>=clientStart+remaining)assert.equal(result.held,null);
    else {
      assert.ok(result.held,'valid early arrivals must be admitted');
      assert.equal(result.held.expiresAt,clientStart+remaining);
      assert.ok(result.held.expiresAt<=actualOriginalExpiry);
    }
    checked++;
  }
  assert.equal(checked,60);
});

test('wall jumps after admission cannot affect display lease or observation time',()=>{
  const reader=accept(envelope());
  for(const wallNow of [-1e15,1e15,0,10500])wall(wallNow,()=>{
    assert.equal(m.displayedPreview(reader.held,committed,10999),.73);
    assert.equal(m.displayedPreview(reader.held,committed,11000),null);
    assert.equal(m.displayedProbabilityObservedAt(committed,reader.held,10999,'committed-clock'),OBS);
    assert.equal(m.displayedProbabilityObservedAt(committed,reader.held,11000,'committed-clock'),'committed-clock');
  });
});

test('duplicate equal sequence with inflated budget preserves original deadline',()=>{
  const first=accept(envelope());
  const duplicate=accept(envelope(60000),10600,10500,first);
  assert.deepEqual(duplicate.held,first.held);
  assert.equal(duplicate.held.expiresAt,11000);
});
test('reopened same sequence cannot refresh an expired lease even with a later request',()=>{
  const first=accept(envelope());
  const reset={...first,held:null};
  const later=accept(envelope(60000),11001,11000,reset);
  assert.equal(later.held,null);
});
test('reopened same sequence before expiry keeps the earliest lease cap',()=>{
  const first=accept(envelope());
  const later=accept(envelope(60000),10900,10800,{...first,held:null});
  assert.equal(later.held?.expiresAt,11000);
});
test('later same-chain sequence cannot acquire a fresh wall or relative lease',()=>{
  const first=accept(envelope());
  const later=wall(-1e15,()=>m.readerAfter(first,frame(6,{ttl_ms:60000}),EID,10900));
  assert.equal(later.held?.seq,6);
  assert.equal(later.held?.expiresAt,11000);
  assert.equal(m.displayedPreview(later.held,committed,11000),null);
});
test('later same-chain sequence after expiry remains invisible',()=>{
  const first=accept(envelope());
  const later=m.readerAfter(first,frame(6,{ttl_ms:60000}),EID,11000);
  assert.equal(later.held,null);
});

test('newer revoke defeats captured older successful GET',()=>{
  let reader=accept(envelope());
  reader=m.readerAfter(reader,{event_id:EID,p:null,provisional:true,
    preview:{kind:'revoke',epoch:EPOCH,seq:6,through_seq:5}},EID,10501);
  reader=accept(envelope(60000),10502,10500,reader);
  assert.equal(reader.held,null);
  assert.equal(reader.singletonSequence.seq,6);
});
test('newer live sequence defeats older successful GET without clearing newer value',()=>{
  let reader=accept(envelope(600,frame(6)));
  reader=accept(envelope(60000,frame(5)),10510,10500,reader);
  assert.equal(reader.held.seq,6);
  assert.equal(reader.held.expiresAt,11000);
});
test('newer committed floor defeats captured old-base response and subsequent old-base data',()=>{
  let reader=accept(envelope());
  reader=m.readerAfterCommitFloor(reader,{'1':11});
  reader=accept(envelope(60000),10510,10500,reader);
  assert.equal(reader.held,null);
  assert.equal(reader.floors['1'],11);
  assert.equal(m.readerAfter(reader,frame(6),EID,10520).held,null);
});
test('replacement epoch defeats captured old owner response',()=>{
  const fresh=accept(envelope(600,frame(1,{epoch:8,lease_id:'new-owner'}),{owner_epoch:8}));
  const next=accept(envelope(60000),10510,10500,fresh);
  assert.equal(next.epoch,8);assert.equal(next.held.epoch,8);
});
test('foreign event response cannot change current reader',()=>{
  const first=accept(envelope());
  const packet=envelope(60000);packet.snapshot.event_id=2;
  assert.equal(accept(packet,10510,10500,first),first);
});

for(const bad of [undefined,null,0,-1,0.5,60001,Infinity,NaN,'600',{},true]) {
  test(`invalid remaining lease ${String(bad)} cannot grant GET authority`,()=>{
    assert.equal(accept(envelope(600,frame(),{lease_remaining_ms:bad})).held,null);
  });
}
for(const [start,now] of [[NaN,10500],[Infinity,10500],[-1,10500],[10501,10500],[10400,NaN],[10400,Infinity]]) {
  test(`invalid local timing start=${start}, now=${now} fails closed`,()=>{
    assert.equal(accept(envelope(),now,start).held,null);
  });
}
for(const leaseId of [undefined,null,'',1,{},'x'.repeat(161)]) {
  test(`invalid lease identity ${typeof leaseId}:${String(leaseId).slice(0,20)} fails closed`,()=>{
    assert.equal(accept(envelope(600,frame(5,{lease_id:leaseId}))).held,null);
  });
}
test('wire-shaped client deadline cannot replace private local request binding',()=>{
  const packet=envelope(0);Object.assign(packet.snapshot.frame.preview,
    {requestStart:10400,deadline:99999999,request_deadline:99999999,monotonic_deadline:99999999});
  assert.equal(accept(packet).held,null);
});
test('private binding never survives serialization onto unrelated wire objects',()=>{
  const bound=frame();assert.ok(m.bindRequestLease(bound,10400,10500,600));
  assert.equal(m.localRequestLease(bound).deadline,11000);
  assert.equal(m.localRequestLease(JSON.parse(JSON.stringify(bound))),undefined);
});
test('maximum allowed budget is bounded by request start',()=>{
  const result=accept(envelope(60000),10500,10400);
  assert.equal(result.held?.expiresAt,70400);
  assert.equal(m.displayedPreview(result.held,committed,70400),null);
});

test('expired GET retains cap so wall rollback cannot revive higher sequence from same chain',()=>{
  const expired=accept(envelope(600),11000,10400);
  assert.equal(expired.held,null);
  const late=wall(10400,()=>m.readerAfter(expired,frame(6,{ttl_ms:60000}),EID,11010));
  assert.equal(late.held,null);
});
test('frame-null zero-budget snapshot caps higher sequence late live despite wall rollback',()=>{
  const packet=envelope(0,null,{lease_id:'stable-producer-chain-deadline',seq_floor:5,reason:'expired_or_uncertain'});
  const expired=accept(packet,11000,10400);
  assert.equal(expired.held,null);
  const late=wall(10400,()=>m.readerAfter(expired,frame(6,{ttl_ms:60000}),EID,11010));
  assert.equal(late.held,null);
});
test('frame-null positive budget already consumed in transit still fences later same-chain live',()=>{
  const packet=envelope(600,null,{lease_id:'stable-producer-chain-deadline',seq_floor:5,reason:'expired_or_uncertain'});
  const expired=accept(packet,11000,10400);
  const late=wall(10400,()=>m.readerAfter(expired,frame(6,{ttl_ms:60000}),EID,11010));
  assert.equal(late.held,null);
});
test('zero budget remains valid non-renewal metadata but never visible authority',()=>{
  assert.equal(m.validatedBudgetDeadline(10400,11000,0),10400);
  assert.equal(m.requestStartDeadline(10400,11000,0),null);
  const f=frame();assert.ok(m.bindRequestLease(f,10400,11000,0));
  assert.equal(m.localRequestLease(f).deadline,10400);
});

test('expired empty older-sequence snapshot clears already-held newer same-chain preview',()=>{
  const first=accept(envelope(60000,frame(6)),10500,10400);
  assert.ok(first.held);
  const packet=envelope(0,null,{lease_id:'stable-producer-chain-deadline',seq_floor:5,reason:'expired_or_uncertain'});
  const next=accept(packet,10510,10400,first);
  assert.equal(next.held,null);
  assert.equal(next.singletonSequence.seq,6,'known later sequence authority must not roll back');
});
test('empty older-sequence snapshot shortens held same-chain lease without renewing it',()=>{
  const first=accept(envelope(60000,frame(6)),10500,10400);
  const packet=envelope(300,null,{lease_id:'stable-producer-chain-deadline',seq_floor:5});
  const next=accept(packet,10600,10500,first);
  assert.equal(next.held?.seq,6);assert.equal(next.held?.expiresAt,10800);
  assert.equal(m.displayedPreview(next.held,committed,10800),null);
});
test('expired empty older-sequence snapshot cannot poison unrelated held chain',()=>{
  const first=accept(envelope(60000,frame(6,{lease_id:'unrelated-chain'})),10500,10400);
  const packet=envelope(0,null,{lease_id:'stable-producer-chain-deadline',seq_floor:5,reason:'expired_or_uncertain'});
  const next=accept(packet,10510,10400,first);
  assert.equal(next.held?.seq,6);assert.equal(next.held?.expiresAt,70400);
});

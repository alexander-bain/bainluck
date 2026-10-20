import assert from 'node:assert/strict';import fs from 'node:fs';import path from 'node:path';import os from 'node:os';
import {Broker,Client,frame,deliver} from './broker.mjs';
import {Owner as OldOwner,Client as OldClient,frame as oldFrame} from '../baseline/recovery-candidate.mjs';
// An explicit OUT and its ancestors must be trusted. Never chmod existing paths.
// Otherwise use a fresh, private directory rather than a predictable shared path.
const out=process.env.OUT||fs.mkdtempSync(path.join(os.tmpdir(),'fenced-tests-'));fs.mkdirSync(out,{recursive:true,mode:0o700});
const blocked={persist:()=>new Promise(()=>{}),reconcile:async()=>null};
const summary={scope:'Deterministic model scheduling, not browser/paint/network measurements',staleOwner:{scenarios:100,baselineStaleDisplays:0,brokerStaleDisplays:0},reconnect:{scenarios:100,baselineStaleDisplays:0,brokerStaleDisplays:0},takeoverPlacement:[],randomized:{seeds:100,stepsPerSeed:300,operations:0,accepted:0,rejected:0,olderEpochViewsWithinLease:0,maxLeaseChallengeAgeMsWhileOlderEpochVisible:0}};
for(let n=1;n<=100;n++){
 const token={stream:`old-${n}`,epoch:'old',generation:1},messages=[],owner=new OldOwner({store:blocked,token,publish:m=>messages.push(m)}),c=new OldClient();c.connect({...token},owner.snapshot());const newer={...token,epoch:'new',generation:2};owner.offer(oldFrame(1,n/101));c.accept(messages[0]);if(c.current?.epoch!==newer.epoch)summary.staleOwner.baselineStaleDisplays++;
 const b=new Broker(),t=b.claim('old'),d=new Client({now:()=>0});b.open(d.start());deliver(b,d);b.claim('new');b.offer(t,frame(1));deliver(b,d);if(d.current?.epoch===t.epoch)summary.staleOwner.brokerStaleDisplays++;
 const r=new OldClient(),read={...token};r.connect(read,owner.snapshot());if(r.current?.epoch!==newer.epoch)summary.reconnect.baselineStaleDisplays++;
 const q=new Broker(),qt=q.claim('old');q.offer(qt,frame(1));const readUnused=q.token();q.claim('new');const qc=new Client({now:()=>0});q.open({...qc.start(),authority:readUnused});deliver(q,qc);if(qc.current?.epoch===qt.epoch)summary.reconnect.brokerStaleDisplays++;
}
for(const placement of ['before-open','between-open-send','between-send-accept','after-accept']){const b=new Broker(),t=b.claim('a'),c=new Client({now:()=>0});b.offer(t,frame(1));let next;if(placement==='before-open')next=b.claim('b');b.open(c.start());if(placement==='between-open-send')next=b.claim('b');const m=b.take(c.session);if(placement==='between-send-accept')next=b.claim('b');c.accept(m);if(placement==='after-accept')next=b.claim('b');const oldView=c.current?.epoch===t.epoch;assert.equal(oldView,['between-send-accept','after-accept'].includes(placement));summary.takeoverPlacement.push({placement,oldViewBeforeDeliveredFence:oldView,sentEpoch:m.epoch,newEpoch:next.epoch});deliver(b,c);assert.equal(c.current,null);}
const random=seed=>()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/2**32;};
for(let seed=1;seed<=summary.randomized.seeds;seed++){
 const rng=random(seed);let time=0;const b=new Broker({maxHistory:10000,maxMailbox:128,maxPending:10000}),c=new Client({now:()=>time,maxPoints:10000});let t=b.claim('initial'),seq=0;const old=[],wire=[];b.open(c.start());deliver(b,c);
 for(let step=0;step<summary.randomized.stepsPerSeed;step++){const op=Math.floor(rng()*10);let result;
  if(op===0){result=b.offer(t,frame(++seq,rng()));}
  else if(op===1){old.push(t);t=b.claim(`owner-${step}`);seq=0;}
  else if(op===2){const oldToken=old[Math.floor(rng()*old.length)];if(oldToken){result=b.offer(oldToken,frame(1));assert.ok(result.error);}}
  else if(op===3){const m=b.take(c.session);if(m)wire.push(m);}
  else if(op===4&&wire.length){const i=Math.floor(rng()*wire.length),m=wire.splice(i,1)[0];result=c.accept(m);if(rng()<.25)c.accept(m);}
  else if(op===5){b.close(c.session);b.open(c.start());}
  else if(op===6){time+=Math.floor(rng()*80);c.tick();}
  else if(op===7){const n=c.challenge();if(n)b.renew(c.session,n);}
  else if(op===8&&b.history.length){const j=b.history[Math.floor(rng()*b.history.length)];result=b.ack(j,{hash:j.hash});}
  else if(op===9){deliver(b,c);}
  c.tick();if(c.current){assert.ok(time<c.deadline);assert.equal(c.current.boot,c.boot);assert.equal(c.current.epoch,c.epoch);assert.equal(c.current.ownerId,c.ownerId);assert.equal(c.current.stream,b.stream);assert.ok(b.history.some(j=>j.boot===c.current.boot&&j.epoch===c.current.epoch&&j.seq===c.current.seq&&j.hash===c.current.hash));if(c.current.epoch<b.epoch){summary.randomized.olderEpochViewsWithinLease++;summary.randomized.maxLeaseChallengeAgeMsWhileOlderEpochVisible=Math.max(summary.randomized.maxLeaseChallengeAgeMsWhileOlderEpochVisible,c.maxLeaseMs-(c.deadline-time));}}
  summary.randomized.operations++;if(result?.accepted||result?.displayed)summary.randomized.accepted++;if(result?.error)summary.randomized.rejected++;
 }
 const groups=new Map();for(const p of c.points){const k=p.boot+'/'+p.epoch;const prev=groups.get(k)||0;assert.ok(p.seq>prev,`seed ${seed}: point regressed/duplicated`);groups.set(k,p.seq);}
}
assert.equal(summary.staleOwner.baselineStaleDisplays,100);assert.equal(summary.staleOwner.brokerStaleDisplays,0);assert.equal(summary.reconnect.baselineStaleDisplays,100);assert.equal(summary.reconnect.brokerStaleDisplays,0);
fs.writeFileSync(path.join(out,'schedule-matrix.json'),JSON.stringify(summary,null,2)+'\n',{flag:'wx',mode:0o600});console.log(JSON.stringify(summary,null,2));console.error(`Schedule report: ${path.join(out,'schedule-matrix.json')}`);

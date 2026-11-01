import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {candidateUrl} from './candidate-path.mjs';
const {Broker,Client,frame}=await import(candidateUrl('src/broker.mjs'));
function permutations(xs){if(!xs.length)return [[]];return xs.flatMap((x,i)=>permutations(xs.filter((_,j)=>j!==i)).map(p=>[x,...p]));}
const receipts=[];

test('all 192 four-operation / drain-placement schedules reach newest authority without stale queued send',()=>{
 for(const order of permutations(['open','oldOffer','claimNew','newOffer']).filter(p=>p.indexOf('claimNew')<p.indexOf('newOffer'))){
  for(let drains=0;drains<16;drains++){
   const b=new Broker(),c=new Client({now:()=>0}),old=b.claim('old');let newer;const events=[];
   const drain=()=>{if(!c.session)return;let m;while(m=b.take(c.session)){
    assert.equal(m.epoch,b.epoch,'broker emitted stale epoch at send boundary');
    const result=c.accept(m);events.push({kind:'wire',wireKind:m.kind,epoch:m.epoch,result,current:c.current?.p??null});
   }};
   for(let i=0;i<order.length;i++){
    const op=order[i];let result;
    if(op==='open')result=b.open(c.start());
    if(op==='oldOffer')result=b.offer(old,frame(1,.2));
    if(op==='claimNew')result=newer=b.claim('new');
    if(op==='newOffer')result=b.offer(newer,frame(1,.8));
    events.push({kind:op,result});if(drains&(1<<i))drain();
   }
   drain();assert.equal(c.current?.p,.8,JSON.stringify({order,drains,events}));assert.equal(c.epoch,2);
   receipts.push({order,drainMask:drains,current:c.current.p,epoch:c.epoch,wireFrames:events.filter(e=>e.kind==='wire').length});
  }
 }
 assert.equal(receipts.length,192);
});
process.on('exit',()=>fs.writeFileSync(new URL('./INTERLEAVING-SWEEP.json',import.meta.url),JSON.stringify({scope:'Deterministic in-process client state, fixed time zero, not network/browser paint',scheduleCount:receipts.length,schedules:receipts},null,2)+'\n'));

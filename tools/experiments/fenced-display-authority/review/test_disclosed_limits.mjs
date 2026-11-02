import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {candidateUrl} from './candidate-path.mjs';
const {Broker,Client,frame,deliver}=await import(candidateUrl('src/broker.mjs'));
const limits=[];

test('limitation: reachable broker renewals do not expire a dead source owner sample',()=>{
 let now=0;const b=new Broker(),token=b.claim('source-owner'),c=new Client({now:()=>now});b.open(c.start());deliver(b,c);b.offer(token,frame(1,.61));deliver(b,c);
 // Source owner supplies no message after t=0, but authority broker remains alive.
 for(let i=1;i<=20;i++){now=i*200;const nonce=c.challenge();b.renew(c.session,nonce);deliver(b,c);assert.equal(c.current.seq,1);assert.equal(c.current.p,.61);}
 assert.equal(c.deadline,4250);assert.equal(c.current.seq,1);assert.equal(c.points.length,1);
 limits.push({name:'broker-lease-not-source-liveness',sourceLastMessageAt:0,observedAt:now,leaseDeadline:c.deadline,currentSequence:c.current.seq,limitationReproduced:true});
});

test('limitation: expiry is a scheduled operation, not passive erasure at deadline',()=>{
 let now=0;const b=new Broker(),token=b.claim('source-owner'),c=new Client({now:()=>now});b.open(c.start());deliver(b,c);b.offer(token,frame(1,.61));deliver(b,c);
 now=10000;assert.equal(c.current.p,.61,'no tick/accept call has run');const before=structuredClone(c.current);c.tick();assert.equal(c.current,null);
 limits.push({name:'scheduler-needed-for-expiry',deadline:250,clockAdvancedTo:10000,currentBeforeTick:before.p,currentAfterTick:c.current,limitationReproduced:true,note:'Virtual-clock model, not an actual suspended browser timing measurement.'});
});

process.on('exit',()=>fs.writeFileSync(new URL('./DISCLOSED-LIMITS.json',import.meta.url),JSON.stringify({limits},null,2)+'\n'));

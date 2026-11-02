import test from 'node:test';
import assert from 'node:assert/strict';
import {candidateUrl} from './candidate-path.mjs';
const {Broker,Client,frame,deliver}=await import(candidateUrl('src/broker.mjs'));

test('ownerless startup refuses before registration, then same handshake succeeds after claim',()=>{
 const b=new Broker(),c=new Client({now:()=>0}),hello=c.start(),opened=b.open(hello);
 assert.equal(opened.error,'no-owner');assert.equal(b.subs.has(hello.session),false);
 assert.ok(b.offer(b.token(),frame(1,.1)).error);assert.equal(b.history.length,0);
 const token=b.claim('first');assert.equal(b.open(hello).connected,true);
 b.offer(token,frame(1,.62));deliver(b,c);assert.equal(c.current?.p,.62);assert.equal(c.status,'active');
});

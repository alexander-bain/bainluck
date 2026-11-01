import test from 'node:test';
import assert from 'node:assert/strict';
import {candidateUrl} from './candidate-path.mjs';
const {Broker,Client,deliver,frame}=await import(candidateUrl('src/broker.mjs'));

// The property required here is no nonce reuse. Returning null, throwing, or
// generating a different private nonce are acceptable candidate implementations.
function attempt(c,nonce){try{return c.challenge(nonce);}catch{return null;}}

test('an outstanding challenge cannot be reused to move its request timestamp',()=>{
 let time=0;const b=new Broker(),t=b.claim('one'),c=new Client({now:()=>time});b.open(c.start());deliver(b,c);b.offer(t,frame(1));deliver(b,c);
 time=100;const nonce=c.challenge('reused');b.renew(c.session,nonce);const old=b.take(c.session);
 time=300;const attempted=attempt(c,nonce);
 assert.notEqual(attempted,nonce,'reusing pending nonce must not overwrite request time');
 c.accept(old);assert.ok(c.deadline<=350,'old response cannot receive request time of later attempt');
});

test('a consumed challenge cannot be reused to make a replay renew after broker loss',()=>{
 let time=0;const b=new Broker(),t=b.claim('one'),c=new Client({now:()=>time});b.open(c.start());deliver(b,c);b.offer(t,frame(1));deliver(b,c);
 time=100;const nonce=c.challenge('reused');b.renew(c.session,nonce);const response=b.take(c.session);c.accept(response);assert.equal(c.deadline,350);
 // Nothing calls the broker after this line. An old response must not renew it.
 time=300;const attempted=attempt(c,nonce);
 assert.notEqual(attempted,nonce,'consumed nonce cannot be reissued in the same session');
 c.accept(response);assert.ok(c.deadline<=350,'replayed response must not extend currentness');
});

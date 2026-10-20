import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {candidateUrl} from './candidate-path.mjs';
const {Broker,Client,frame,deliver}=await import(candidateUrl('src/broker.mjs'));
const traces=[];
function fixture(){let time=0;const b=new Broker({leaseMs:250});const token=b.claim('owner-one');const c=new Client({now:()=>time,leaseMs:250});b.open(c.start());deliver(b,c);return {b,c,token,setTime:n=>time=n};}
const observe=(name,x,extra={})=>traces.push({name,current:structuredClone(x.c.current),status:x.c.status,epoch:x.c.epoch,revision:x.c.revision,deadline:x.c.deadline,...extra});

test('takeover during initial snapshot delivery preserves handshake lease',()=>{
 const b=new Broker(),c=new Client({now:()=>0});b.claim('one');b.open(c.start());const token=b.claim('two');
 const m=b.take(c.session);const result=c.accept(m);assert.equal(result.snapshot,true,JSON.stringify({result,m}));
 b.offer(token,frame(1,.6));deliver(b,c);assert.equal(c.current.p,.6);assert.equal(c.epoch,2);
});

test('takeover while renewal queued preserves bounded renewal challenge',()=>{
 const x=fixture();x.setTime(200);x.b.renew(x.c.session,x.c.challenge());x.b.claim('two');deliver(x.b,x.c);
 assert.equal(x.c.deadline,450);x.setTime(251);x.c.tick();assert.equal(x.c.status,'active');
});

test('bounded limitation: sent old publication can display before delayed handover fence',()=>{
 const x=fixture();x.b.offer(x.token,frame(1,.71));const sent=x.b.take(x.c.session);
 x.setTime(10);x.b.claim('two');const result=x.c.accept(sent);
 assert.equal(result.displayed,true);assert.equal(x.c.current.epoch,1);
 observe('old-sent-frame-after-takeover',x,{takeoverAt:10,limitReproduced:true});
 x.setTime(249);assert.equal(x.c.tick().p,.71);x.setTime(250);assert.equal(x.c.tick(),null);
 observe('expiry-at-original-request-deadline',x);
});

test('observed handover fences delayed old publication and acknowledgement',()=>{
 const x=fixture();x.b.offer(x.token,frame(1,.51));const old=x.b.take(x.c.session);
 const newer=x.b.claim('two');deliver(x.b,x.c);x.b.offer(newer,frame(1,.81));deliver(x.b,x.c);
 assert.equal(x.c.current.p,.81);const revision=x.c.revision,points=x.c.points.length;
 assert.equal(x.c.accept(old).error,'fenced-or-expired');
 assert.equal(x.c.accept({...old,kind:'persistence',state:'durable',receipt:{hash:old.hash},revision:100000}).error,'fenced-or-expired');
 assert.equal(x.c.current.p,.81);assert.equal(x.c.revision,revision);assert.equal(x.c.points.length,points);
});

test('delayed lease response expires from request time, never response time',()=>{
 const x=fixture();x.setTime(100);x.b.renew(x.c.session,x.c.challenge());const sent=x.b.take(x.c.session);
 x.setTime(400);assert.equal(x.c.accept(sent).snapshot,true);assert.equal(x.c.deadline,350);assert.equal(x.c.current,null);assert.equal(x.c.status,'unavailable');
 observe('delayed-renewal-is-already-expired',x);
});

test('delayed renewal after observed new epoch cannot extend lease',()=>{
 const x=fixture();x.setTime(100);x.b.renew(x.c.session,x.c.challenge());const old=x.b.take(x.c.session);
 x.b.claim('two');deliver(x.b,x.c);const deadline=x.c.deadline;
 assert.equal(x.c.accept(old).error,'old-snapshot');assert.equal(x.c.deadline,deadline);
});

test('rejected high revision payload/receipt and ignored ACK do not poison freshness',()=>{
 const x=fixture();x.b.offer(x.token,frame(1,.4));deliver(x.b,x.c);x.b.offer(x.token,frame(2,.5));const valid=x.b.take(x.c.session);
 const revision=x.c.revision;
 assert.equal(x.c.accept({...valid,revision:99999,payload:frame(2,.9)}).error,'invalid-publication');assert.equal(x.c.revision,revision);
 assert.equal(x.c.accept({...valid,kind:'persistence',state:'durable',revision:99999,receipt:{hash:valid.hash}}).ignored,true);assert.equal(x.c.revision,revision);
 assert.equal(x.c.accept(valid).displayed,true);assert.equal(x.c.current.p,.5);
});

test('repeated reconnect rejects old channel snapshot and publication',()=>{
 const x=fixture();x.b.offer(x.token,frame(1,.4));const old=x.b.take(x.c.session);const oldSession=x.c.session;
 x.b.open(x.c.start());const snap=x.b.take(x.c.session);assert.equal(x.c.accept(snap).snapshot,true);
 assert.equal(x.c.accept(old).error,'session');x.b.close(oldSession);assert.equal(x.c.current.p,.4);
});

test('terminal followed by old valid traffic stays terminal and empty',()=>{
 const x=fixture();x.b.offer(x.token,frame(1,.4));const old=x.b.take(x.c.session);
 assert.equal(x.b.terminal(x.token).terminal,true);deliver(x.b,x.c);assert.equal(x.c.status,'terminal');
 assert.equal(x.c.accept(old).error,'fenced-or-expired');assert.equal(x.c.current,null);
 assert.equal(x.b.claim('two').error,'terminal');assert.equal(x.b.offer(x.token,frame(2,.7)).error,'fenced-or-terminal');
});

test('publication is available while persistence has not even been invoked',async()=>{
 let called=0;const b=new Broker({persist:()=>{called++;return new Promise(()=>{});}}),token=b.claim('one'),c=new Client();b.open(c.start());deliver(b,c);
 assert.equal(b.offer(token,frame(1,.3)).accepted,true);deliver(b,c);
 assert.equal(c.current.p,.3);assert.equal(c.current.state,'pending');assert.equal(called,0);
 await Promise.resolve();assert.equal(called,1);
});

process.on('exit',()=>fs.writeFileSync(new URL('./CANDIDATE-STATE-TRACES.json',import.meta.url),JSON.stringify({scope:'Client-model state; no browser or database; explicit expected-limit case',traces},null,2)+'\n'));

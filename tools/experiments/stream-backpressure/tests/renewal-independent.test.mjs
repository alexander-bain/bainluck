import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
const source=process.env.EVENT_SOURCE || fileURLToPath(new URL('../src/',import.meta.url));
const {WireClient}=await import(pathToFileURL(path.join(source,'wire-client.mjs')));
const {Broker}=await import(pathToFileURL(path.join(source,'broker.mjs')));
const {frame}=await import(pathToFileURL(path.join(source,'protocol.mjs')));
const fixture=frame(1,.7); // synthetic protocol contract only, not source193 data
const step=async()=>{for(let i=0;i<8;i++)await Promise.resolve();};
function setup(){
 let now=0;
 const w=new WireClient({stream:'event-review',lab:'mock-only',leaseMs:1000});
 w.client.now=()=>now;w.closed=false;w.generation=1;
 const b=new Broker({stream:'event-review',leaseMs:1000}),token=b.claim('owner');
 b.offer(token,fixture);
 const hello=w.client.start();b.open(hello);w.client.accept(b.take(hello.session));
 const requests=[];
 w.api=(action,extra,options)=>new Promise((resolve,reject)=>requests.push({action,...extra,options,resolve,reject}));
 return {w,b,token,requests,time:t=>{now=t;}};
}
function message(x,index=x.requests.length-1){
 const r=x.requests[index];x.b.renew(r.session,r.challenge);return x.b.take(r.session);
}
function receive(x,m){return x.w.receiveEnvelope({message:m,transport:{mock:true}});}
async function cleanup(x){
 x.w.renewal?.catch(()=>{});
 await x.w.close();
 for(const r of x.requests)r.reject(Error('mock cleanup'));
 await step();
 assert.equal(x.w.renewControls.size,0);
 assert.equal(x.w.renewProof,null);
}
test('historical short proof settles before observer; consumer cannot treat its old deadline as fresh',async()=>{
 const x=setup(),p=x.w.renew();await step();const m=message(x);m.lease.ttlMs=40;
 x.time(39);let saw=false;
 x.w.onObserve=row=>{if(row.kind==='authority-envelope'){saw=true;assert.equal(x.w.renewal,null);assert.equal(x.requests[0].options.signal.aborted,true);x.time(41);assert.equal(x.w.tick(),null);}};
 receive(x,m);const proof=await p;
 assert.ok(saw);assert.equal(proof.confirmedAtMs,39);assert.equal(proof.deadlineMs,40);
 assert.equal(x.w.client.deadline,40);assert.equal(x.w.client.current,null);assert.equal(x.w.client.status,'unavailable');
 assert.match(proof.meaning,/consult Client.tick/);await cleanup(x);
});
test('explicit pre-parse receipt boundary is retained without changing proof time',async()=>{
 const x=setup(),p=x.w.renew();await step();x.time(50);
 const beforeParse=performance.now()-25;
 x.w.receiveEnvelope({message:message(x),transport:{mock:true}},beforeParse);
 const row=x.w.trace.find(r=>r.kind==='authority-envelope');
 assert.equal(row.receivedMs,beforeParse);assert.ok(row.validationMs>=25);
 assert.equal((await p).confirmedAtMs,50);await cleanup(x);
});
test('observer reentrant renewal B survives both A completion logging and late A HTTP success',async()=>{
 const x=setup(),a=x.w.renew();await step();let b;
 x.w.onObserve=row=>{if(row.kind==='authority-envelope'&&!b){b=x.w.renew();}};
 receive(x,message(x));await a;await step();
 assert.equal(x.w.renewal,b);assert.equal(x.requests.length,2);
 x.requests[0].resolve({queued:true});await step();assert.equal(x.w.renewal,b);
 receive(x,message(x,1));await b;await cleanup(x);
});
test('HTTP failure before a valid SSE proof does not delete the pending proof',async()=>{
 const x=setup(),p=x.w.renew();await step();x.requests[0].reject(Error('mock request timeout'));await step();
 assert.equal(x.w.renewControls.size,0);assert.equal(x.w.renewal,p);assert.ok(x.w.renewProof);
 x.time(800);receive(x,message(x));const proof=await p;
 assert.equal(proof.controlResponsePending,false);assert.equal(proof.confirmedAtMs,800);
 assert.equal(x.w.controlOutcomes[0].ok,false);await cleanup(x);
});
test('delivered accepted snapshot at the exact own deadline is not a valid proof',async()=>{
 const x=setup(),p=x.w.renew();p.catch(()=>{});await step();x.time(1000);
 assert.equal(receive(x,message(x)).snapshot,true);assert.equal(x.w.renewal,p);
 assert.equal(x.w.client.current,null);await cleanup(x);await assert.rejects(p,/session-changed/);
});
test('malformed and wrong-session messages do not settle or consume pending proof',async()=>{
 const x=setup(),p=x.w.renew();await step();const m=message(x);
 const bad=structuredClone(m);bad.latest.payload.p=.123;
 assert.equal(receive(x,bad).error,'invalid-snapshot');assert.equal(x.w.renewal,p);
 assert.ok(x.w.client.challenges.has(m.lease.nonce));
 const oldSession=structuredClone(m);oldSession.session='old';
 assert.equal(receive(x,oldSession).error,'session');assert.equal(x.w.renewal,p);
 receive(x,m);await p;await cleanup(x);
});
test('accepted old short proof cannot borrow an unrelated fresh lease',async()=>{
 const x=setup(),p=x.w.renew();p.catch(()=>{});await step();const m=message(x);m.lease.ttlMs=40;
 x.time(50);receive(x,m);assert.equal(x.w.renewal,p);
 const other=x.w.client.challenge('separate-valid-challenge');x.b.renew(x.w.client.session,other);receive(x,x.b.take(x.w.client.session));
 assert.equal(x.w.client.deadline,1050);assert.equal(x.w.renewal,p);
 assert.equal(receive(x,m).error,'lease');assert.equal(x.w.renewal,p);
 await cleanup(x);await assert.rejects(p,/session-changed/);
});
test('session replacement retires proof even after its HTTP control settled',async()=>{
 const x=setup(),a=x.w.renew();a.catch(()=>{});await step();
 const old=message(x);x.requests[0].resolve({queued:true});await step();
 assert.equal(x.w.renewControls.size,0);assert.equal(x.w.renewal,a);
 x.w.retireRenewControls('session-replaced');x.w.generation++;x.time(100);
 const hello=x.w.client.start();x.b.open(hello);receive(x,x.b.take(hello.session));
 await assert.rejects(a,/session-changed/);
 const next=x.w.renew();await step();assert.equal(receive(x,old).error,'session');assert.equal(x.w.renewal,next);
 receive(x,message(x,1));await next;await cleanup(x);
});
test('a terminal accepted snapshot confirms handling, never active numeric authority',async()=>{
 const x=setup(),p=x.w.renew();await step();x.b.terminal(x.token);const m=message(x);
 assert.equal(m.status,'terminal');receive(x,m);const result=await p;
 assert.equal(result.confirmedBy,'accepted-sse-snapshot');assert.equal(x.w.client.current,null);
 assert.equal(x.w.client.status,'terminal');await cleanup(x);
});
test('real API timeout plus failure timer rejects without accepted proof, using mocked fetch only',async()=>{
 const w=new WireClient({stream:'timeout',lab:'mock-only',leaseMs:30,controlTimeoutMs:5});
 w.closed=false;w.generation=1;w.client.start();
 const original=globalThis.fetch;let aborted=false;
 globalThis.fetch=(url,options)=>new Promise((resolve,reject)=>{
  options.signal.addEventListener('abort',()=>{aborted=true;reject(options.signal.reason);},{once:true});
 });
 try {
  const p=w.renew();await assert.rejects(p,/no-valid-lease-before-deadline/);
  await step();assert.ok(aborted);assert.equal(w.renewControls.size,0);assert.equal(w.renewal,null);
  assert.equal(w.renewProof,null);assert.equal(w.client.current,null);
 } finally {globalThis.fetch=original;await w.close();}
});
test('actual SSE parsing path confirms proof before observer without waiting for the mocked POST',async()=>{
 let now=0,streamController,request,postAborted=false;
 const w=new WireClient({base:'http://mock.invalid',stream:'parser-review',lab:'no-network',leaseMs:1000});
 w.client.now=()=>now;
 const b=new Broker({stream:'parser-review',leaseMs:1000}),token=b.claim('owner');
 b.offer(token,fixture);
 const encoder=new TextEncoder(),original=globalThis.fetch;
 const send=m=>streamController.enqueue(encoder.encode(`data: ${JSON.stringify({message:m,transport:{mock:true}})}\n\n`));
 globalThis.fetch=(url,options)=>{
  if(String(url).includes('/stream?')){
   const parsed=new URL(url),hello=Object.fromEntries(parsed.searchParams);b.open(hello);
   const body=new ReadableStream({start(controller){streamController=controller;send(b.take(hello.session));}});
   options.signal.addEventListener('abort',()=>streamController.error(new DOMException('Mock abort','AbortError')),{once:true});
   return Promise.resolve({ok:true,body});
  }
  request=JSON.parse(options.body);
  return new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>{
   postAborted=true;reject(new DOMException('Mock abort','AbortError'));
  },{once:true}));
 };
 try {
  await w.open();now=10;const renewal=w.renew();await step();
  assert.equal(request.action,'renew');b.renew(request.session,request.challenge);
  now=1009;
  w.onObserve=row=>{if(row.kind==='authority-envelope'&&row.message.lease?.nonce===request.challenge){
   assert.equal(w.renewal,null);assert.ok(postAborted);now=1011;assert.equal(w.tick(),null);
  }};
  send(b.take(request.session));const confirmed=await renewal;
  assert.equal(confirmed.confirmedAtMs,1009);assert.equal(confirmed.deadlineMs,1010);
  assert.equal(w.tick(),null);assert.equal(w.client.points.length,1);
  await step();assert.equal(w.renewControls.size,0);
 } finally {await w.close();globalThis.fetch=original;}
});

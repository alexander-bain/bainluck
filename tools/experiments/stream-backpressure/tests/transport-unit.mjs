import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {Broker,frame} from '../src/broker.mjs';
import {WireClient,until} from '../src/wire-client.mjs';
import {createStreamServer} from '../src/stream-server.mjs';
await test('SSE consumer handles fragmented UTF-8 transport chunks, duplicate frames, and real EOF invalidation with mocked fetch (no socket)',async()=>{
 const original=globalThis.fetch,b=new Broker({leaseMs:1500}),token=b.claim('unit-owner');let controller;
 globalThis.fetch=async(url,options)=>{
  const parsed=new URL(url),hello={session:parsed.searchParams.get('session'),challenge:parsed.searchParams.get('challenge')};b.open(hello);b.offer(token,frame(1,.4));const messages=[];let message;while((message=b.take(hello.session)))messages.push(message);messages.push(messages.at(-1));
  const bytes=new TextEncoder().encode(': unicode comment α☃🧪\n\n'+messages.map(message=>`event: authority\ndata: ${JSON.stringify({message,transport:{readyToWriteMs:0}})}\n\n`).join(''));
  const body=new ReadableStream({start(c){controller=c;for(let i=0;i<bytes.length;i+=3)c.enqueue(bytes.slice(i,i+3));options.signal.addEventListener('abort',()=>{try{c.error(new DOMException('Aborted','AbortError'));}catch{}});}});
  return new Response(body,{status:200,headers:{'Content-Type':'text/event-stream'}});
 };
 const wire=new WireClient({base:'http://127.0.0.1:1',lab:'mock',leaseMs:1500});
 try{await wire.open();await until(()=>wire.client.current?.seq===1,'fragmented publication');assert.equal(wire.client.current.p,.4);assert.equal(wire.client.points.length,1);assert.ok(wire.trace.some(r=>r.result?.ignored));controller.close();await until(()=>wire.closed,'mock EOF');assert.equal(wire.client.current,null);assert.equal(wire.client.points.length,1);}
 finally{await wire.close();globalThis.fetch=original;}
});
await test('shutdown is idempotent and reports an actual shared completion (no listener started)',async()=>{
 const out=fs.mkdtempSync(path.join(os.tmpdir(),'sse-stop-unit-'));const app=createStreamServer({out});
 try{const first=app.stop('unit-no-listener'),second=app.stop('duplicate-stop');assert.equal(first,second);const result=await first;assert.equal(result.remainingSockets,0);assert.equal(result.remainingLabs,0);assert.equal(result.cleanupTimedOut,false);assert.equal(result.kind,'clean-shutdown');assert.equal(result.reason,'unit-no-listener');assert.equal(fs.readdirSync(out).filter(f=>f.startsWith('shutdown-')).length,1);}
 finally{fs.rmSync(out,{recursive:true,force:true});}
});
await test('expired initial handshake fails and closes its stream without restarting TTL (mock fetch; no socket)',async()=>{
 const original=globalThis.fetch;let now=0,aborted=false;
 globalThis.fetch=async(url,options)=>{
  const u=new URL(url),b=new Broker({leaseMs:1500});b.claim('late-owner');b.open({session:u.searchParams.get('session'),challenge:u.searchParams.get('challenge')});const message=b.take(u.searchParams.get('session'));now=1501;
  const body=new ReadableStream({start(c){c.enqueue(new TextEncoder().encode(`data: ${JSON.stringify({message})}\n\n`));options.signal.addEventListener('abort',()=>{aborted=true;try{c.error(new DOMException('Aborted','AbortError'));}catch{}});}});
  return new Response(body,{status:200});
 };
 const wire=new WireClient({base:'http://127.0.0.1:1',lab:'late-handshake',leaseMs:1500});wire.client.now=()=>now;
 try{await assert.rejects(wire.open(),/initial-handshake-arrived-expired/);assert.equal(aborted,true);assert.equal(wire.closed,true);assert.equal(wire.client.current,null);assert.equal(wire.client.session,null);assert.equal(wire.client.points.length,0);assert.ok(wire.trace.some(r=>r.result?.snapshot&&r.deadlineMs===1500));}
 finally{await wire.close();globalThis.fetch=original;}
});
await test('fresh terminal and fatal snapshots remain successful informational handshakes (mock fetch; no socket)',async()=>{
 const original=globalThis.fetch;
 try{for(const status of ['terminal','fatal']){
  globalThis.fetch=async(url,options)=>{const u=new URL(url),b=new Broker({leaseMs:1500}),token=b.claim();if(status==='terminal')b.terminal(token);else b.fatal('fixture');b.open({session:u.searchParams.get('session'),challenge:u.searchParams.get('challenge')});const message=b.take(u.searchParams.get('session'));return new Response(new ReadableStream({start(c){c.enqueue(new TextEncoder().encode(`data: ${JSON.stringify({message})}\n\n`));options.signal.addEventListener('abort',()=>{try{c.error(new DOMException('Aborted','AbortError'));}catch{}});}}),{status:200});};
  const wire=new WireClient({base:'http://127.0.0.1:1',lab:status,leaseMs:1500});wire.client.now=()=>0;try{await wire.open();assert.equal(wire.client.status,status);assert.equal(wire.client.current,null);}finally{await wire.close();}
 }}finally{globalThis.fetch=original;}
});

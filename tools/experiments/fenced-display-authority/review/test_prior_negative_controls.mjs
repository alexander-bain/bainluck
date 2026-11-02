// Independent read-only baseline reproduction. No PostgreSQL or browser started.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {candidateUrl} from './candidate-path.mjs';
const {Owner,Client,frame}=await import(candidateUrl('baseline/recovery-candidate.mjs'));
const traces=[];
const token={stream:'independent-review',epoch:'old-epoch',generation:1};
const newer={...token,epoch:'new-epoch',generation:2};
const record=(event,c,extra={})=>({event,current:structuredClone(c.current),connected:c.connected,...extra});
function fixture(){let authority={...token},release;const blocked=new Promise(r=>release=r),messages=[];
 const store={async persist(job){await blocked;if(authority.epoch!==job.epoch)throw Error('stale-owner');return {hash:job.hash};},async reconcile(){return null;}};
 const owner=new Owner({token:{...token},store,publish:m=>messages.push(m)});
 return {owner,messages,release,takeover:()=>authority={...newer},authority:()=>structuredClone(authority)};
}

test('negative control: superseded connected owner displays before database fence arrives',async()=>{
 const x=fixture(),c=new Client(),events=[];c.connect(x.authority(),x.owner.snapshot());
 x.owner.publish=m=>{x.messages.push(m);c.accept(m);events.push(record(m.kind,c));};
 x.takeover();events.push(record('takeover',c,{authority:x.authority()}));
 x.owner.offer(frame(1,.73));events.push(record('offer-return',c));
 assert.equal(c.current.epoch,'old-epoch');assert.equal(c.current.p,.73);
 x.release();await x.owner.drain();assert.equal(c.current,null);
 traces.push({name:'superseded-owner',limitationReproduced:true,events});
});

test('negative control: queued old publication arrives after takeover before invalidation',async()=>{
 const x=fixture(),c=new Client(),events=[];c.connect(x.authority(),x.owner.snapshot());
 x.owner.offer(frame(1,.61));const queued=x.messages.find(m=>m.kind==='publication');
 x.takeover();events.push(record('takeover',c,{authority:x.authority()}));
 c.accept(queued);events.push(record('deliver-old-queued-publication',c));
 assert.equal(c.current.epoch,'old-epoch');assert.equal(c.current.p,.61);
 x.release();await x.owner.drain();c.accept(x.messages.find(m=>m.kind==='fenced'));
 assert.equal(c.current,null);events.push(record('deliver-fence',c));
 traces.push({name:'late-buffered-publication',limitationReproduced:true,events});
});

test('negative control: authority read followed by takeover still authorizes old snapshot',async()=>{
 const x=fixture(),c=new Client(),events=[];x.owner.offer(frame(1,.43));
 const read=x.authority();x.takeover();events.push(record('takeover-after-read',c,{authority:x.authority(),previousRead:read}));
 const result=c.connect(read,x.owner.snapshot());events.push(record('old-snapshot-connect',c));
 assert.equal(result.connected,true);assert.equal(c.current.epoch,'old-epoch');
 c.disconnect();assert.equal(c.connect(x.authority(),x.owner.snapshot()).error,'unavailable-or-stale');
 x.release();await x.owner.drain();traces.push({name:'reconnect-check-use',limitationReproduced:true,events});
});

test('negative control: dropped invalidation retains old current indefinitely without expiry',async()=>{
 const x=fixture(),c=new Client(),events=[];x.owner.offer(frame(1,.58));
 c.connect(x.authority(),x.owner.snapshot());assert.equal(c.current.p,.58);
 x.takeover();x.release();await x.owner.drain();assert.equal(x.owner.closed,true);
 // Broker/DB knows owner is fenced, but transport deliberately loses all messages.
 events.push(record('owner-fenced-no-client-delivery',c,{ownerClosed:x.owner.closed}));
 assert.equal(c.current.epoch,'old-epoch');assert.equal(c.connected,true);
 assert.equal(typeof c.expire,'undefined');
 traces.push({name:'lost-invalidation-no-expiry',limitationReproduced:true,events,note:'No real-time duration claim: client has no time-based expiry operation.'});
});

process.on('exit',()=>fs.writeFileSync(new URL('./PRIOR-NEGATIVE-CONTROLS.json',import.meta.url),JSON.stringify({scope:'Baseline Owner/Client with controllable in-memory authority; actual client-state calls, no SQL/browser/paint',checks:traces},null,2)+'\n'));

// Recorded synthetic failure replay only. No transport, timer, or performance rerun.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import {fileURLToPath,pathToFileURL} from 'node:url';
import path from 'node:path';
const source=process.env.FENCE_SOURCE||fileURLToPath(new URL('../src/',import.meta.url));
const fixturePath=process.env.FENCE_FIXTURE||new URL('./fixtures/held-fence-failures.json',import.meta.url);
const fixture=JSON.parse(fs.readFileSync(fixturePath,'utf8'));
const {WireClient}=await import(pathToFileURL(path.join(source,'wire-client.mjs')));
const {Client}=await import(pathToFileURL(path.join(source,'client.mjs')));
const digest=crypto.createHash('sha256').update(fs.readFileSync(path.join(source,'client.mjs'))).digest('hex');
assert.equal(digest,fixture.frozenClientSha256,'Receiver remains byte-identical to failed-run/predecessor Client');
assert.equal(fixture.fullReceiptSha256,'5f19850ce2a8e718db49275b1383ed4e323e225a703b01d5deba24a2db0141ac');
for(const captured of fixture.cases)test(`${captured.name}: recorded expired arrivals remain unavailable`,async()=>{
 assert.equal(captured.passed,false,'Original failed compatibility outcome retained');
 const trace=captured.clientTrace,hello=trace.find(r=>r.kind==='connect-request').hello;
 const envelopes=trace.filter(r=>r.kind==='authority-envelope'),first=envelopes[0];
 const requested=first.deadlineMs-first.message.lease.ttlMs;
 assert.equal(trace.filter(r=>r.kind==='control-request'&&r.action==='renew').length,0);
 assert.equal(trace.filter(r=>r.kind==='renewal-complete').length,0);
 assert.ok(trace.filter(r=>r.kind==='control-request').some(req=>{
  const res=trace.find(r=>r.n>req.n&&r.kind==='control-response'&&r.action===req.action);
  return res&&req.clientMonoMs<first.deadlineMs&&res.clientMonoMs>=first.deadlineMs;
 }),'A recorded non-renew control wait spans the original lease expiry');
 let time=requested;
 const wire=new WireClient({leaseMs:1500}),frozenClient=new Client({leaseMs:1500,now:()=>time});
 wire.client.now=()=>time;wire.closed=false;wire.generation=1;
 for(const client of [wire.client,frozenClient]){
  client.start();client.session=hello.session;
  client.challenges=new Map([[hello.challenge,requested]]);
  client.usedChallenges=new Set([hello.challenge]);
 }
 for(const row of envelopes){
  time=row.acceptedMs;
  // The changed receive/confirm hook DOES run. No pending proof can settle.
  const actual=wire.receiveEnvelope({message:structuredClone(row.message),transport:row.transport});
  const unchanged=frozenClient.accept(structuredClone(row.message));
  assert.deepEqual(actual,row.result);assert.deepEqual(unchanged,row.result);
  assert.equal(wire.client.deadline,row.deadlineMs);assert.equal(frozenClient.deadline,row.deadlineMs);
  assert.equal(wire.renewProof,null);assert.equal(wire.renewControls.size,0);
  assert.equal(wire.client.current,null);assert.equal(frozenClient.current,null);
 }
 assert.equal(wire.client.points.length,0);assert.equal(frozenClient.points.length,0);
 assert.deepEqual(captured.points,[]);
 await wire.close();
});

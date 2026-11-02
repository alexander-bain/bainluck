import fs from 'node:fs';
import assert from 'node:assert/strict';
const file=process.argv[2]||'results/wire-receipt.json';
const report=JSON.parse(fs.readFileSync(file,'utf8'));let count=0;
const check=(ok,label)=>{assert.ok(ok,label);count++;};
for(const result of report.results){
 check(result.passed,`${result.name}: scenario must have passed`);
 const events=result.server.events,opened=new Map(),closed=new Map();
 for(let i=0;i<events.length;i++){
  const e=events[i];check(e.n===i+1,`${result.name}: server receipt order is contiguous`);
  if(e.kind==='stream-open')opened.set(e.connection,e);
  if(e.kind==='stream-close')closed.set(e.connection,e);
  if(e.kind==='wire-write'){
   check(opened.has(e.connection)&&opened.get(e.connection).n<e.n,`${result.name}: write must follow connection open`);
   check(!closed.has(e.connection),`${result.name}: no write accepted after socket close receipt`);
   check(e.session===opened.get(e.connection).session,`${result.name}: response stays bound to original session`);
   check(e.transport.producerReadyMs===null||e.transport.readyToWriteMs>=0,`${result.name}: server timing is nonnegative`);
  }
 }
 const envelopes=result.clientTrace.filter(e=>e.kind==='authority-envelope');
 if(result.name==='ordered-delivery'){
  check(JSON.stringify(result.points.map(p=>p.seq))===JSON.stringify(Array.from({length:30},(_,i)=>i+1)),'Ordered exact sequence 1–30');
  const duplicate=envelopes.filter(e=>e.message.kind==='publication'&&e.result.ignored);check(duplicate.length===1,'One explicit duplicate must be ignored');
  check(envelopes.some(e=>e.message.kind==='persistence'&&e.result.ack),'Persistence ACK processed separately');
 }
 if(['drop-reconnect','delayed-old-connection','disconnect-handover'].includes(result.name.replace(/-immediate$/,''))){
  const opens=events.filter(e=>e.kind==='stream-open');check(opens.length===2,`${result.name}: two real connections`);
  check(opens[0].session!==opens[1].session,`${result.name}: fresh session`);
  const close=events.find(e=>e.kind==='stream-close'&&e.connection===opens[0].connection);
  check(close&&close.n<opens[1].n,`${result.name}: old connection close recorded before replacement open`);
  if(result.name.endsWith('-immediate'))check(result.metrics.configuredRetryDelayMs===0,`${result.name}: no explicit timer wait injected`);
  check(result.metrics.authorityUnavailableMs>=result.metrics.explicitRetrySleepMs,`${result.name}: reported outage includes configured wait`);
 }
 if(result.name==='held-old-before-fence'){
  const handover=events.find(e=>e.kind==='claim'&&e.token.epoch===2);
  const staleWrite=events.find(e=>e.kind==='wire-write'&&e.message.kind==='publication'&&e.message.epoch===1);
  check(staleWrite.n>handover.n,'Residual requires old bytes actually written after server handover');
  check(envelopes.some(e=>e.message.epoch===1&&e.result.displayed),'Residual requires old message actually accepted');
 }
 if(result.name==='held-old-after-fence')check(envelopes.some(e=>e.message.epoch===1&&e.result.error==='fenced-or-expired'),'Old epoch rejected after fence');
 if(result.name==='expired-renew-latest'){check(JSON.stringify(result.points.map(p=>p.seq))==='[1,3]','Expired seq 2 not fabricated');check(result.clientTrace.filter(e=>e.kind==='control-request'&&e.action==='renew').length===1,'Concurrent renewals share one control request');}
 if(result.name==='skipped-intermediate')check(JSON.stringify(result.points.map(p=>p.seq))==='[1,3]','Intermediate omission must remain explicitly absent');
 if(result.name==='omitted-final'){
  const omitted=events.find(e=>e.kind==='intentionally-omitted');
  const renewed=events.find(e=>e.kind==='control'&&e.action==='renew');
  check(omitted.n<renewed.n,'Final publication omitted before renewal');
  check(envelopes.some(e=>e.message.kind==='snapshot'&&e.message.latest?.seq===2),'Final value recovered by latest snapshot, not fabricated publication');
 }
 if(result.name.startsWith('atomic-')){
  const open=events.find(e=>e.kind==='stream-open');const offer=events.find(e=>e.kind==='offer'&&e.seq===1);
  check(result.name==='atomic-before'?offer.n<open.n:offer.n>open.n,`${result.name}: requested subscribe ordering was actually exercised`);
 }
}
console.log(JSON.stringify({file,cases:report.results.length,assertions:count,passed:true,scope:'Offline server/client receipt ordering and duplicate/skip/final-update audit; not a new network run'},null,2));

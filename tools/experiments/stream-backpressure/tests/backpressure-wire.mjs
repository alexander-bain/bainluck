import http from 'node:http';
import fs from 'node:fs';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {createStreamServer} from '../src/stream-server.mjs';
import {createStreamServer as baselineServer} from '../baseline/stream-server.mjs';
import {frame} from '../src/broker.mjs';
import {Client} from '../src/client.mjs';
import {WireClient,until,sleep} from '../src/wire-client.mjs';
const sourceHashes=Object.fromEntries(['src/bounded-sse-writer.mjs','src/stream-server.mjs','tests/backpressure-wire.mjs','src/client.mjs','src/protocol.mjs','src/broker.mjs'].map(p=>[p,crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex')]));
const report={sourceHashes,kind:'bounded-loopback-backpressure',startedAt:new Date().toISOString(),scope:'Synthetic loopback only; paused real Node HTTP/TCP reader; no browser or Internet partition claim',caps:{maxSseClients:3,applicationAndNodeBufferedBytesPerClient:2*1024*1024,maxBurstMs:30000,maxFrames:5000},cases:[]};
fs.mkdirSync('results',{recursive:true});
async function api(base,path,data){const body=JSON.stringify(data);return await new Promise((resolve,reject)=>{const req=http.request(`${base}${path}`,{method:'POST',agent:false,headers:{'Content-Type':'application/json','Content-Length':Buffer.byteLength(body)},timeout:5000},res=>{let text='';res.on('data',s=>text+=s);res.on('end',()=>{try{const r=JSON.parse(text);if(res.statusCode!==200||r.error)reject(Error(r.error||res.statusCode));else resolve(r);}catch(e){reject(e);}});});req.on('timeout',()=>req.destroy(Error('control-timeout')));req.on('error',reject);req.end(body);});}
async function rawPaused(base,lab){const client=new Client({leaseMs:30000}),{session,challenge}=client.start();return await new Promise((resolve,reject)=>{const req=http.get(`${base}/stream?lab=${lab}&session=${session}&challenge=${challenge}`,{agent:false},res=>{res.on('error',()=>{});res.pause();let buffer='';const errors=[];res.on('data',chunk=>{buffer+=chunk.toString('utf8');if(Buffer.byteLength(buffer)>2*1024*1024){errors.push('client-parser-cap');res.destroy();return;}let boundary;while((boundary=buffer.indexOf('\n\n'))>=0){const event=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);const data=event.split('\n').filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trimStart()).join('\n');if(data)try{client.accept(JSON.parse(data).message);}catch(e){errors.push(e.message);}}});resolve({req,res,session,client,errors,close(){res.destroy();req.destroy();}});});req.on('error',reject);});}

async function runBaseline(){
 const app=baselineServer({out:'results/baseline-wire',leaseMs:30000});let raw;
 try{const addr=await app.listen(0),base=`http://127.0.0.1:${addr.port}`,created=await api(base,'/api/create',{}),lab=app.labs.get(created.id);raw=await rawPaused(base,lab.id);const conn=[...lab.connections.values()][0],start=performance.now();let peak=0,count=0,firstFalse=null,blocked=false,writesWithoutDrain=0;const flow=[];const originalWrite=conn.res.write.bind(conn.res);conn.res.on('drain',()=>{flow.push({kind:'drain',at:performance.now()});blocked=false;});conn.res.write=(...args)=>{if(blocked)writesWithoutDrain++;const ok=originalWrite(...args);peak=Math.max(peak,conn.res.writableLength);flow.push({kind:'write',ok,bufferedBytes:conn.res.writableLength,at:performance.now()});if(!ok)blocked=true;return ok;};
  // Queue 120 frames before each real control request pumps them. This is under the broker's 128-frame bound.
  for(let batch=0;batch<40;batch++){
   for(let i=0;i<120;i++){assert.ok(lab.broker.offer(lab.token,frame(++count)).accepted);}
   await api(base,'/api/action',{lab:lab.id,action:'resume-pump'});
   peak=Math.max(peak,conn.res.writableLength);
   firstFalse??=lab.events.find(e=>e.kind==='wire-write'&&e.backpressure);
   assert.ok(peak<2*1024*1024,'baseline safety cap exceeded');assert.ok(performance.now()-start<30000,'baseline burst cap');
   if(firstFalse&&lab.events.filter(e=>e.kind==='wire-write'&&e.n>firstFalse.n).length>=120)break;
  }
  assert.ok(firstFalse,'real write(false) must be exercised, not inferred');
  const writesAfterFalse=lab.events.filter(e=>e.kind==='wire-write'&&e.n>firstFalse.n).length;
  assert.ok(writesAfterFalse>0);assert.ok(writesWithoutDrain>0);report.cases.push({name:'baseline-real-paused-reader',passed:true,expectedSafetyFailure:true,conclusion:'Baseline keeps enqueueing after actual write(false)',publications:count,writesAfterFirstFalse:writesAfterFalse,writesWithoutInterveningDrain:writesWithoutDrain,peakObservedNodeBytes:peak,flow,burstMs:performance.now()-start,firstFalse,events:lab.events});
 }finally{raw?.close();const shutdown=await app.stop('baseline-wire-finished');assert.equal(shutdown.remainingSockets,0);report.baselineShutdown={remainingSockets:shutdown.remainingSockets,remainingLabs:shutdown.remainingLabs,cleanupTimedOut:shutdown.cleanupTimedOut};}
}
async function runCandidate(){
 const app=createStreamServer({out:'results/candidate-wire',leaseMs:30000,transportPaddingBytes:8192,writerOptions:{stallMs:400,maxQueuedBytes:128*1024,maxQueuedFrames:64,maxFrameBytes:16*1024,maxBufferedBytes:256*1024}});let raw,normal,recovered;
 try{const addr=await app.listen(0),base=`http://127.0.0.1:${addr.port}`,created=await api(base,'/api/create',{}),lab=app.labs.get(created.id);raw=await rawPaused(base,lab.id);normal=new WireClient({base,lab:lab.id,leaseMs:30000});await normal.open();const slow=[...lab.connections.values()].find(c=>c.session===raw.session),fast=[...lab.connections.values()].find(c=>c.session===normal.client.session);
  const start=performance.now();let seq=0,healthMaxMs=0;
  // Small, yielded batches keep the reading client's socket drained; only the paused reader accumulates pressure.
  for(let batch=0;batch<1000&&!slow.closed;batch++){
   for(let i=0;i<4&&!slow.closed;i++){assert.ok(lab.broker.offer(lab.token,frame(++seq,(seq%100)/100)).accepted);app.pump(lab);}
   await sleep(1);
   assert.ok(slow.writer.stats.peakBufferedBytes<=256*1024);assert.ok(fast.writer.stats.peakBufferedBytes<=256*1024);assert.ok(performance.now()-start<30000,'candidate burst cap');
   assert.ok(!fast.closed,'normal reader must remain connected during slow-reader stress');
   if(batch%25===0){const t=performance.now();await api(base,'/api/action',{lab:lab.id,action:'resume-pump'});healthMaxMs=Math.max(healthMaxMs,performance.now()-t);}
  }
  assert.ok(slow.writer.stats.writeFalse>0,'real paused client must reach response.write(false)');
  assert.equal(slow.closed,true,'bounded writer must disconnect slow reader');assert.ok(['queue-limit','drain-timeout'].includes(slow.writer.stats.closeReason));
  await until(()=>normal.client.current?.seq===seq,'normal reader latest');assert.equal(normal.client.points.length,seq);assert.equal(new Set(normal.client.points.map(p=>p.id)).size,seq);assert.equal(normal.client.current.p,(seq%100)/100);assert.equal(normal.client.current.state,'pending','display is not gated by storage ACK');
  const burstMs=performance.now()-start,slowStats={...slow.writer.stats},fastStats={...fast.writer.stats};
  raw.close();await until(()=>slow.res.destroyed,'slow socket destroyed');
  // Explicit fresh-session reconnect restores latest state, not the unseen intermediate history.
  recovered=new WireClient({base,lab:lab.id,leaseMs:30000});const recoveryStart=performance.now();await recovered.open();await until(()=>recovered.client.current?.seq===seq,'recovery latest snapshot');const recoveryMs=performance.now()-recoveryStart;
  assert.equal(recovered.client.current.p,(seq%100)/100);assert.equal(recovered.client.points.length,1);assert.equal(recovered.client.points[0].seq,seq);assert.equal(new Set(recovered.client.points.map(p=>p.id)).size,1);await recovered.renew();assert.equal(recovered.client.points.length,1,'renewal snapshot must not duplicate latest point');
  const postCloseWritesBefore=lab.events.filter(e=>e.kind==='wire-write'&&e.connection===slow.id).length;
  slow.res.emit('drain');await sleep(450);const postCloseWritesAfter=lab.events.filter(e=>e.kind==='wire-write'&&e.connection===slow.id).length;assert.equal(postCloseWritesAfter,postCloseWritesBefore);assert.equal(slow.writer.stats.callbacksAfterClose,0);assert.equal(slow.writer.timer,null);assert.equal(slow.writer.queue.length,0);assert.equal(slow.writer.queuedBytes,0);
  report.cases.push({name:'candidate-real-paused-reader-and-responsive-reader',passed:true,conclusion:'Bounded slow-client disconnect while normal reader receives every synthetic point without duplicates; latest-only snapshot recovery',publications:seq,burstMs,maxControlResponseMs:healthMaxMs,recoveryMs,observedRecoveryPoints:recovered.client.points.map(p=>p.seq),normalPointCount:normal.client.points.length,normalPendingWithoutStorageAck:normal.client.current.state==='pending',slowStats,fastStats,postCloseWrites:postCloseWritesAfter-postCloseWritesBefore,events:lab.events,normalTrace:normal.trace,recoveryTrace:recovered.trace});
  await recovered.close();recovered=null;await normal.close();normal=null;await until(()=>lab.connections.size===0,'first lab clients closed');
  // An explicitly abandoned blocked stream must release its listener, timer, queue, and broker session.
  const second=await api(base,'/api/create',{}),abandonLab=app.labs.get(second.id);raw=await rawPaused(base,second.id);const abandoned=[...abandonLab.connections.values()][0];let n=0;
  while(!abandoned.writer.blocked&&n<2000){assert.ok(abandonLab.broker.offer(abandonLab.token,frame(++n)).accepted);app.pump(abandonLab);await sleep(1);}
  assert.equal(abandoned.writer.blocked,true);raw.close();await until(()=>abandoned.closed,'abandoned close');await sleep(450);assert.equal(abandoned.writer.timer,null);assert.equal(abandoned.writer.queue.length,0);assert.equal(abandoned.res.listenerCount('drain'),0);assert.equal(abandonLab.broker.subs.size,0);assert.equal(abandoned.writer.stats.callbacksAfterClose,0);report.cases.push({name:'candidate-real-abandon-while-blocked',passed:true,publications:n,stats:abandoned.writer.stats,remainingBrokerSessions:abandonLab.broker.subs.size,events:abandonLab.events});
  for(const mode of ['drain-resume','drain-never-fires','handover-with-backlog']){
   const createdCase=await api(base,'/api/create',{}),l=app.labs.get(createdCase.id);raw=await rawPaused(base,l.id);const conn=[...l.connections.values()][0];let n=0;const start=performance.now();
   while(!conn.writer.blocked&&n<2000){assert.ok(l.broker.offer(l.token,frame(++n,.6)).accepted);app.pump(l);await sleep(1);assert.ok(performance.now()-start<30000);}
   assert.equal(conn.writer.blocked,true);assert.equal(conn.writer.closed,false);
   if(mode==='drain-resume'){
    for(let i=0;i<2;i++){assert.ok(l.broker.offer(l.token,frame(++n,.6)).accepted);app.pump(l);}const blockedWrites=conn.writer.stats.writes,waitStart=performance.now();raw.res.resume();await until(()=>raw.client.current?.seq===n,'paused reader resumes to latest');assert.ok(conn.writer.stats.drains>=1);assert.equal(raw.client.points.length,n);assert.equal(new Set(raw.client.points.map(p=>p.id)).size,n);assert.equal(raw.client.current.p,.6);assert.deepEqual(raw.errors,[]);assert.equal(conn.closed,false);assert.ok(conn.writer.stats.writes>blockedWrites);report.cases.push({name:'candidate-real-drain-resume',passed:true,publications:n,pausedToLatestMs:performance.now()-waitStart,stats:{...conn.writer.stats},exactFullPointCount:raw.client.points.length,events:l.events});
   }else if(mode==='drain-never-fires'){
    const waitStart=performance.now();await until(()=>conn.closed,'no-drain timeout',{timeout:1500});assert.equal(conn.writer.stats.closeReason,'drain-timeout');assert.equal(conn.writer.stats.drains,0);assert.equal(conn.writer.timer,null);report.cases.push({name:'candidate-real-no-drain-deadline',passed:true,publications:n,observedDisconnectMs:performance.now()-waitStart,configuredStallMs:400,stats:conn.writer.stats,events:l.events});
   }else{
    for(let i=0;i<2;i++){assert.ok(l.broker.offer(l.token,frame(++n,.6)).accepted);app.pump(l);}assert.ok(conn.writer.queue.length>0);const writesBefore=conn.writer.stats.writes;const handed=await api(base,'/api/action',{lab:l.id,action:'handover',p:.2});assert.equal(conn.closed,true);assert.equal(conn.writer.stats.closeReason,'authority-changed-with-backlog');assert.equal(conn.writer.stats.writes,writesBefore);assert.equal(handed.oldRefusal.error,'fenced-or-terminal');raw.close();recovered=new WireClient({base,lab:l.id,leaseMs:30000});await recovered.open();assert.equal(recovered.client.current.epoch,2);assert.equal(recovered.client.current.seq,1);assert.equal(recovered.client.current.p,.2);assert.deepEqual(recovered.client.points.map(p=>[p.epoch,p.seq,p.p]),[[2,1,.2]]);await recovered.renew();assert.equal(recovered.client.points.length,1);report.cases.push({name:'candidate-real-handover-purges-old-backlog-by-disconnect',passed:true,oldPublications:n,stats:conn.writer.stats,recoveryPoints:recovered.client.points,events:l.events});await recovered.close();recovered=null;
   }
   raw.close();await until(()=>l.connections.size===0,'case cleanup');
  }

 }finally{raw?.close();await recovered?.close();await normal?.close();const shutdown=await app.stop('candidate-wire-finished');assert.equal(shutdown.remainingSockets,0);assert.equal(shutdown.remainingLabs,0);assert.equal(shutdown.cleanupTimedOut,false);report.candidateShutdown={remainingSockets:shutdown.remainingSockets,remainingLabs:shutdown.remainingLabs,cleanupTimedOut:shutdown.cleanupTimedOut};}
}
const watchdog=setTimeout(()=>{console.error('WIRE HARNESS EXCEEDED 90 SECOND SAFETY DEADLINE');process.exit(2);},90000);
try{await runBaseline();await runCandidate();report.passed=true;}catch(error){report.passed=false;report.error=error.stack;throw error;}finally{clearTimeout(watchdog);report.endedAt=new Date().toISOString();fs.writeFileSync('results/backpressure-wire.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({...report,cases:report.cases.map(({events,normalTrace,recoveryTrace,firstFalse,...rest})=>rest)}));}

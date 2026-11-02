import {ownedPostgresConfig} from '../owned-postgres.mjs';
// Isolated publication-custody candidate, not production code.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
import {validPayload} from '../baseline/client-core.mjs';
const require=createRequire(process.env.PG_DEPENDENCY_PACKAGE || import.meta.url);
const {Pool}=require('pg');
export const sleep=ms=>new Promise(r=>setTimeout(r,ms));
export const hash=x=>crypto.createHash('sha256').update(JSON.stringify(x)).digest('hex');
export const instrumentScope=Object.freeze({provider:'synthetic-fixture',market:'synthetic-event-1',token:'synthetic-yes',outcome:'yes'});
export const frame=(seq,p=.5)=>({status:'live',event_id:1,seq,p,sources:{kalshi:{value:p}},instrument:{...instrumentScope}});
export const validFrame=p=>validPayload(p)&&p.instrument&&['provider','market','token','outcome'].every(k=>p.instrument[k]===instrumentScope[k])&&Object.keys(p.instrument).length===4;
const identity=j=>`${j.stream}|${j.epoch}|${j.seq}`;
function error(message,extra={}){return Object.assign(Error(message),extra);}
export class Store {
 constructor(){this.errors=[];this.pool=new Pool({...ownedPostgresConfig(),max:8,connectionTimeoutMillis:1000,query_timeout:5000});this.pool.on('error',e=>this.errors.push({kind:'pool',message:e.message}));this.pool.on('connect',client=>client.on('error',e=>this.errors.push({kind:'client',message:e.message})));}
 async init(){await this.pool.query(`CREATE TABLE authority(stream text PRIMARY KEY,generation bigint NOT NULL,epoch text NOT NULL,terminal boolean NOT NULL DEFAULT false); CREATE TABLE log(stream text NOT NULL,epoch text NOT NULL,seq integer NOT NULL,payload jsonb NOT NULL,hash text NOT NULL,writer_generation bigint NOT NULL,receipt timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(stream,epoch,seq)); CREATE TABLE latest(stream text NOT NULL,epoch text NOT NULL,seq integer NOT NULL,hash text NOT NULL,PRIMARY KEY(stream,epoch));`);}
 async claim(stream,epoch=crypto.randomUUID()){
  const c=await this.pool.connect();try{await c.query('BEGIN');await c.query('SELECT pg_advisory_xact_lock(hashtext($1))',[stream]);
   const a=(await c.query('SELECT * FROM authority WHERE stream=$1 FOR UPDATE',[stream])).rows[0];
   if(a?.terminal)throw error('terminal');
   const generation=Number(a?.generation||0)+1;
   await c.query('INSERT INTO authority(stream,generation,epoch) VALUES($1,$2,$3) ON CONFLICT(stream) DO UPDATE SET generation=$2,epoch=$3',[stream,generation,epoch]);await c.query('COMMIT');return {stream,epoch,generation};
  }catch(e){await c.query('ROLLBACK').catch(()=>{});throw e;}finally{c.release();}
 }
 async current(stream){return (await this.pool.query('SELECT * FROM authority WHERE stream=$1',[stream])).rows[0];}
 async terminate(token){const r=await this.pool.query('UPDATE authority SET terminal=true WHERE stream=$1 AND generation=$2 AND epoch=$3 RETURNING *',[token.stream,token.generation,token.epoch]);if(!r.rowCount)throw error('stale-owner');}
 async persist(job,token,{delayMs=0,fail=false,lostAck=false,historical=false,stage=()=>{},lockDelayMs=0}={}){
  if(delayMs)await sleep(delayMs);
  const c=await this.pool.connect();let commitAttempted=false;
  try{await c.query('BEGIN');await c.query("SET LOCAL statement_timeout='4000ms'");
   const a=(await c.query('SELECT * FROM authority WHERE stream=$1 FOR UPDATE',[token.stream])).rows[0];
   if(!a||Number(a.generation)!==token.generation||a.epoch!==token.epoch||a.terminal)throw error('stale-owner');
   if(job.stream!==token.stream||(!historical&&job.epoch!==token.epoch))throw error('stale-publication');
   if(hash(job.payload)!==job.hash||job.seq!==job.payload.seq||!validFrame(job.payload))throw error('invalid-job');
   if(lockDelayMs)await sleep(lockDelayMs);
   stage('before_write',job);if(fail)throw error('injected-unavailable');
   await c.query('INSERT INTO log(stream,epoch,seq,payload,hash,writer_generation) VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING',[job.stream,job.epoch,job.seq,job.payload,job.hash,token.generation]);
   const row=(await c.query('SELECT * FROM log WHERE stream=$1 AND epoch=$2 AND seq=$3',[job.stream,job.epoch,job.seq])).rows[0];
   if(row.hash!==job.hash)throw error('identity-payload-conflict');
   await c.query('INSERT INTO latest(stream,epoch,seq,hash) VALUES($1,$2,$3,$4) ON CONFLICT(stream,epoch) DO UPDATE SET seq=$3,hash=$4 WHERE latest.seq<$3',[job.stream,job.epoch,job.seq,job.hash]);
   stage('after_write',job);commitAttempted=true;await c.query('COMMIT');stage('after_commit',job);
   if(lostAck)throw error('lost-ack',{outcomeUnknown:true});
   return {hash:row.hash,receipt:row.receipt,writerGeneration:Number(row.writer_generation)};
  }catch(e){await c.query('ROLLBACK').catch(()=>{});if(commitAttempted)e.outcomeUnknown=true;throw e;}finally{c.release();}
 }
 async reconcile(job){const r=(await this.pool.query('SELECT * FROM log WHERE stream=$1 AND epoch=$2 AND seq=$3',[job.stream,job.epoch,job.seq])).rows[0];if(!r)return null;if(r.hash!==job.hash)throw error('identity-payload-conflict');return {hash:r.hash,receipt:r.receipt,reconciled:true};}
 async rows(stream){return (await this.pool.query('SELECT * FROM log WHERE stream=$1 ORDER BY epoch,seq',[stream])).rows;}
 async latest(stream,epoch){return (await this.pool.query('SELECT * FROM latest WHERE stream=$1 AND epoch=$2',[stream,epoch])).rows[0];}
 async close(){await this.pool.end();}
}
export class WAL {
 constructor(file,{maxBytes=1024*1024,io=fs}={}){
  this.io=io;this.poisoned=false;
  this.file=file;this.maxBytes=maxBytes;fs.mkdirSync(path.dirname(file),{recursive:true});
  this.fd=fs.openSync(file,'a+');fs.fsyncSync(this.fd);const d=fs.openSync(path.dirname(file),'r');fs.fsyncSync(d);fs.closeSync(d);
  this.bytes=fs.fstatSync(this.fd).size;this.poisoned=this.read().tornTailBytes>0;
 }
 append(job,{sync=true}={}){if(this.poisoned)throw error('wal-unusable');const record={job,checksum:hash(job)};const data=Buffer.from(JSON.stringify(record)+'\n');if(this.bytes+data.length>this.maxBytes)throw error('wal-capacity');try{let n=0;while(n<data.length){const wrote=this.io.writeSync(this.fd,data,n,data.length-n);if(wrote<=0)throw error('wal-zero-write');n+=wrote;}if(sync)this.io.fsyncSync(this.fd);this.bytes+=data.length;return data.length;}catch(e){this.poisoned=true;throw e;}}
 read(){const data=fs.readFileSync(this.file,'utf8'),lines=data.split('\n');const tornTail=lines.pop();const jobs=[];for(let i=0;i<lines.length;i++){let r;try{r=JSON.parse(lines[i]);}catch{throw error(`wal-corrupt-line-${i+1}`);}if(hash(r.job)!==r.checksum||hash(r.job.payload)!==r.job.hash)throw error(`wal-checksum-line-${i+1}`);jobs.push(r.job);}return {jobs,tornTailBytes:Buffer.byteLength(tornTail)};}
 close(){fs.closeSync(this.fd);}
}
export class Owner {
 constructor({token,store,wal=null,mode='memory',capacity=64,concurrency=4,maxAttempts=3,maxEntries=1024,publish=()=>{},policy=()=>({}),stage=()=>{}}){Object.assign(this,{token,store,wal,mode,capacity,concurrency,maxAttempts,maxEntries,publish,policy,stage});this.entries=new Map();this.queue=[];this.active=0;this.outstanding=0;this.maxOutstanding=0;this.lastSeq=0;this.closed=false;this.revision=0;this.stats={offered:0,accepted:0,displayed:0,refused:0,duplicate:0,invalid:0,durable:0,unknown:0,failed:0,retries:0,deliveryErrors:0};}
 emit(m){try{this.publish(m);}catch{this.stats.deliveryErrors++;}}
 offer(payload){const start=performance.now();this.stats.offered++;if(this.closed){this.stats.refused++;return {error:'terminal-or-fenced'};}if(!validFrame(payload)){this.stats.invalid++;return {error:'invalid'};}
  const h=hash(payload),known=this.entries.get(payload.seq);if(known){this.stats.duplicate++;return {error:known.job.hash===h?'duplicate':'identity-payload-conflict'};}if(payload.seq<=this.lastSeq){this.stats.invalid++;return {error:'out-of-order-input'};}
  if(this.outstanding>=this.capacity||this.entries.size>=this.maxEntries){this.stats.refused++;return {error:'capacity'};}
  const job={...this.token,seq:payload.seq,payload:structuredClone(payload),hash:h};this.stage('before_enqueue',job);
  if(this.mode==='wal-before'){try{this.wal.append(job);this.stage('after_wal',job);}catch(e){this.stats.refused++;return {error:e.message};}}
  this.lastSeq=job.seq;this.outstanding++;this.maxOutstanding=Math.max(this.maxOutstanding,this.outstanding);this.stats.accepted++;this.entries.set(job.seq,{job,state:'pending'});this.queue.push(job);this.revision++;this.stage('after_enqueue',job);
  this.stats.displayed++;this.emit({kind:'publication',...job,state:'pending',revision:this.revision,displayLatencyMs:performance.now()-start});this.stage('after_display',job);
  if(this.mode==='wal-after'){try{this.wal.append(job);this.stage('after_wal',job);}catch(e){this.entries.get(job.seq).walError=e.message;this.emit({kind:'wal-error',...job,state:'pending-unprotected'});}}
  this.pump();return {accepted:true};
 }
 pump(){while(!this.closed&&this.active<this.concurrency&&this.queue.length){const j=this.queue.shift();this.active++;this.work(j).finally(()=>{this.active--;this.pump();});}}
 finishJob(job,state,receipt){const item=this.entries.get(job.seq);item.state=state;item.receipt=receipt;this.revision++;if(state==='durable'){this.stats.durable++;this.outstanding--;}else this.stats[state]=(this.stats[state]||0)+1;this.emit({kind:'persistence',...job,state,receipt,revision:this.revision});this.stage('after_ack',job);}
 async work(job){let unknown=false;for(let attempt=1;attempt<=this.maxAttempts;attempt++){
  try{const receipt=await this.store.persist(job,this.token,{...this.policy(job,attempt),stage:this.stage});this.finishJob(job,'durable',receipt);return;}
  catch(e){unknown ||= !!e.outcomeUnknown;
   if(e.message==='stale-owner'){this.closed=true;this.queue.length=0;this.emit({kind:'fenced',...this.token});this.finishJob(job,'fenced');return;}
   if(e.message==='identity-payload-conflict'){this.finishJob(job,'conflict');return;}
   if(attempt===this.maxAttempts){if(unknown){try{const receipt=await this.store.reconcile(job);if(receipt){this.finishJob(job,'durable',receipt);return;}}catch{}}
    this.finishJob(job,unknown?'unknown':'failed');return;}
   this.stats.retries++;await sleep(5*attempt);
  }
 }}
 retryUnresolved(){if(this.closed)return;for(const x of this.entries.values())if(['unknown','failed'].includes(x.state)){x.state='pending';this.queue.push(x.job);}this.pump();}
 snapshot(){if(this.closed)return {available:false,...this.token,revision:this.revision};return {available:true,...this.token,revision:this.revision,entries:[...this.entries.values()].map(x=>structuredClone(x))};}
 async drain(){while(this.active||this.queue.length)await sleep(2);return {...this.stats,outstanding:this.outstanding,maxOutstanding:this.maxOutstanding};}
 fence(){this.closed=true;this.queue.length=0;this.emit({kind:'fenced',...this.token});}
 async terminal(){this.fence();await this.store.terminate(this.token);}
}
// Reconnect must first clear. Only a separately verified current-owner token may
// authorize a snapshot. This model has no distributed failure detector.
export class Client {
 constructor(){this.disconnect();this.points=[];this.rejected=0;}
 disconnect(){this.connected=false;this.current=null;this.token=null;this.revision=0;this.points=[];}
 connect(authority,snapshot){this.disconnect();if(!Number.isSafeInteger(snapshot.revision)||snapshot.revision<0||authority.terminal||!snapshot.available||authority.stream!==snapshot.stream||authority.epoch!==snapshot.epoch||Number(authority.generation)!==snapshot.generation){return {error:'unavailable-or-stale'};}this.token={stream:authority.stream,epoch:authority.epoch,generation:Number(authority.generation)};this.connected=true;this.revision=snapshot.revision;for(const x of snapshot.entries.sort((a,b)=>a.job.seq-b.job.seq))this.accept({kind:'publication',...x.job,state:x.state,receipt:x.receipt,revision:snapshot.revision},true);return {connected:true};}
 accept(m,snapshot=false){if(!this.connected||m.stream!==this.token.stream||m.epoch!==this.token.epoch||m.generation!==this.token.generation){this.rejected++;return {error:'stale-or-disconnected'};}
  if(m.kind==='fenced'){this.disconnect();return {cleared:true};}if(!Number.isSafeInteger(m.revision)||m.revision<0)return {error:'invalid-revision'};if(!snapshot&&m.revision<this.revision){this.rejected++;return {error:'old-revision'};}
  if(!['pending','durable','failed','unknown','fenced','conflict'].includes(m.state)||(m.state==='durable'&&m.receipt?.hash!==m.hash))return {error:'invalid-state-or-receipt'};
  if(m.kind==='persistence'){if(!this.current||m.seq!==this.current.seq||m.hash!==this.current.hash)return {ignored:true};if(this.current.state==='durable'&&m.state!=='durable')return {error:'durable-regression'};this.revision=Math.max(this.revision,m.revision||0);this.current={...this.current,state:m.state};return {statusOnly:true};}
  if(m.kind!=='publication'||!validFrame(m.payload)||m.payload.seq!==m.seq||hash(m.payload)!==m.hash)return {error:'invalid'};
  if(this.current&&m.seq<=this.current.seq)return {error:'duplicate-or-older'};this.revision=Math.max(this.revision,m.revision||0);this.current={seq:m.seq,p:m.payload.p,hash:m.hash,state:m.state,epoch:m.epoch};this.points.push(this.current);return {displayed:true};
 }
}
export async function replay(wal,store,token){const {jobs,tornTailBytes}=wal.read();let committed=0;for(const j of jobs){await store.persist(j,token,{historical:true});committed++;}return {records:jobs.length,committed,tornTailBytes,unique:new Set(jobs.map(identity)).size};}

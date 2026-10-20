import crypto from 'node:crypto';
import {clone,hash,validPayload,validJob,sameToken} from './protocol.mjs';
export {frame,hash,SCOPE} from './protocol.mjs';
export {Client} from './client.mjs';
export class Broker {
 constructor({stream='synthetic-stream',journal=null,persist=null,maxPending=256,maxMailbox=256,maxHistory=100000,maxSessions=128,leaseMs=250,stage=()=>{}}={}){
  this.stream=stream;this.journal=journal;this.persist=persist;this.maxPending=maxPending;this.maxMailbox=maxMailbox;this.maxHistory=maxHistory;this.maxSessions=maxSessions;this.leaseMs=leaseMs;this.stage=stage;
  this.boot=crypto.randomUUID();this.epoch=0;this.ownerId=null;this.status='active';this.revision=0;this.latest=null;this.subs=new Map();this.pending=new Map();this.inflight=new Map();this.history=[];this.stats={accepted:0,rejected:0,sent:0,droppedStale:0,acksIgnored:0,mailboxClosed:0,persistErrors:0};
  if(journal){for(const r of journal.records){if(r.stream!==stream)throw Error('journal-stream');if(!Number.isSafeInteger(r.epoch)||r.epoch<0||!['boot','claim','publication','terminal'].includes(r.kind))throw Error('journal-record');if(r.kind==='publication'&&!validJob(r.job))throw Error('journal-job');if(r.epoch>this.epoch)this.epoch=r.epoch;if(r.kind==='claim')this.ownerId=r.ownerId;if(r.kind==='terminal')this.status='terminal';if(r.kind==='publication')this.history.push(r.job);}
   this.record({kind:'boot',epoch:this.epoch,boot:this.boot});}
 }
 record(r){if(!this.journal)return;this.stage('before_journal',r);this.journal.append({stream:this.stream,...r});this.stage('after_fsync',r);}
 token(){return {stream:this.stream,boot:this.boot,epoch:this.epoch,ownerId:this.ownerId};}
 claim(ownerId=crypto.randomUUID()){
  if(this.status!=='active')return {error:this.status};
  const epoch=this.epoch+1;try{this.record({kind:'claim',epoch,boot:this.boot,ownerId});}catch(e){this.fatal(e.message);return {error:e.message};}
  this.stage('before_claim_linearization',{epoch});this.epoch=epoch;this.ownerId=ownerId;this.latest=null;this.revision++;
  for(const s of this.subs.values())this.reset(s);this.stage('after_claim_linearization',{epoch});return this.token();
 }
 snapshot(s,challenge=null){return {kind:'snapshot',...this.token(),session:s.id,revision:this.revision,status:this.status,latest:this.latest?clone(this.latest):null,...(challenge?{lease:{nonce:challenge,ttlMs:this.leaseMs}}:{})};}
 reset(s,challenge=null){if(s.closed)return;s.queue=[this.snapshot(s,challenge||s.pendingChallenge)];}
 // There is deliberately no await between registering the subscriber and snapshotting.
 open({session,challenge}){if(this.ownerId===null)return {error:'no-owner'};if(typeof session!=='string'||!session||typeof challenge!=='string'||!challenge)return {error:'invalid-session'};
  if(this.subs.has(session))return {error:'duplicate-session'};if(this.subs.size>=this.maxSessions)return {error:'session-capacity'};const s={id:session,queue:[],closed:false,pendingChallenge:challenge};this.subs.set(session,s);this.reset(s,challenge);return {connected:true,boundary:this.revision,boot:this.boot};}
 renew(session,challenge){if(typeof challenge!=='string'||!challenge)return {error:'invalid-challenge'};const s=this.subs.get(session);if(!s||s.closed)return {error:'disconnected'};s.pendingChallenge=challenge;this.reset(s,challenge);return {queued:true};}
 close(session){this.subs.delete(session);}
 enqueue(message){for(const s of this.subs.values()){if(s.closed)continue;if(s.queue.length>=this.maxMailbox){s.closed=true;s.queue=[];this.stats.mailboxClosed++;continue;}s.queue.push({...clone(message),session:s.id});}}
 take(session){const s=this.subs.get(session);if(!s)return null;if(s.closed)return {kind:'disconnect',session,reason:'mailbox-overflow'};
  while(s.queue.length){let m=s.queue.shift();if(!sameToken(m,this.token())||m.kind==='snapshot'&&m.status!==this.status){this.stats.droppedStale++;this.reset(s,m.lease?.nonce);continue;}
   // send linearizes here. A handover after this point cannot retract network bytes.
   if(m.lease?.nonce===s.pendingChallenge)s.pendingChallenge=null;this.stats.sent++;return clone(m);}return null;}
 offer(token,payload){if(this.ownerId===null||this.status!=='active'||!sameToken(token,this.token())){this.stats.rejected++;return {error:'fenced-or-terminal'};}
  if(!validPayload(payload)){this.stats.rejected++;return {error:'invalid'};}if(this.latest&&payload.seq<=this.latest.seq)return {error:'sequence'};
  if(this.pending.size>=this.maxPending||this.history.length>=this.maxHistory)return {error:'capacity'};
  const job={...this.token(),seq:payload.seq,payload:clone(payload),hash:hash(payload)};
  try{this.record({kind:'publication',epoch:this.epoch,job});}catch(e){this.fatal(e.message);return {error:e.message};}
  this.stage('before_publish',job);const message={kind:'publication',...job,revision:++this.revision,state:'pending'};this.latest=clone(message);this.history.push(clone(job));if(this.persist)this.pending.set(hash(job),job);this.enqueue(message);this.stats.accepted++;this.stage('after_publish',message);
  // Deferred invocation, even when persist throws synchronously. PG cannot gate offer.
  if(this.persist)this.schedulePersistence(job);
  return {accepted:true,seq:job.seq};
 }
 schedulePersistence(job){const key=hash(job);if(this.inflight.has(key))return false;const task=Promise.resolve().then(()=>this.persist(clone(job))).then(receipt=>this.ack(job,receipt)).catch(e=>{this.stats.persistErrors++;}).finally(()=>this.inflight.delete(key));this.inflight.set(key,task);return true;}
 retryPending(){let count=0;for(const job of this.pending.values())if(this.schedulePersistence(job))count++;return count;}
 async drain(){while(this.inflight.size)await Promise.allSettled([...this.inflight.values()]);}
 ack(job,receipt){if(!validJob(job)||receipt?.hash!==job.hash)return {error:'invalid-receipt'};this.pending.delete(hash(job));
  if(this.status!=='active'||!sameToken(job,this.token())||!this.latest||this.latest.seq!==job.seq||this.latest.hash!==job.hash){this.stats.acksIgnored++;return {ignored:true};}
  this.latest={...this.latest,state:'durable',receipt:{hash:job.hash},revision:++this.revision};this.enqueue({...clone(this.latest),kind:'persistence'});return {accepted:true};}
 terminal(token){if(this.status!=='active'||!sameToken(token,this.token()))return {error:'fenced-or-terminal'};
  try{this.record({kind:'terminal',epoch:this.epoch,boot:this.boot});}catch(e){this.fatal(e.message);return {error:e.message};}
  this.status='terminal';this.latest=null;this.revision++;for(const s of this.subs.values())this.reset(s);return {terminal:true};}
 fatal(reason){this.status='fatal';this.reason=reason;this.latest=null;this.revision++;for(const s of this.subs.values())this.reset(s);}
}
export function deliver(b,c){let m,n=0;while((m=b.take(c.session))){c.accept(m);n++;if(m.kind==='disconnect')break;}return n;}

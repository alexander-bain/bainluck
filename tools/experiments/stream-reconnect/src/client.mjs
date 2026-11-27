import {clone,int,sameToken,validJob} from './protocol.mjs';
export class Client {
 constructor({stream='synthetic-stream',now=()=>performance.now(),leaseMs=250,maxChallenges=4,maxPoints=4096,maxChallengeIds=4096}={}){this.stream=stream;this.now=now;this.maxLeaseMs=leaseMs;this.maxChallenges=maxChallenges;this.maxChallengeIds=maxChallengeIds;this.maxPoints=maxPoints;this.points=[];this.seen=new Set();this.disconnect();}
 disconnect(){this.current=null;this.session=null;this.boot=null;this.epoch=-1;this.ownerId=null;this.revision=-1;this.deadline=-Infinity;this.challenges=new Map();this.usedChallenges=new Set();this.status='disconnected';}
 start(){const session=globalThis.crypto.randomUUID(),nonce=globalThis.crypto.randomUUID();this.disconnect();this.session=session;this.status='connecting';this.challenges.set(nonce,this.now());this.usedChallenges.add(nonce);return {session,challenge:nonce};}
 challenge(nonce=globalThis.crypto.randomUUID()){if(typeof nonce!=='string'||!nonce||this.usedChallenges.has(nonce)||this.usedChallenges.size>=this.maxChallengeIds)return null;for(const [n,t] of this.challenges)if(this.now()-t>=this.maxLeaseMs)this.challenges.delete(n);if(this.challenges.size>=this.maxChallenges)return null;this.challenges.set(nonce,this.now());this.usedChallenges.add(nonce);return nonce;}
 tick(){if(this.now()>=this.deadline){this.current=null;this.status=this.status==='terminal'?'terminal':'unavailable';}return this.current;}
 validSnapshot(m){return ['active','terminal','fatal'].includes(m.status)&&(!m.latest||validJob(m.latest)&&sameToken(m,m.latest)&&['pending','durable'].includes(m.latest.state)&&(m.latest.state!=='durable'||m.latest.receipt?.hash===m.latest.hash))&&(m.status==='active'||!m.latest);}
 accept(m){this.tick();if(!m||!this.session||m.session!==this.session)return {error:'session'};if(m.kind==='disconnect'){this.disconnect();return {disconnected:true};}
  if(m.stream!==this.stream||typeof m.boot!=='string'||!m.boot||!int(m.epoch)||typeof m.ownerId!=='string'||!int(m.revision))return {error:'identity'};
  if(this.boot&&m.boot!==this.boot)return {error:'incarnation'};
  if(m.kind==='snapshot'){
   if(!this.validSnapshot(m))return {error:'invalid-snapshot'};
   let deadline=this.deadline;if(m.lease){const requested=this.challenges.get(m.lease.nonce);if(requested===undefined||!Number.isFinite(m.lease.ttlMs)||m.lease.ttlMs<=0||m.lease.ttlMs>this.maxLeaseMs)return {error:'lease'};deadline=requested+m.lease.ttlMs;}
   if(m.epoch<this.epoch||m.epoch===this.epoch&&this.ownerId&&m.ownerId!==this.ownerId||m.revision<this.revision)return {error:'old-snapshot'};
   if(!this.boot&&!m.lease)return {error:'no-handshake'};
   // Only completely validated snapshots can consume a challenge or move the cursor.
   if(m.lease)this.challenges.delete(m.lease.nonce);this.boot=m.boot;this.epoch=m.epoch;this.ownerId=m.ownerId;this.revision=m.revision;this.deadline=deadline;this.status=m.status;this.current=null;
   if(m.status==='active'&&this.now()<deadline&&m.latest)this.set(m.latest);this.tick();return {snapshot:true};
  }
  if(m.epoch!==this.epoch||m.ownerId!==this.ownerId||this.status!=='active'||this.now()>=this.deadline)return {error:'fenced-or-expired'};
  if(!validJob(m)||!['pending','durable'].includes(m.state)||m.state==='durable'&&m.receipt?.hash!==m.hash)return {error:'invalid-publication'};
  if(m.revision<=this.revision)return {ignored:true};
  if(m.kind==='persistence'){if(!this.current||this.current.seq!==m.seq||this.current.hash!==m.hash||m.state!=='durable')return {ignored:true};this.current.state='durable';this.revision=m.revision;return {ack:true};}
  if(m.kind!=='publication'||m.state!=='pending')return {error:'kind'};
  if(this.current&&m.seq<=this.current.seq)return {ignored:true};this.set(m);this.revision=m.revision;return {displayed:true};
 }
 set(m){this.current={...clone(m),p:m.payload.p};const id=[m.boot,m.epoch,m.seq,m.hash].join('/');if(!this.seen.has(id)){this.seen.add(id);this.points.push({boot:m.boot,epoch:m.epoch,seq:m.seq,p:m.payload.p,id});if(this.points.length>this.maxPoints){const removed=this.points.shift();this.seen.delete(removed.id);}}}
}

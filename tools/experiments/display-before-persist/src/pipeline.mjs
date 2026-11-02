import crypto from 'node:crypto';
import { validPayload } from './client.mjs';

export const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
export const hash = value => crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');

export class Pipeline {
 constructor({run,arm,epoch=crypto.randomUUID(),store,publish,record=()=>{},capacity=64,concurrency=4,maxAttempts=3,policy=()=>({})}){
  Object.assign(this,{run,arm,epoch,store,publish,record,capacity,concurrency,maxAttempts,policy});this.queue=[];this.active=0;this.outstanding=0;this.maxOutstanding=0;this.closed=false;this.identities=new Map();this.stats={offered:0,durable:0,failed:0,refused:0,retries:0};this.lastSeq=0;
 }
 offer(frame){
  if(this.closed)return {error:'terminal'};
  if(!validPayload(frame))return {error:'invalid'};
  const payload=structuredClone(frame),h=hash(payload),known=this.identities.get(frame.seq);
  if(known)return {error:known===h?'duplicate':'identity-payload-conflict'};
  if(frame.seq<=this.lastSeq)return {error:'out-of-order-input'};
  // Fixed finite experiment, no unbounded idempotency cache masquerading as production.
  if(this.identities.size>=256)return {error:'finite-run-limit'};
  this.lastSeq=frame.seq;this.identities.set(frame.seq,h);this.stats.offered++;
  const job={run:this.run,arm:this.arm,epoch:this.epoch,event:1,seq:frame.seq,payload,hash:h,offeredMono:performance.now()};
  if(this.outstanding>=this.capacity){this.stats.refused++;this.stats.failed++;this.record({kind:'admission-refused',...job,state:'not-queued'});if(this.arm==='display-first')this.emit({kind:'publication',...job,state:'not-queued',failure:'capacity'});return {error:'capacity'};}
  this.outstanding++;this.maxOutstanding=Math.max(this.maxOutstanding,this.outstanding);this.queue.push(job);
  if(this.arm==='display-first')this.emit({kind:'publication',...job,state:'pending'});
  this.record({kind:'offered',...job,state:'pending',outstanding:this.outstanding});this.pump();return {accepted:true,epoch:this.epoch,seq:frame.seq};
 }
 pump(){while(this.active<this.concurrency&&this.queue.length){const job=this.queue.shift();this.active++;this.work(job).finally(()=>{this.active--;this.outstanding--;this.pump();});}}
 emit(message){try{this.publish(message);}catch(error){this.record({kind:'delivery-failed',seq:message.seq,arm:this.arm,error:String(error),state:message.state,mono:performance.now()});}}
 committed(job,receipt,attempt){const committedMono=performance.now();this.stats.durable++;this.record({kind:'durable',seq:job.seq,arm:this.arm,attempt,mono:committedMono,lagMs:committedMono-job.offeredMono,receipt});this.emit({kind:this.arm==='display-first'?'persistence':'publication',...job,state:'durable',committedMono,receipt});}
 async work(job){
  let sawUnknown=false;
  for(let attempt=1;attempt<=this.maxAttempts;attempt++){
   this.record({kind:'attempt',seq:job.seq,arm:this.arm,attempt,mono:performance.now()});
   let receipt;
   try{receipt=await this.store.persist(job,this.policy(job,attempt));}
   catch(error){sawUnknown ||= !!error.outcomeUnknown;this.record({kind:'attempt-failed',seq:job.seq,arm:this.arm,attempt,error:String(error),outcomeUnknown:!!error.outcomeUnknown,mono:performance.now()});
    if(String(error).includes('identity-payload-conflict')||attempt===this.maxAttempts){
     if(sawUnknown){try{const proven=await this.store.reconcile(job);if(proven){this.committed(job,proven,attempt);return;}}catch(reconcileError){this.record({kind:'reconciliation-error',seq:job.seq,arm:this.arm,error:String(reconcileError)});}}
     const state=sawUnknown?'outcome-unknown':'failed';this.stats[state==='failed'?'failed':'unknown']=(this.stats[state==='failed'?'failed':'unknown']||0)+1;this.emit({kind:'persistence',...job,state,failure:String(error)});return;
    }
    this.stats.retries++;await delay(20*attempt);continue;
   }
   this.committed(job,receipt,attempt);return;
  }
 }
 async finish(){this.closed=true;while(this.outstanding)await delay(10);return {...this.stats,maxOutstanding:this.maxOutstanding,outstanding:this.outstanding,epoch:this.epoch};}
}

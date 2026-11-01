import {Client} from './client.mjs';
export const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
export async function until(predicate,label,{timeout=5000}={}){const start=performance.now();while(!predicate()){if(performance.now()-start>timeout)throw Error(`Timed out: ${label}`);await sleep(5);}return predicate();}
export class WireClient {
  constructor({base='',lab,stream='synthetic-stream',leaseMs=1500,onObserve=()=>{},maxRenewControls=2,controlTimeoutMs=5000}={}){this.base=base;this.lab=lab;this.client=new Client({leaseMs,stream});this.trace=[];this.onObserve=onObserve;this.generation=0;this.closed=true;if(!Number.isSafeInteger(maxRenewControls)||maxRenewControls<1||maxRenewControls>4||!Number.isSafeInteger(controlTimeoutMs)||controlTimeoutMs<1||controlTimeoutMs>5000)throw Error('renewal-control-options');this.maxRenewControls=maxRenewControls;this.controlTimeoutMs=controlTimeoutMs;this.renewControls=new Map();this.renewProof=null;this.controlOutcomes=[];}
  log(kind,data={}){const row={n:this.trace.length+1,kind,clientMonoMs:performance.now(),...data};this.trace.push(row);this.onObserve(row,this.client);return row;}
  async api(action,extra={}, {signal}={}){this.log('control-request',{action,...extra});const response=await fetch(`${this.base}/api/action`,{method:'POST',headers:{'Content-Type':'application/json'},signal:signal?AbortSignal.any([signal,AbortSignal.timeout(this.controlTimeoutMs)]):AbortSignal.timeout(this.controlTimeoutMs),body:JSON.stringify({lab:this.lab,action,...extra})});const result=await response.json();if(!response.ok||result.error)throw Error(result.error||response.status);this.log('control-response',{action,result});return result;}
  retireRenewControls(reason){this.renewProof?.finish(Error('renewal-session-changed'));for(const entry of this.renewControls.values()){entry.finish?.(Error('renewal-session-changed'));entry.controller.abort(reason);}}
  receiveEnvelope(envelope,receivedMs=performance.now()){
    const message=envelope.message,result=this.client.accept(message),acceptedMs=performance.now();
    // Confirm in the same task, immediately after the real Client accepted the
    // proof and BEFORE observer/render work. No trace scan or polling timer.
    const confirmation=this.confirmRenewal(message,result);
    this.log('authority-envelope',{message,transport:envelope.transport,receivedMs,acceptedMs,validationMs:acceptedMs-receivedMs,result,current:this.client.current?{epoch:this.client.current.epoch,seq:this.client.current.seq,p:this.client.current.p,state:this.client.current.state}:null,deadlineMs:this.client.deadline,pointCount:this.client.points.length});if(confirmation)this.log('renewal-complete',confirmation);return result;
  }
  confirmRenewal(m,result){
    const entry=this.renewProof,at=this.client.now();
    if(!entry||m?.lease?.nonce!==entry.challenge||entry.finished||result?.snapshot!==true||m?.kind!=='snapshot'||this.closed||entry.generation!==this.generation||entry.session!==this.client.session||m.session!==entry.session||m.stream!==this.client.stream||m.boot!==this.client.boot||m.epoch!==this.client.epoch||m.ownerId!==this.client.ownerId||!Number.isFinite(m.lease.ttlMs)||m.lease.ttlMs<=0||m.lease.ttlMs>this.client.maxLeaseMs||this.client.challenges.has(entry.challenge)||at>=this.client.deadline||at>=entry.requested+m.lease.ttlMs)return false;
    const confirmation={confirmedBy:'accepted-sse-snapshot',challenge:entry.challenge,confirmedAtMs:at,deadlineMs:entry.requested+m.lease.ttlMs,currentDeadlineMs:this.client.deadline,controlResponsePending:!entry.settled,meaning:'proof was valid at confirmedAtMs; consult Client.tick for current authority'};
    entry.finish(null,confirmation);return confirmation;
  }
  async open(){this.retireRenewControls('session-replaced');this.abort?.abort();const generation=++this.generation;this.closed=false;const hello=this.client.start();this.abort=new AbortController();this.log('connect-request',{hello,generation});
    const stream=new URL(`${this.base||location.origin}/stream`);for(const [k,v] of Object.entries({lab:this.lab,...hello}))stream.searchParams.set(k,v);
    this.task=(async()=>{let reader;try{
      const response=await fetch(stream,{signal:this.abort.signal,cache:'no-store'});if(!response.ok)throw Error(`stream-http-${response.status}`);
      if(generation!==this.generation)return;this.log('http-stream-open',{generation});reader=response.body.getReader();const decoder=new TextDecoder();let buffer='';
      while(true){const {done,value}=await reader.read();if(done)break;if(generation!==this.generation)break;buffer+=decoder.decode(value,{stream:true});if(buffer.length>1_000_000)throw Error('sse-buffer-limit');let boundary;
        while((boundary=buffer.indexOf('\n\n'))>=0){const event=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);const data=event.split('\n').filter(line=>line.startsWith('data:')).map(line=>line.slice(5).trimStart()).join('\n');if(!data)continue;const receivedMs=performance.now();this.receiveEnvelope(JSON.parse(data),receivedMs);}
      }
      this.log('http-stream-eof',{generation});
    }catch(error){this.log('http-stream-error',{generation,error:error.name==='AbortError'?'local-abort':error.message});}
    finally{try{await reader?.cancel();}catch{}if(generation===this.generation){this.closed=true;this.client.disconnect();this.log('disconnected',{generation});}}
    })();
    try{
      await until(()=>this.trace.some(r=>r.kind==='authority-envelope'&&r.message.session===hello.session&&r.result.snapshot)||this.closed,'initial authority snapshot');
      if(this.closed)throw Error('stream-closed-before-handshake');
      if(generation!==this.generation||this.client.session!==hello.session)throw Error('handshake-superseded');
      if(this.client.now()>=this.client.deadline)throw Error('initial-handshake-arrived-expired');
      // A fresh terminal/fatal snapshot is a valid handshake, not active authority.
      return hello;
    }catch(error){if(generation===this.generation)await this.close();throw error;}
  }
  renew(){
    if(this.renewal)return this.renewal;
    if(this.closed||!this.client.session)return Promise.reject(Error('renewal-disconnected'));
    if(this.renewControls.size>=this.maxRenewControls)return Promise.reject(Error('renewal-control-capacity'));
    const session=this.client.session,generation=this.generation,challenge=this.client.challenge();
    if(!challenge)return Promise.reject(Error('challenge-capacity'));
    const requested=this.client.challenges.get(challenge),controller=new AbortController();
    const entry={session,generation,challenge,requested,controller,settled:false,finished:false,outcome:null};this.renewControls.set(challenge,entry);this.renewProof=entry;
    let resolve,reject;const task=new Promise((yes,no)=>{resolve=yes;reject=no;});this.renewal=task;
    entry.finish=(error,confirmation)=>{
      if(entry.finished)return;entry.finished=true;clearTimeout(entry.timer);
      controller.abort(error?'renewal-finished':'lease-confirmed-by-sse');
      // Old completion/HTTP callbacks can never clear a newer request slot.
      if(this.renewal===task)this.renewal=null;if(this.renewProof===entry)this.renewProof=null;
      if(error)reject(error);else resolve(confirmation);
    };
    // This timer only bounds failure. Valid proof completion is event-driven.
    entry.timer=setTimeout(()=>entry.finish(Error('renewal-no-valid-lease-before-deadline')),this.client.maxLeaseMs);
    entry.promise=Promise.resolve().then(()=>this.api('renew',{session,challenge},{signal:controller.signal})).then(
      result=>{entry.outcome={ok:true,result};},
      error=>{entry.outcome={ok:false,error:error?.message||String(error)};}
    ).then(()=>{entry.settled=true;this.renewControls.delete(challenge);this.controlOutcomes.push({session,generation,challenge,...entry.outcome});if(this.controlOutcomes.length>64)this.controlOutcomes.shift();});
    return task;
  }
  async ensureAuthority(){
    if(this.client.status!=='active'||this.client.now()>=this.client.deadline-this.client.maxLeaseMs*.75){
      this.log('renewal-policy-trigger',{reason:this.client.now()>=this.client.deadline?'expired-recovery':'remaining-lease-under-75-percent',deadlineMs:this.client.deadline});
      await this.renew();return true;
    }return false;
  }
  tick(){const before=this.client.current;const value=this.client.tick();if(before&&!value)this.log('lease-expiry-observed',{deadlineMs:this.client.deadline});return value;}
  async close(){const pendingRenewal=this.renewal;this.retireRenewControls('client-close');this.generation++;this.abort?.abort();this.client.disconnect();this.closed=true;await this.task;if(pendingRenewal)await Promise.allSettled([pendingRenewal]);this.log('local-close');}
}
